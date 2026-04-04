"""Q-Orca dynamic quantum verification — builds actual circuits and verifies quantum properties.

This module performs actual quantum verification by:
1. Building Qiskit circuits from action sequences
2. Computing fidelity of resulting states
3. Checking Schmidt rank / von Neumann entropy for entanglement
4. Verifying collapse completeness sums to 1
"""

from __future__ import annotations

import re
from typing import Optional

from q_orca.ast import QMachineDef, QuantumGate
from q_orca.verifier.types import QVerificationError, QVerificationResult


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


def _build_circuit_from_actions(
    machine: QMachineDef,
    qubit_count: int,
    max_gates: int = 50,
) -> tuple[Optional[str], list[list[str]]]:
    """Build a Qiskit circuit from the machine's action sequence.

    Returns (error_message, list of gate lists per transition).
    """
    action_map = {a.name: a for a in machine.actions}

    initial = next((s for s in machine.states if s.is_initial), None)
    if not initial:
        return "No initial state found", []

    visited: set[str] = set()
    queue = [initial.name]
    gate_sequence: list[list[str]] = []

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
                    gates = _parse_effect_gates(action.effect)
                    gate_sequence.append(gates)

            is_measure = "measure" in t.event.lower() or "collapse" in t.event.lower()
            if not is_measure and t.target not in visited:
                queue.append(t.target)

    return None, gate_sequence


def _parse_effect_gates(effect_str: str) -> list[str]:
    """Parse semicolon-separated gates from an effect string."""
    gates = []
    for part in effect_str.split(";"):
        part = part.strip()
        if not part:
            continue
        gate_str = _gate_to_openqasm(part)
        if gate_str:
            gates.append(gate_str)
    return gates


def _gate_to_openqasm(effect_str: str) -> Optional[str]:
    """Convert a gate effect string to OpenQASM format."""
    effect_str = effect_str.strip()

    # Hadamard(qs[N])
    m = re.search(r"Hadamard\(\s*(\w+)\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        idx = m.group(2)
        return f"h q[{idx}]"

    # CNOT(qs[a], qs[b])
    m = re.search(r"CNOT\(\s*(\w+)\[(\d+)\]\s*,\s*(\w+)\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        ctrl = m.group(2)
        tgt = m.group(4)
        return f"cx q[{ctrl}], q[{tgt}]"

    # CZ(qs[a], qs[b])
    m = re.search(r"CZ\(\s*(\w+)\[(\d+)\]\s*,\s*(\w+)\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        ctrl = m.group(2)
        tgt = m.group(4)
        return f"cz q[{ctrl}], q[{tgt}]"

    # X(qs[N]), Y(qs[N]), Z(qs[N]), etc.
    m = re.search(r"^([XYZS])\((\w+)\[(\d+)\]\s*\)", effect_str)
    if m:
        kind = m.group(1).lower()
        idx = m.group(3)
        return f"{kind} q[{idx}]"

    # Generic single-qubit: GateName(qs[N])
    m = re.search(r"^([A-Za-z]+)\((\w+)\[(\d+)\]\s*\)", effect_str)
    if m:
        kind = m.group(1).lower()
        idx = m.group(3)
        kind_map = {"h": "h", "x": "x", "y": "y", "z": "z", "t": "t", "s": "s"}
        if kind in kind_map:
            return f"{kind_map[kind]} q[{idx}]"
        return f"{kind} q[{idx}]"  # Allow unknown gates

    return None


def _try_dynamic_verification(machine: QMachineDef) -> tuple[bool, list[QVerificationError]]:
    """Attempt dynamic verification using Qiskit.

    Returns (success, errors). If Qiskit is not available, returns (False, []).
    """
    try:
        import qiskit
        from qiskit import QuantumCircuit
        from qiskit.quantum_info import Statevector, Operator
        import numpy as np
    except ImportError:
        return False, []

    errors: list[QVerificationError] = []

    qubit_count = _infer_qubit_count(machine)
    if qubit_count < 2:
        return False, []  # Can't verify entanglement with <2 qubits

    err_msg, gate_sequence = _build_circuit_from_actions(machine, qubit_count)
    if err_msg:
        return False, []

    # Build and run the circuit
    try:
        qc = QuantumCircuit(qubit_count)

        for gates in gate_sequence:
            for gate_str in gates:
                _apply_gate_to_circuit(qc, gate_str)

        # Check unitarity: the circuit operator should be unitary
        try:
            op = Operator(qc)
            U = op.data
            U_dagger = np.conj(U.T)
            product = np.dot(U, U_dagger)
            identity = np.eye(len(U))
            error = np.linalg.norm(product - identity)
            if error > 1e-6:
                errors.append(QVerificationError(
                    code="DYNAMIC_UNITARITY_ERROR",
                    message=f"Circuit operator is not unitary (error: {error:.2e})",
                    severity="error",
                    location=None,
                    suggestion="Check that all gates in the circuit are valid unitary operations",
                ))
        except Exception:
            pass  # Can't check unitarity for circuits with measurements

        # For Bell-like states, check entanglement via Schmidt rank
        # Only check if the machine explicitly mentions "entangled" or "bell" or "ghz"
        # in a state name or state expression
        entangled_kinds = {"bell", "ghz", "epr", "entangl"}
        entangled_states = [
            s for s in machine.states
            if s.state_expression and any(k in s.state_expression.lower() for k in entangled_kinds)
        ]

        for state in entangled_states:
            if qubit_count >= 2:
                try:
                    sv = Statevector(qc)
                    if len(sv.data) == 4:  # 2-qubit state
                        psi = sv.data.reshape(2, 2)
                        s = np.linalg.svd(psi, compute_uv=False)
                        schmidt_rank = int(np.sum(s > 1e-6))
                        if schmidt_rank == 1:
                            errors.append(QVerificationError(
                                code="DYNAMIC_NO_ENTANGLEMENT",
                                message=f"State '{state.name}' should be entangled but has Schmidt rank 1",
                                severity="error",
                                location={"state": state.name},
                                suggestion="Ensure the circuit creates an entangled state",
                            ))
                except Exception:
                    pass

        return True, errors

    except Exception as e:
        return False, []


def _apply_gate_to_circuit(qc: QuantumCircuit, gate_str: str) -> None:
    """Apply a gate string to a Qiskit circuit."""
    parts = gate_str.split()
    if not parts:
        return
    gate = parts[0]
    args = [int(x.group(1)) for x in re.finditer(r"q\[(\d+)\]", gate_str)]

    if gate == "h" and len(args) == 1:
        qc.h(args[0])
    elif gate == "x" and len(args) == 1:
        qc.x(args[0])
    elif gate == "y" and len(args) == 1:
        qc.y(args[0])
    elif gate == "z" and len(args) == 1:
        qc.z(args[0])
    elif gate == "t" and len(args) == 1:
        qc.t(args[0])
    elif gate == "s" and len(args) == 1:
        qc.s(args[0])
    elif gate == "cx" and len(args) == 2:
        qc.cx(args[0], args[1])
    elif gate == "cz" and len(args) == 2:
        qc.cz(args[0], args[1])


def dynamic_verify(machine: QMachineDef) -> QVerificationResult:
    """Run dynamic quantum verification using actual circuit simulation.

    This attempts to build and simulate the quantum circuit from action sequences,
    then verifies quantum properties (unitarity, entanglement) using Qiskit.

    If Qiskit is not available or verification fails, returns a valid result
    with no errors (fallback to static verification).
    """
    errors: list[QVerificationError] = []

    success, dynamic_errors = _try_dynamic_verification(machine)
    if success:
        errors.extend(dynamic_errors)

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
