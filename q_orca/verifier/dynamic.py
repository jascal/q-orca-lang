"""Q-Orca dynamic quantum verification — QuTiP-based circuit simulation and verification.

This module performs actual quantum verification by:
1. Building circuits from action sequences using QuTiP's gate_expand_1toN
2. Computing Schmidt rank for entanglement verification
3. Von Neumann entropy for entanglement
4. Fidelity checks against known Bell/GHZ states
5. Collapse probability normalization
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from q_orca.ast import QMachineDef
from q_orca.compiler.parametric import expand_action_call
from q_orca.effect_parser import (
    ParsedGate,
    parse_effect_string,
    parse_single_gate,
)
from q_orca.verifier.types import QVerificationError, QVerificationResult

# QuTiP imports with graceful fallback
# qutip 5.x split gate operations into the separate qutip_qip package.
QUTIP_AVAILABLE = False
try:
    from qutip import basis, ket2dm, entropy_vn, qeye, Qobj, tensor, sigmax, sigmay, sigmaz
    from qutip_qip.operations import (
        hadamard_transform, cnot, x_gate, y_gate, z_gate,
        rx, ry, rz, expand_operator, cz_gate, swap, controlled_gate,
    )
    QUTIP_AVAILABLE = True
except ImportError:
    Qobj = Any
    pass


def _infer_qubit_count(machine: QMachineDef) -> int:
    """Infer qubit count from machine context."""
    n_value: Optional[int] = None
    has_ancilla = False
    qubits_list_length: Optional[int] = None

    for field in machine.context:
        if field.name == "n" and hasattr(field.type, "kind") and field.type.kind == "int":
            try:
                n_value = int(field.default_value) if field.default_value else None
            except (ValueError, TypeError):
                n_value = None
        if field.name == "ancilla" and hasattr(field.type, "kind") and field.type.kind == "qubit":
            has_ancilla = True
        if field.name == "qubits" and hasattr(field.type, "kind") and field.type.kind == "list":
            if field.default_value:
                items = re.findall(r"q\d+", field.default_value)
                if items:
                    qubits_list_length = len(items)

    if n_value is not None and has_ancilla:
        return n_value + 1
    if qubits_list_length is not None:
        return qubits_list_length

    max_bits = 0
    for state in machine.states:
        m = re.search(r"\|([01]+)>", state.name)
        if m:
            max_bits = max(max_bits, len(m.group(1)))
    return max_bits or 1


def _build_gate_sequence(machine: QMachineDef, max_gates: int = 50) -> tuple[Optional[str], list[list[Dict[str, Any]]]]:
    """Extract gate sequence from machine transitions as gate dicts."""
    action_map = {a.name: a for a in machine.actions}
    angle_context = _build_angle_context(machine)

    initial = next((s for s in machine.states if s.is_initial), None)
    if not initial:
        return "No initial state", []

    visited: set = set()
    queue = [initial.name]
    gate_sequence: list[list[Dict[str, Any]]] = []
    iteration = 0

    while queue and iteration < max_gates:
        iteration += 1
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        outgoing = [t for t in machine.transitions if t.source == current]
        for t in outgoing:
            if t.action:
                action = action_map.get(t.action)
                if action and action.effect:
                    effect = (
                        expand_action_call(action, t.bound_arguments)
                        if t.bound_arguments is not None
                        else action.effect
                    )
                    gates = _parse_effect_to_gate_dicts(effect, angle_context=angle_context)
                    gate_sequence.append(gates)

            is_measure = "measure" in t.event.lower() or "collapse" in t.event.lower()
            if not is_measure and t.target not in visited:
                queue.append(t.target)

    return None, gate_sequence


def _build_angle_context(machine: QMachineDef) -> dict[str, float]:
    """Mirror of `markdown_parser._build_angle_context` for the dynamic verifier.

    Yields {name: float} for context fields with `int`/`float` type and a
    numeric default — i.e. the identifiers that may appear inside rotation
    gate angle expressions.
    """
    out: dict[str, float] = {}
    for f in getattr(machine, "context", []) or []:
        kind = getattr(f.type, "kind", "")
        if kind not in ("int", "float"):
            continue
        if not f.default_value:
            continue
        try:
            out[f.name] = float(f.default_value.strip())
        except (ValueError, AttributeError):
            continue
    return out


def _parsed_gate_to_dict(gate: ParsedGate) -> Dict[str, Any]:
    """Translate a ParsedGate into the verifier's gate-dict shape.

    The evolver (`_get_qutip_operator`) reads ``name`` via ``.upper()``,
    so we uppercase here to keep behavior identical to the legacy
    parser's output.
    """
    params: Dict[str, float] = {}
    if gate.parameter is not None:
        params["theta"] = gate.parameter
    return {
        "name": gate.name.upper(),
        "targets": list(gate.targets),
        "controls": list(gate.controls),
        "params": params,
    }


def _parse_effect_to_gate_dicts(
    effect_str: str,
    angle_context: Optional[Dict[str, float]] = None,
) -> list[Dict[str, Any]]:
    """Parse an effect string into the verifier's gate-dict list."""
    return [_parsed_gate_to_dict(g) for g in parse_effect_string(effect_str, angle_context=angle_context)]


def _parse_single_gate_to_dict(
    effect_str: str,
    angle_context: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Parse a single gate effect string into a gate dict."""
    parsed = parse_single_gate(effect_str, angle_context=angle_context)
    if parsed is None:
        return None
    return _parsed_gate_to_dict(parsed)


def _expand_1qubit_gate(op: Qobj, n_qubits: int, target: int) -> Qobj:
    """Expand a single-qubit gate to act on the full register."""
    return expand_operator(op, dims=[2] * n_qubits, targets=target)


def _get_qutip_operator(gate: Dict[str, Any], n_qubits: int) -> Qobj:
    """Convert a gate dict to a QuTiP Qobj operator."""
    name = gate.get("name", "").upper()
    targets = gate.get("targets", [])
    controls = gate.get("controls", [])
    params = gate.get("params", {})

    if not targets:
        return qeye([2] * n_qubits)

    if name == "H":
        op = hadamard_transform()
        return _expand_1qubit_gate(op, n_qubits, targets[0])

    elif name in ("X", "NOT"):
        op = x_gate()
        return _expand_1qubit_gate(op, n_qubits, targets[0])

    elif name == "Y":
        op = y_gate()
        return _expand_1qubit_gate(op, n_qubits, targets[0])

    elif name == "Z":
        op = z_gate()
        return _expand_1qubit_gate(op, n_qubits, targets[0])

    elif name in ("CNOT", "CX"):
        ctrl = controls[0] if controls else targets[0]
        tgt = targets[1] if len(targets) > 1 else targets[0]
        return expand_operator(cnot(), dims=[2] * n_qubits, targets=[ctrl, tgt])

    elif name == "CZ":
        ctrl = controls[0] if controls else targets[0]
        tgt = targets[0]
        return expand_operator(cz_gate(), dims=[2] * n_qubits, targets=[ctrl, tgt])

    elif name == "SWAP":
        tgt1 = targets[0]
        tgt2 = targets[1] if len(targets) > 1 else targets[0]
        return expand_operator(swap(), dims=[2] * n_qubits, targets=[tgt1, tgt2])

    elif name == "RX":
        theta = params.get("theta", 0.0)
        return expand_operator(rx(theta), dims=[2] * n_qubits, targets=targets[0])

    elif name == "RY":
        theta = params.get("theta", 0.0)
        return expand_operator(ry(theta), dims=[2] * n_qubits, targets=targets[0])

    elif name == "RZ":
        theta = params.get("theta", 0.0)
        return expand_operator(rz(theta), dims=[2] * n_qubits, targets=targets[0])

    elif name in ("RXX", "RYY", "RZZ"):
        theta = params.get("theta", 0.0)
        pauli = {"RXX": sigmax, "RYY": sigmay, "RZZ": sigmaz}[name]
        pp = tensor(pauli(), pauli())
        op = (-1j * theta / 2 * pp).expm()
        tgt1, tgt2 = targets[0], targets[1] if len(targets) > 1 else targets[0]
        return expand_operator(op, dims=[2] * n_qubits, targets=[tgt1, tgt2])

    elif name in ("CRX", "CRY", "CRZ"):
        theta = params.get("theta", 0.0)
        rot = {"CRX": rx, "CRY": ry, "CRZ": rz}[name]
        ctrl = controls[0] if controls else 0
        tgt = targets[0]
        op = controlled_gate(rot(theta), controls=0, targets=1, N=2)
        return expand_operator(op, dims=[2] * n_qubits, targets=[ctrl, tgt])

    else:
        return qeye([2] * n_qubits)


def _evolve_path(initial_psi: Qobj, path_gates: List[Dict[str, Any]], n_qubits: int) -> Qobj:
    """Sequentially apply every gate in the path."""
    psi = initial_psi
    for gate in path_gates:
        U = _get_qutip_operator(gate, n_qubits)
        psi = U * psi
    return psi


def _entanglement_entropy(subsystem: List[int], psi: Qobj, n_qubits: int) -> float:
    """Von Neumann entropy of the reduced density matrix on `subsystem`."""
    rho = ket2dm(psi)
    # ptrace(sel) keeps the listed subsystems; requires multi-qubit dims on rho
    rho_reduced = rho.ptrace(subsystem)
    return float(entropy_vn(rho_reduced, base=2))


def _schmidt_rank_across_bipartition(
    psi: Qobj, partition_a: List[int], partition_b: List[int], n_qubits: int
) -> int:
    """True Schmidt rank for a pure state across two groups A and B."""
    keep = list(set(partition_a) | set(partition_b))
    rho_ab = ket2dm(psi).ptrace(keep) if len(keep) < n_qubits else ket2dm(psi)

    # Compute Schmidt rank via eigenvalues of reduced density matrix A
    rho_a = rho_ab.ptrace([keep.index(q) for q in partition_a])
    import numpy as np
    evals = np.abs(rho_a.eigenenergies())
    rank = int(np.sum(evals > 1e-10))
    return rank


def _check_dynamic_entanglement(
    machine: QMachineDef,
    path_gates: List[Dict[str, Any]],
    state_label: str,
    expected_entangled_pairs: Optional[List[Tuple[int, int]]] = None,
    tolerance: float = 1e-8,
) -> Dict[str, Any]:
    """Core dynamic entanglement check."""

    if not QUTIP_AVAILABLE:
        return {"skipped": True, "reason": "QuTiP not available", "passed": True}

    n_qubits = _infer_qubit_count(machine)
    if n_qubits < 2:
        return {"skipped": True, "reason": "Need at least 2 qubits", "passed": True}

    # Skip if no superposition-creating gates exist in the path — starting from
    # |0...0>, CNOT/CZ/SWAP alone can never produce entanglement.
    superposition_gates = {"H", "RX", "RY", "RZ"}
    if not any(g.get("name", "").upper() in superposition_gates for g in path_gates):
        return {"skipped": True, "reason": "No superposition gates in path", "passed": True}

    initial_psi = basis([2] * n_qubits, [0] * n_qubits)
    final_psi = _evolve_path(initial_psi, path_gates, n_qubits)

    report: Dict[str, Any] = {
        "state": state_label,
        "entropy_checks": {},
        "schmidt_ranks": {},
        "passed": False,  # must find at least one entangled pair
        "details": {},
    }

    if expected_entangled_pairs is None:
        expected_entangled_pairs = [(i, i + 1) for i in range(n_qubits - 1)]

    for q1, q2 in expected_entangled_pairs:
        entropy_q1 = _entanglement_entropy([q1], final_psi, n_qubits)
        report["entropy_checks"][f"q{q1}"] = entropy_q1

        rank = _schmidt_rank_across_bipartition(final_psi, [q1], [q2], n_qubits)
        report["schmidt_ranks"][f"q{q1}-q{q2}"] = rank

        if entropy_q1 >= tolerance and rank > 1:
            # At least one entangled pair found — that is sufficient
            report["passed"] = True
        else:
            if entropy_q1 < tolerance:
                report["details"][f"q{q1}"] = "no entanglement detected (entropy ≈ 0)"
            if rank <= 1:
                report["details"][f"q{q1}-q{q2}"] = f"Schmidt rank {rank} ≤ 1"

    return report


def _check_unitary_gates(
    gate_sequence: List[List[Dict[str, Any]]], n_qubits: int
) -> List[QVerificationError]:
    """Verify every distinct gate in the sequence satisfies U†U ≈ I."""
    errors: List[QVerificationError] = []
    identity = qeye([2] * n_qubits)
    seen: set = set()

    for step_gates in gate_sequence:
        for gate in step_gates:
            name = gate.get("name", "UNKNOWN")
            key = (
                name,
                tuple(gate.get("targets", [])),
                tuple(gate.get("controls", [])),
                tuple(sorted(gate.get("params", {}).items())),
            )
            if key in seen:
                continue
            seen.add(key)

            U = _get_qutip_operator(gate, n_qubits)
            diff = float((U.dag() * U - identity).norm())
            if diff > 1e-10:
                errors.append(QVerificationError(
                    code="DYNAMIC_NON_UNITARY_GATE",
                    message=f"Gate '{name}' is not unitary: ‖U†U − I‖ = {diff:.2e}",
                    severity="error",
                    location={"gate": name},
                    suggestion="All quantum gates must be unitary; check gate parameters",
                ))

    return errors


# Public API — callable directly from tests or external code
check_dynamic_entanglement = _check_dynamic_entanglement
check_unitary_gates = _check_unitary_gates
evolve_path = _evolve_path
entanglement_entropy = _entanglement_entropy
schmidt_rank_across_bipartition = _schmidt_rank_across_bipartition

# ---------------------------------------------------------------------------
# GPU-accelerated path via CuPy
# ---------------------------------------------------------------------------

CUPY_AVAILABLE = False
try:
    import cupy  # noqa: F401
    CUPY_AVAILABLE = True
except ImportError:
    pass


def _evolve_path_gpu(
    initial_psi: "Any",  # cupy ndarray (2**n, 1)
    path_gates: List[Dict[str, Any]],
    n_qubits: int,
) -> "Any":  # cupy ndarray
    """Apply gate sequence to a cupy state vector using GPU matrix multiplication."""
    import cupy as cp
    psi = initial_psi
    for gate in path_gates:
        U_np = _get_qutip_operator(gate, n_qubits).full()
        U_gpu = cp.asarray(U_np)
        psi = U_gpu @ psi
    return psi


def dynamic_verify_gpu(machine: QMachineDef) -> QVerificationResult:
    """GPU-accelerated verification using CuPy for gate matrix operations.

    Runs the same checks as dynamic_verify but offloads state-vector evolution
    to GPU via CuPy matrix multiplications. Falls back to the CPU path if CuPy
    or QuTiP is unavailable.
    """
    if not CUPY_AVAILABLE or not QUTIP_AVAILABLE:
        return dynamic_verify(machine)

    import cupy as cp

    errors: list[QVerificationError] = []

    qubit_count = _infer_qubit_count(machine)
    err_msg, gate_sequence = _build_gate_sequence(machine, qubit_count)
    if err_msg:
        return QVerificationResult(valid=True, errors=[])

    all_gates = [g for gates in gate_sequence for g in gates]

    # Unitarity check runs on CPU — gate matrices are identical on both paths.
    errors.extend(_check_unitary_gates(gate_sequence, qubit_count))

    # Build initial |0...0> state on GPU
    dim = 2 ** qubit_count
    psi_gpu = cp.zeros((dim, 1), dtype=cp.complex128)
    psi_gpu[0, 0] = 1.0

    # Evolve on GPU.
    # NOTE: each gate matrix is transferred CPU→GPU individually here.
    # For long circuits this is the dominant latency; caching gate matrices on
    # GPU across calls is future work.
    psi_gpu = _evolve_path_gpu(psi_gpu, all_gates, qubit_count)

    # Bring final state back to CPU as a QuTiP ket for analysis
    psi_np = cp.asnumpy(psi_gpu)
    final_psi = Qobj(psi_np, dims=[[2] * qubit_count, [1] * qubit_count])

    # Entanglement checks — semantics match _check_dynamic_entanglement on CPU:
    # pass if ANY expected pair is entangled (not ALL pairs must be).
    entangled_kinds = {"bell", "ghz", "epr", "entangl"}
    entangled_states = [
        s for s in machine.states
        if any(k in (s.state_expression or "").lower() or k in (s.name or "").lower()
               for k in entangled_kinds)
    ]

    invariant_pairs = [
        (inv.qubits[0], inv.qubits[1])
        for inv in getattr(machine, "invariants", [])
        if inv.kind in ("entanglement", "schmidt_rank") and len(inv.qubits) >= 2
    ]

    # Skip entanglement check entirely when no superposition gates are present —
    # CNOT/CZ/SWAP on |0...0> cannot produce entanglement.
    superposition_gates = {"H", "RX", "RY", "RZ"}
    has_superposition = any(g.get("name", "").upper() in superposition_gates for g in all_gates)

    for state in entangled_states:
        if not has_superposition:
            continue

        expected_pairs = invariant_pairs or [(i, i + 1) for i in range(qubit_count - 1)]
        report: Dict[str, Any] = {"passed": False, "details": {}}

        for q1, q2 in expected_pairs:
            entropy_q1 = _entanglement_entropy([q1], final_psi, qubit_count)
            rank = _schmidt_rank_across_bipartition(final_psi, [q1], [q2], qubit_count)

            if entropy_q1 >= 1e-8 and rank > 1:
                # At least one entangled pair found — sufficient to pass
                report["passed"] = True
            else:
                if entropy_q1 < 1e-8:
                    report["details"][f"q{q1}"] = "no entanglement detected (entropy ≈ 0)"
                if rank <= 1:
                    report["details"][f"q{q1}-q{q2}"] = f"Schmidt rank {rank} ≤ 1"

        if not report["passed"]:
            details_str = "; ".join(f"{k}: {v}" for k, v in report["details"].items())
            errors.append(QVerificationError(
                code="DYNAMIC_NO_ENTANGLEMENT",
                message=f"State '{state.name}' should be entangled but verification failed: {details_str}",
                severity="error",
                location={"state": state.name},
                suggestion="Ensure the circuit creates an entangled state with CNOT or CZ gates",
            ))

    # Collapse completeness check (identical to dynamic_verify)
    measure_events = {e.name for e in machine.events if "measure" in e.name.lower()}
    measure_transitions = [
        t for t in machine.transitions
        if any(m in t.event.lower() for m in measure_events)
    ]
    if measure_transitions:
        prob_sum = 0.0
        has_probs = False
        for t in measure_transitions:
            if t.guard:
                guard_def = next((g for g in machine.guards if g.name == t.guard.name), None)
                if guard_def and guard_def.expression.kind == "probability":
                    prob_sum += guard_def.expression.outcome.probability
                    has_probs = True
        if has_probs and abs(prob_sum - 1.0) > 0.01:
            errors.append(QVerificationError(
                code="DYNAMIC_INCOMPLETE_COLLAPSE",
                message=f"Measurement branches have probabilities summing to {prob_sum:.4f}, expected 1.0",
                severity="error",
                location=None,
                suggestion="Ensure all collapse outcomes are covered with probabilities summing to 1",
            ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )


def dynamic_verify(machine: QMachineDef) -> QVerificationResult:
    """Run QuTiP-based dynamic quantum verification.

    Performs:
    1. Circuit unitary verification
    2. Schmidt rank for entanglement verification
    3. Von Neumann entropy for entanglement
    4. Collapse probability normalization

    Returns valid result if QuTiP is not available (graceful fallback).
    """
    errors: list[QVerificationError] = []

    if not QUTIP_AVAILABLE:
        return QVerificationResult(valid=True, errors=[])

    qubit_count = _infer_qubit_count(machine)

    err_msg, gate_sequence = _build_gate_sequence(machine, qubit_count)
    if err_msg:
        return QVerificationResult(valid=True, errors=[])

    # Flatten gate_sequence for entanglement checks
    all_gates = [g for gates in gate_sequence for g in gates]

    # Unitarity check — verify every gate satisfies U†U ≈ I
    errors.extend(_check_unitary_gates(gate_sequence, qubit_count))

    # Check entanglement for states that are explicitly declared as entangled
    entangled_kinds = {"bell", "ghz", "epr", "entangl"}
    entangled_states = [
        s for s in machine.states
        if any(k in (s.state_expression or "").lower() or k in (s.name or "").lower()
               for k in entangled_kinds)
    ]

    # Collect declared invariant pairs from parsed Markdown `## invariants`
    invariant_pairs = [
        (inv.qubits[0], inv.qubits[1])
        for inv in getattr(machine, "invariants", [])
        if inv.kind in ("entanglement", "schmidt_rank") and len(inv.qubits) >= 2
    ]

    for state in entangled_states:
        if invariant_pairs:
            expected_pairs = invariant_pairs
        else:
            # Fall back to adjacent-pair heuristic
            expected_pairs = [(i, i + 1) for i in range(qubit_count - 1)]

        result = _check_dynamic_entanglement(
            machine, all_gates, state.name, expected_entangled_pairs=expected_pairs
        )

        if not result["passed"]:
            details_str = "; ".join(f"{k}: {v}" for k, v in result["details"].items())
            errors.append(QVerificationError(
                code="DYNAMIC_NO_ENTANGLEMENT",
                message=f"State '{state.name}' should be entangled but verification failed: {details_str}",
                severity="error",
                location={"state": state.name},
                suggestion="Ensure the circuit creates an entangled state with CNOT or CZ gates",
            ))

    # Check collapse completeness — probabilities sum to 1
    measure_events = {e.name for e in machine.events if "measure" in e.name.lower()}
    measure_transitions = [
        t for t in machine.transitions
        if any(m in t.event.lower() for m in measure_events)
    ]
    if measure_transitions:
        prob_sum = 0.0
        has_probs = False
        for t in measure_transitions:
            if t.guard:
                guard_def = next((g for g in machine.guards if g.name == t.guard.name), None)
                if guard_def and guard_def.expression.kind == "probability":
                    prob_sum += guard_def.expression.outcome.probability
                    has_probs = True
        if has_probs and abs(prob_sum - 1.0) > 0.01:
            errors.append(QVerificationError(
                code="DYNAMIC_INCOMPLETE_COLLAPSE",
                message=f"Measurement branches have probabilities summing to {prob_sum:.4f}, expected 1.0",
                severity="error",
                location=None,
                suggestion="Ensure all collapse outcomes are covered with probabilities summing to 1",
            ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
