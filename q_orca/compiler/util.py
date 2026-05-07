"""Shared compiler helpers usable across compiler back-ends and analysis modules."""

from __future__ import annotations

import re

from q_orca.ast import QMachineDef, QTypeList, QTypeQubit, QTypeScalar


def infer_qubit_count(machine: QMachineDef) -> int:
    """Infer the qubit register width of a machine.

    Resolution order:
    1. Explicit ``qubits = [q0, q1, ...]`` list in context (length wins).
    2. ``n: int`` plus an ``ancilla: qubit`` field → ``n + 1``.
    3. Bitstring-style state names (``|00>``) and state expressions.
    4. Highest qubit index referenced in action gate targets / controls /
       effect-string subscripts (``+1``).
    5. Fallback to ``1``.
    """
    n_value = None
    has_ancilla = False
    qubits_list_length = None

    for field in machine.context:
        if field.name == "n" and isinstance(field.type, QTypeScalar) and field.type.kind == "int":
            try:
                n_value = int(field.default_value) if field.default_value else None
            except (ValueError, TypeError):
                n_value = None
        if field.name == "ancilla" and isinstance(field.type, QTypeQubit):
            has_ancilla = True
        if field.name == "qubits" and isinstance(field.type, QTypeList):
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
    for state in machine.states:
        if state.state_expression:
            for m in re.finditer(r"\|([01]+)>", state.state_expression):
                max_bits = max(max_bits, len(m.group(1)))
    for guard in machine.guards:
        if guard.expression.kind == "probability":
            max_bits = max(max_bits, len(guard.expression.outcome.bitstring))

    max_gate_idx = -1
    for action in machine.actions:
        if action.gate:
            for idx in action.gate.targets or []:
                max_gate_idx = max(max_gate_idx, idx)
            for idx in action.gate.controls or []:
                max_gate_idx = max(max_gate_idx, idx)
        if action.effect:
            for idx_match in re.finditer(r"\w+\[(\d+)\]", action.effect):
                max_gate_idx = max(max_gate_idx, int(idx_match.group(1)))
    if max_gate_idx >= 0:
        max_bits = max(max_bits, max_gate_idx + 1)

    return max_bits or 1
