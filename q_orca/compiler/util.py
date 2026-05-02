"""Shared compiler utilities reusable across backends and analyses.

Helpers in this module derive structural properties from a parsed
``QMachineDef`` (e.g., qubit register size) without importing any
specific backend (Qiskit, OpenQASM, CUDA-Q). Backend-specific
modules MAY re-export the public names here under their historical
underscored aliases for backward compatibility, but new callers
SHOULD import directly from this module.
"""

from __future__ import annotations

import re

from q_orca.ast import QMachineDef, QTypeList, QTypeQubit, QTypeScalar


def infer_qubit_count(machine: QMachineDef) -> int:
    """Return the qubit register size implied by ``machine``.

    Resolution order (first match wins):

    1. ``context.n: int`` plus a ``context.ancilla: qubit`` field —
       returns ``n + 1`` (the ``MCX``/Grover convention where ``n``
       is the count of control qubits and ``ancilla`` is the work
       qubit).
    2. ``context.qubits: list<qubit> = [q0, q1, ...]`` — returns the
       list length.
    3. The widest bitstring ket appearing in any state name, state
       expression, or probability guard outcome (``|001>`` → 3).
    4. The largest qubit subscript appearing in any action's gate
       targets/controls or effect string (``CNOT(qs[2], qs[3])`` → 4).

    Falls back to ``1`` if none of the above signals are present.
    """
    n_value = None
    has_ancilla = False
    qubits_list_length = None

    for field in machine.context:
        if (
            field.name == "n"
            and isinstance(field.type, QTypeScalar)
            and field.type.kind == "int"
        ):
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
