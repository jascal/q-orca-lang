"""Stage 4b state-category assertion checker (`add-runtime-state-assertions`).

For each state annotated with `[assert: …]`, this stage builds the circuit
prefix that drives the machine from `[initial]` to that state, simulates it on
the QuTiP backend, and evaluates the assertion's predicate against the
resulting state vector. See the change's design.md.

Three implementation decisions (recorded here and in tasks.md §6) where the
spec's literal statistical recipe is physically wrong or under-determined:

* `entangled` / `separable` use the **PPT / negativity criterion**
  (Peres–Horodecki) on the reduced two-qubit density matrix, which is exact for
  two qubits — correct on a Bell pair (entangled) and on GHZ pairwise reductions
  (separable). The design's `Tr(ρ²) < 1−ε` on the *pair* is wrong: a 2-qubit
  Bell state's pair purity is exactly 1.
* `classical` / `superposition` treat `assertion_policy.confidence` as the
  Wilson-interval **confidence level** and decide against a fixed *definiteness*
  threshold `_DEFINITENESS`. Overloading `confidence` as both level and
  probability threshold (as the spec text does) makes the canonical passing
  case unprovable — a perfectly classical state's Wilson lower bound sits below
  0.99 at any practical shot count. Sampling uses a fixed seed so verification
  is reproducible (no flaky CI).
* Mid-circuit measurement is handled by **deterministic dominant-outcome
  collapse**: project onto the higher-probability branch, record the bit, and
  fire conditional gates on the recorded bits. The design's assumption that
  Stage 4b already replays measurements is not true of the current code.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Optional

import numpy as np

from q_orca.ast import QAssertion, QMachineDef, QuantumGate
from q_orca.compiler.parametric import expand_action_call
from q_orca.compiler.util import infer_qubit_count
from q_orca.effect_parser import parse_effect_string
from q_orca.verifier import dynamic as _dyn
from q_orca.verifier._partial_trace import reduced_density_matrix
from q_orca.verifier.types import QVerificationError

# Sampling RNG seed — fixed so a verify run is reproducible (deterministic
# PASS/FAIL/INCONCLUSIVE for a given machine + policy).
_SEED = 20260528
# Operational "definiteness" threshold: a single computational-basis outcome
# whose Wilson lower bound clears this is treated as classical/definite.
_DEFINITENESS = 0.90
# Negativity tolerance for the PPT entanglement witness.
_PT_EPS = 1e-6
# Backend names that denote real hardware (no simulator path → assertions are
# skipped). None ship today; this is the forward-looking contract.
_REAL_DEVICE_BACKENDS = frozenset({"ibmq", "ibm_hardware", "hardware", "real_device", "device"})


def check_state_assertions(
    machine: QMachineDef, backend: Optional[str] = None
) -> list[QVerificationError]:
    """Evaluate every `[assert: …]` annotation and return diagnostics.

    `backend` is an optional backend-name hint from the pipeline; the machine's
    `assertion_policy.backend` takes precedence unless it is `'auto'`.
    """
    diagnostics: list[QVerificationError] = []
    policy = machine.assertion_policy

    annotated = [s for s in machine.states if s.assertions]
    if not annotated:
        return diagnostics

    # Resolve the effective backend name.
    effective = policy.backend if policy.backend != "auto" else (backend or "qutip")

    if effective in _REAL_DEVICE_BACKENDS:
        diagnostics.append(QVerificationError(
            code="ASSERTIONS_SKIPPED_NO_SIMULATOR",
            message=(
                f"State assertions skipped: backend '{effective}' is a real "
                f"device with no simulator path; assertions are a debug-time "
                f"simulator check."
            ),
            severity="info",
        ))
        return diagnostics

    if not _dyn.QUTIP_AVAILABLE:
        diagnostics.append(QVerificationError(
            code="ASSERTION_BACKEND_MISSING",
            message=(
                f"State assertions require a simulator backend; "
                f"'{effective}' (QuTiP) is not installed."
            ),
            severity="warning",
        ))
        return diagnostics

    n_qubits = infer_qubit_count(machine)
    angle_ctx = _dyn._build_angle_context(machine)
    reachable = _reachable_states(machine)
    on_fail_severity = "error" if policy.on_failure == "error" else "warning"

    for state in annotated:
        if state.name not in reachable:
            continue  # unreachable states are flagged by the structural stage
        ops = _circuit_prefix_for_state(machine, state.name, angle_ctx)
        if ops is None:
            continue
        state_vec = _simulate(ops, n_qubits)
        for assertion in state.assertions:
            verdict, detail = _eval_assertion(assertion, state_vec, n_qubits, policy)
            diagnostics.append(
                _build_diagnostic(verdict, detail, assertion, state.name, on_fail_severity)
            )

    return diagnostics


# ---------------------------------------------------------------------------
# Circuit-prefix construction
# ---------------------------------------------------------------------------

def _reachable_states(machine: QMachineDef) -> set[str]:
    """State names reachable from the initial state over all transitions."""
    initial = next((s for s in machine.states if s.is_initial), None)
    if initial is None:
        return set()
    reachable = {initial.name}
    frontier = [initial.name]
    while frontier:
        current = frontier.pop()
        for t in machine.transitions:
            if t.source == current and t.target not in reachable:
                reachable.add(t.target)
                frontier.append(t.target)
    return reachable


def _circuit_prefix_for_state(
    machine: QMachineDef, target_name: str, angle_ctx: dict
) -> Optional[list[dict]]:
    """Ops along the first declaration-order path from `[initial]` to a state.

    Returns a list of op dicts (`gate` / `measure` / `cond`), or `None` if no
    path reaches `target_name`. When the machine branches, the first matching
    transition in `machine.transitions` declaration order is taken at each
    node; this is documented behaviour (the assertion is evaluated against the
    canonical prefix, not every interleaving).
    """
    initial = next((s for s in machine.states if s.is_initial), None)
    if initial is None:
        return None
    action_map = {a.name: a for a in machine.actions}

    def dfs(current: str, visited: frozenset) -> Optional[list[dict]]:
        if current == target_name:
            return []
        if current in visited:
            return None
        visited = visited | {current}
        for t in machine.transitions:
            if t.source != current:
                continue
            sub = dfs(t.target, visited)
            if sub is not None:
                return _transition_ops(t, action_map, angle_ctx) + sub
        return None

    return dfs(initial.name, frozenset())


def _transition_ops(transition, action_map: dict, angle_ctx: dict) -> list[dict]:
    """The quantum ops contributed by a single transition's action."""
    if not transition.action:
        return []
    action = action_map.get(transition.action)
    if action is None:
        return []

    if action.mid_circuit_measure is not None:
        m = action.mid_circuit_measure
        return [{"kind": "measure", "qubit": m.qubit_idx, "bit": m.bit_idx}]
    if action.conditional_gate is not None:
        c = action.conditional_gate
        return [{"kind": "cond", "conditions": list(c.conditions), "gate": _qgate_to_dict(c.gate)}]
    if action.context_update is not None:
        return []  # purely classical — no effect on the quantum state
    if action.effect:
        effect = (
            expand_action_call(action, transition.bound_arguments)
            if transition.bound_arguments is not None
            else action.effect
        )
        return [
            {"kind": "gate", "gate": _dyn._parsed_gate_to_dict(g)}
            for g in parse_effect_string(effect, angle_context=angle_ctx)
        ]
    return []


def _qgate_to_dict(gate: QuantumGate) -> dict:
    params: dict[str, float] = {}
    if gate.parameter is not None:
        params["theta"] = gate.parameter
    return {
        "name": gate.kind.upper(),
        "targets": list(gate.targets),
        "controls": list(gate.controls or []),
        "params": params,
    }


# ---------------------------------------------------------------------------
# Simulation (QuTiP state vector + dominant-outcome measurement collapse)
# ---------------------------------------------------------------------------

def _simulate(ops: list[dict], n_qubits: int) -> np.ndarray:
    """Evolve `|0…0>` through `ops` and return the final state vector.

    Measurement collapses deterministically to the higher-probability outcome;
    conditional gates fire when their recorded classical bits match.
    """
    from qutip import basis

    psi = basis([2] * n_qubits, [0] * n_qubits)
    bits: dict[int, int] = {}
    for op in ops:
        kind = op["kind"]
        if kind == "gate":
            psi = _dyn._get_qutip_operator(op["gate"], n_qubits) * psi
        elif kind == "measure":
            psi, outcome = _collapse(psi, op["qubit"], n_qubits)
            bits[op["bit"]] = outcome
        elif kind == "cond":
            if all(bits.get(b) == v for b, v in op["conditions"]):
                psi = _dyn._get_qutip_operator(op["gate"], n_qubits) * psi
    return np.asarray(psi.full()).flatten()


def _collapse(psi, qubit: int, n_qubits: int):
    """Project `psi` onto the dominant Z-basis outcome of `qubit`; renormalize."""
    from qutip import basis, expand_operator, expect

    proj1 = expand_operator(basis(2, 1).proj(), dims=[2] * n_qubits, targets=qubit)
    p1 = float(np.real(expect(proj1, psi)))
    outcome = 1 if p1 >= 0.5 else 0
    proj = expand_operator(
        basis(2, outcome).proj(), dims=[2] * n_qubits, targets=qubit
    )
    collapsed = proj * psi
    norm = collapsed.norm()
    if norm > 1e-12:
        collapsed = collapsed / norm
    return collapsed, outcome


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------

def _eval_assertion(
    assertion: QAssertion, state_vec: np.ndarray, n_qubits: int, policy
) -> tuple[str, str]:
    """Return (verdict, detail) where verdict ∈ {PASSED, FAILED, INCONCLUSIVE}."""
    cat = assertion.category
    if cat in ("entangled", "separable"):
        qi, qj = assertion.targets[0].start, assertion.targets[1].start
        min_eig = _pt_min_eigenvalue(state_vec, n_qubits, qi, qj)
        is_entangled = min_eig < -_PT_EPS
        ok = is_entangled if cat == "entangled" else (not is_entangled)
        return ("PASSED" if ok else "FAILED", f"min partial-transpose eigenvalue={min_eig:.4g}")

    qubits = assertion.targets[0].indices()
    return _concentration_verdict(cat, state_vec, n_qubits, qubits, policy)


def _pt_min_eigenvalue(state_vec: np.ndarray, n_qubits: int, qi: int, qj: int) -> float:
    """Smallest eigenvalue of the partial transpose of ρ on qubits (qi, qj).

    Negative ⇒ entangled (Peres–Horodecki, necessary and sufficient for two
    qubits). The reduced matrix is ordered (qi, qj) ascending by index.
    """
    keep = sorted((qi, qj))
    rho = reduced_density_matrix(state_vec, n_qubits, keep)  # 4×4
    rho4 = rho.reshape(2, 2, 2, 2)  # [a_out, b_out, a_in, b_in]
    rho_pt = rho4.transpose(0, 3, 2, 1).reshape(4, 4)  # transpose subsystem b
    eigs = np.linalg.eigvalsh((rho_pt + rho_pt.conj().T) / 2)
    return float(np.min(eigs.real))


def _concentration_verdict(
    category: str, state_vec: np.ndarray, n_qubits: int, qubits: list[int], policy
) -> tuple[str, str]:
    shots = policy.shots_per_assert
    conf = policy.confidence
    probs = np.abs(state_vec) ** 2
    total = probs.sum()
    if total <= 0:
        return ("INCONCLUSIVE", "degenerate state vector")
    probs = probs / total

    rng = np.random.default_rng(_SEED)
    samples = rng.choice(len(probs), size=shots, p=probs)

    if category == "classical":
        keys = [tuple(_bit(idx, q, n_qubits) for q in qubits) for idx in samples]
        dom = max(Counter(keys).values())
        lo, hi = _wilson(dom, shots, conf)
        if lo >= _DEFINITENESS:
            return ("PASSED", f"dominant outcome ≥ {_DEFINITENESS} (Wilson lo={lo:.3f})")
        if hi < _DEFINITENESS:
            return ("FAILED", f"no outcome reaches {_DEFINITENESS} (Wilson hi={hi:.3f})")
        return ("INCONCLUSIVE", f"dominant-outcome interval [{lo:.3f}, {hi:.3f}] straddles {_DEFINITENESS}")

    # superposition: some qubit in the slice must show both outcomes
    any_superposed = False
    all_definite = True
    for q in qubits:
        ones = int(sum(_bit(idx, q, n_qubits) for idx in samples))
        dom = max(ones, shots - ones)
        lo, hi = _wilson(dom, shots, conf)
        if hi < _DEFINITENESS:
            any_superposed = True
        if lo < _DEFINITENESS:
            all_definite = False
    if any_superposed:
        return ("PASSED", "at least one qubit's dominant outcome is below the definiteness threshold")
    if all_definite:
        return ("FAILED", "every qubit collapses to a definite outcome")
    return ("INCONCLUSIVE", "no qubit confidently superposed at this shot count")


def _bit(index: int, qubit: int, n_qubits: int) -> int:
    """Big-endian bit of `qubit` in basis `index` (qubit 0 = most significant)."""
    return (index >> (n_qubits - 1 - qubit)) & 1


def _wilson(k: int, n: int, confidence: float) -> tuple[float, float]:
    """Wilson score interval for `k` successes in `n` trials at `confidence`."""
    if n == 0:
        return (0.0, 1.0)
    # Two-sided z for the given confidence level.
    z = statistics.NormalDist(0.0, 1.0).inv_cdf((1.0 + confidence) / 2.0)
    phat = k / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _format_assertion(assertion: QAssertion) -> str:
    parts = []
    for sl in assertion.targets:
        parts.append(f"qs[{sl.start}]" if sl.is_single else f"qs[{sl.start}..{sl.end}]")
    return f"{assertion.category}({', '.join(parts)})"


def _build_diagnostic(
    verdict: str, detail: str, assertion: QAssertion, state_name: str, on_fail_severity: str
) -> QVerificationError:
    expr = _format_assertion(assertion)
    location = {"state": state_name, "line": assertion.source_span.line}
    if verdict == "PASSED":
        return QVerificationError(
            code="ASSERTION_PASSED",
            message=f"assertion {expr} holds at state {state_name} ({detail})",
            severity="info",
            location=location,
        )
    if verdict == "INCONCLUSIVE":
        return QVerificationError(
            code="ASSERTION_INCONCLUSIVE",
            message=(
                f"assertion {expr} at state {state_name} is inconclusive "
                f"({detail}); raise shots_per_assert"
            ),
            severity="warning",
            location=location,
        )
    return QVerificationError(
        code="ASSERTION_FAILED",
        message=f"assertion {expr} fails at state {state_name} ({detail})",
        severity=on_fail_severity,
        location=location,
        suggestion="check the gate sequence reaching this state or relax the assertion",
    )
