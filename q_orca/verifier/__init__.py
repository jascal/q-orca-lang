"""Q-Orca verifier — 5-stage verification pipeline."""

from dataclasses import dataclass
from typing import Optional

from q_orca.ast import QMachineDef, QOrcaFile
from q_orca.verifier.structural import check_structural
from q_orca.verifier.completeness import check_completeness
from q_orca.verifier.determinism import check_determinism
from q_orca.verifier.classical_context import check_classical_context
from q_orca.verifier.quantum import verify_quantum
from q_orca.verifier.resources import check_resource_invariants
from q_orca.verifier.superposition import check_superposition_leaks
from q_orca.verifier.hea_encoding import check_hea_encoding
from q_orca.verifier.types import QVerificationResult, QVerificationError


@dataclass
class VerifyOptions:
    skip_completeness: bool = False
    skip_quantum: bool = False
    skip_qutip: bool = False
    skip_dynamic: bool = False
    skip_classical_context: bool = False
    skip_resource_bounds: bool = False
    skip_state_assertions: bool = False
    skip_composition: bool = False
    skip_noise_model: bool = False
    skip_qubit_roles: bool = False
    skip_loop_verification: bool = False
    backend: str = "qutip"
    compile_target: Optional[str] = None  # noise backend-compatibility checks key off this


def verify(
    machine: QMachineDef,
    options: Optional[VerifyOptions] = None,
    file: Optional[QOrcaFile] = None,
    import_graph=None,
    _visited: Optional[frozenset] = None,
) -> QVerificationResult:
    """Run the full verification pipeline on a quantum machine definition.

    `file` supplies the surrounding `QOrcaFile` so the composition stage can
    resolve sibling machines for `[invoke: …]` states; it is optional and the
    composition stage is skipped when it is absent. `_visited` is an internal
    guard against unbounded recursion during nested composition verification.
    """
    opts = options or VerifyOptions()
    all_errors: list[QVerificationError] = []

    # Stage 1: Structural
    structural = check_structural(machine)
    all_errors.extend(structural.errors)

    if not structural.valid:
        return QVerificationResult(valid=False, errors=all_errors)

    # Stage 2: Completeness
    if not opts.skip_completeness:
        completeness = check_completeness(machine)
        all_errors.extend(completeness.errors)

    # Stage 3: Determinism
    determinism = check_determinism(machine)
    all_errors.extend(determinism.errors)

    # Stage 3b: Classical-context (types + feedforward completeness)
    if not opts.skip_classical_context:
        classical = check_classical_context(machine)
        all_errors.extend(classical.errors)

    # Stage 3d: Noise model (## noise_model section + deprecated alias). Runs
    # only when a noise model resolves; backend-compatibility keys off
    # opts.compile_target (None in a plain verify).
    if not opts.skip_noise_model:
        from q_orca.verifier.noise_model import check_noise_model
        noise = check_noise_model(machine, target=opts.compile_target)
        all_errors.extend(noise.errors)

    # Stage 3e: Qubit-role structural rules (ancilla reset, syndrome
    # completeness). Fire automatically when any non-`data` role is declared.
    if not opts.skip_qubit_roles:
        from q_orca.verifier.roles import check_qubit_roles
        all_errors.extend(check_qubit_roles(machine).errors)

    # Stage 3f: Bounded-loop structural rules (well-formed body, body
    # unitarity, adaptive-termination reachability). Fire automatically when
    # any `[loop …]`-annotated state is present.
    if not opts.skip_loop_verification:
        from q_orca.verifier.loops import check_loop_rules
        all_errors.extend(check_loop_rules(machine).errors)

    # Stage 3c: Composition (multi-machine invoke/return checks). Runs only
    # when a surrounding file is supplied and the machine has invoke states.
    if (
        not opts.skip_composition
        and file is not None
        and any(s.invoke is not None for s in machine.states)
    ):
        from q_orca.verifier.composition import check_composition
        composition = check_composition(
            file, machine, opts, import_graph=import_graph, _visited=_visited)
        all_errors.extend(composition.errors)

    # Stage 4: Quantum-specific checks
    if not opts.skip_quantum:
        quantum = verify_quantum(machine)
        all_errors.extend(quantum.errors)

    # Stage 4b: Dynamic quantum verification via selected backend
    if not opts.skip_dynamic:
        dynamic_errors, _ = _run_dynamic_backend(machine, opts.backend)
        all_errors.extend(dynamic_errors)

        # Stage 4b (HEA): consistency check for explicit-grammar HEA
        # machines. Builds per-concept statevectors via numpy
        # simulation, so it lives under the same `skip_dynamic` gate
        # as the backend dispatch above.
        all_errors.extend(check_hea_encoding(machine))

    # Stage 4c: Resource-bound invariants (opt-in, gated by presence)
    if not opts.skip_resource_bounds:
        all_errors.extend(check_resource_invariants(machine))

    # Stage 5: Superposition leak check
    superposition = check_superposition_leaks(machine)
    all_errors.extend(superposition.errors)

    # Stage 6: State-category assertions (opt-in via the `state_assertions`
    # verification rule + at least one `[assert: …]` annotation). Skipped
    # entirely when the rule is absent so annotated-but-not-opted-in machines
    # emit no assertion diagnostics.
    if not opts.skip_state_assertions and _has_state_assertions_rule(machine):
        from q_orca.verifier.assertions import check_state_assertions
        all_errors.extend(check_state_assertions(machine, opts.backend))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in all_errors),
        errors=all_errors,
    )


def _has_state_assertions_rule(machine: QMachineDef) -> bool:
    return any(r.kind == "state_assertions" for r in machine.verification_rules)


def _run_dynamic_backend(machine: QMachineDef, backend_name: str):
    """Dispatch Stage 4b to the named backend, falling back to QuTiP on unavailability.

    Returns (errors: list[QVerificationError], backend_result_or_None).
    Emits a BACKEND_UNAVAILABLE warning when a fallback occurs.
    """
    from q_orca.backends import BackendRegistry, BackendUnavailableError

    try:
        adapter, fell_back = BackendRegistry.get_with_fallback(backend_name)
    except BackendUnavailableError as exc:
        # No backend at all — degrade gracefully (same as skip_dynamic)
        warn = QVerificationError(
            code="BACKEND_UNAVAILABLE",
            message=str(exc),
            severity="warning",
        )
        return [warn], None

    result, backend_result = adapter.verify(machine)

    errors: list[QVerificationError] = list(result.errors)
    if fell_back:
        errors.insert(0, QVerificationError(
            code="BACKEND_UNAVAILABLE",
            message=(
                f"Backend '{backend_name}' is not available; "
                f"fell back to '{adapter.name}'"
            ),
            severity="warning",
        ))

    return errors, backend_result


__all__ = ["verify", "VerifyOptions", "QVerificationResult", "QVerificationError"]
