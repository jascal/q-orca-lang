"""Q-Orca verifier — 5-stage verification pipeline."""

from dataclasses import dataclass
from typing import Optional

from q_orca.ast import QMachineDef
from q_orca.verifier.structural import check_structural
from q_orca.verifier.completeness import check_completeness
from q_orca.verifier.determinism import check_determinism
from q_orca.verifier.quantum import verify_quantum
from q_orca.verifier.superposition import check_superposition_leaks
from q_orca.verifier.types import QVerificationResult, QVerificationError


@dataclass
class VerifyOptions:
    skip_completeness: bool = False
    skip_quantum: bool = False
    skip_qutip: bool = False
    skip_dynamic: bool = False
    backend: str = "qutip"


def verify(machine: QMachineDef, options: Optional[VerifyOptions] = None) -> QVerificationResult:
    """Run the full verification pipeline on a quantum machine definition."""
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

    # Stage 4: Quantum-specific checks
    if not opts.skip_quantum:
        quantum = verify_quantum(machine)
        all_errors.extend(quantum.errors)

    # Stage 4b: Dynamic quantum verification via selected backend
    if not opts.skip_dynamic:
        dynamic_errors, _ = _run_dynamic_backend(machine, opts.backend)
        all_errors.extend(dynamic_errors)

    # Stage 5: Superposition leak check
    superposition = check_superposition_leaks(machine)
    all_errors.extend(superposition.errors)

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in all_errors),
        errors=all_errors,
    )


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
