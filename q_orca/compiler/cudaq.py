"""Q-Orca CUDA-Q compiler — compiles QMachineDef → CUDA-Q Python kernel script."""

from __future__ import annotations

import re
from typing import List, Optional

from q_orca.angle import evaluate_angle
from q_orca.ast import QMachineDef


def _infer_qubit_count(machine: QMachineDef) -> int:
    """Infer qubit count from machine context (mirrors qiskit compiler logic)."""
    n_value = None
    has_ancilla = False
    qubits_list_length = None

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

    max_gate_idx = -1
    for action in machine.actions:
        if action.effect:
            for idx_match in re.finditer(r"\w+\[(\d+)\]", action.effect):
                max_gate_idx = max(max_gate_idx, int(idx_match.group(1)))
    if max_gate_idx >= 0:
        max_bits = max(max_bits, max_gate_idx + 1)

    return max_bits or 1


def _parse_effect_to_cudaq_lines(effect_str: str, n_qubits: int) -> List[str]:
    """Parse a semicolon-separated effect string into CUDA-Q kernel body lines."""
    lines = []
    for part in effect_str.split(";"):
        part = part.strip()
        if not part:
            continue
        line = _parse_single_gate_to_cudaq(part, n_qubits)
        if line:
            lines.append(line)
    return lines


def _parse_single_gate_to_cudaq(effect_str: str, n_qubits: int) -> Optional[str]:
    """Map a single gate effect string to its CUDA-Q Python API call."""
    effect_str = effect_str.strip()

    # Hadamard(qs[N])
    m = re.search(r"Hadamard\(\s*\w+\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        return f"    cudaq.h(qvec[{m.group(1)}])"

    # CNOT(qs[ctrl], qs[tgt]) or CX(...)
    m = re.search(r"(?:CNOT|CX)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        return f"    cudaq.x.ctrl(qvec[{m.group(1)}], qvec[{m.group(2)}])"

    # CZ(qs[ctrl], qs[tgt])
    m = re.search(r"CZ\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        return f"    cudaq.z.ctrl(qvec[{m.group(1)}], qvec[{m.group(2)}])"

    # CCX / CCNOT / Toffoli — two controls + one target
    m = re.search(
        r"(CCX|CCNOT|Toffoli)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        c0, c1, tgt = m.group(2), m.group(3), m.group(4)
        return f"    cudaq.x.ctrl(qvec[{c0}], qvec[{c1}], qvec[{tgt}])"

    # CCZ — two controls + one target
    m = re.search(
        r"CCZ\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        c0, c1, tgt = m.group(1), m.group(2), m.group(3)
        return f"    cudaq.z.ctrl(qvec[{c0}], qvec[{c1}], qvec[{tgt}])"

    # MCX / MCZ — variable arity (≥3 args), last argument is the target.
    m = re.search(
        r"(MCX|MCZ)\(\s*((?:\w+\[\d+\]\s*,\s*){2,}\w+\[\d+\])\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        kind = m.group(1).upper()
        indices = [int(x) for x in re.findall(r"\d+", m.group(2))]
        op = "x" if kind == "MCX" else "z"
        qvec_args = ", ".join(f"qvec[{i}]" for i in indices)
        return f"    cudaq.{op}.ctrl({qvec_args})"

    # SWAP(qs[a], qs[b])
    m = re.search(r"SWAP\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        return f"    cudaq.swap(qvec[{m.group(1)}], qvec[{m.group(2)}])"

    # X(qs[N])
    m = re.search(r"^X\(\s*\w+\[(\d+)\]\s*\)", effect_str)
    if m:
        return f"    cudaq.x(qvec[{m.group(1)}])"

    # Y(qs[N])
    m = re.search(r"^Y\(\s*\w+\[(\d+)\]\s*\)", effect_str)
    if m:
        return f"    cudaq.y(qvec[{m.group(1)}])"

    # Z(qs[N])
    m = re.search(r"^Z\(\s*\w+\[(\d+)\]\s*\)", effect_str)
    if m:
        return f"    cudaq.z(qvec[{m.group(1)}])"

    # Rx(qs[N], angle)
    m = re.search(r"Rx\(\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)", effect_str, re.IGNORECASE)
    if m:
        try:
            theta = evaluate_angle(m.group(2).strip())
        except ValueError:
            theta = 0.0
        return f"    cudaq.rx({theta}, qvec[{m.group(1)}])"

    # Ry(qs[N], angle)
    m = re.search(r"Ry\(\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)", effect_str, re.IGNORECASE)
    if m:
        try:
            theta = evaluate_angle(m.group(2).strip())
        except ValueError:
            theta = 0.0
        return f"    cudaq.ry({theta}, qvec[{m.group(1)}])"

    # Rz(qs[N], angle)
    m = re.search(r"Rz\(\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)", effect_str, re.IGNORECASE)
    if m:
        try:
            theta = evaluate_angle(m.group(2).strip())
        except ValueError:
            theta = 0.0
        return f"    cudaq.rz({theta}, qvec[{m.group(1)}])"

    # measure / mz
    m = re.search(r"measure\(\s*\w+\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        return f"    mz(qvec[{m.group(1)}])"

    return None


def _extract_gate_lines(machine: QMachineDef, n_qubits: int) -> List[str]:
    """Walk the machine BFS and collect CUDA-Q gate lines."""
    action_map = {a.name: a for a in machine.actions}
    initial = next((s for s in machine.states if s.is_initial), None)
    if not initial:
        return []

    visited: set = set()
    queue = [initial.name]
    lines: List[str] = []

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        outgoing = [t for t in machine.transitions if t.source == current]
        for t in outgoing:
            if t.action:
                action = action_map.get(t.action)
                if action and action.effect:
                    gate_lines = _parse_effect_to_cudaq_lines(action.effect, n_qubits)
                    lines.extend(gate_lines)

            is_measure = "measure" in t.event.lower() or "collapse" in t.event.lower()
            if not is_measure and t.target not in visited:
                queue.append(t.target)

    return lines


def compile_to_cudaq(machine: QMachineDef) -> str:
    """Compile a QMachineDef to a CUDA-Q Python kernel script.

    The output is a self-contained Python file with:
    - ``import cudaq``
    - A ``@cudaq.kernel`` decorated function
    - Gate operations mapped from the machine's action effects
    - A ``mz`` measurement at the end

    Returns the generated script as a string.
    """
    n_qubits = _infer_qubit_count(machine)
    gate_lines = _extract_gate_lines(machine, n_qubits)

    lines = [
        "# Generated by Q-Orca compiler (CUDA-Q target)",
        f"# Machine: {machine.name}",
        "",
        "import cudaq",
        "",
        "",
        "@cudaq.kernel",
        f"def {machine.name.lower().replace(' ', '_').replace('-', '_')}():",
        f"    qvec = cudaq.qvector({n_qubits})",
    ]

    if gate_lines:
        lines.extend(gate_lines)
    else:
        lines.append("    pass")

    lines += [
        "",
        "",
        "if __name__ == '__main__':",
        f"    counts = cudaq.sample({machine.name.lower().replace(' ', '_').replace('-', '_')})",
        "    print(counts)",
    ]

    return "\n".join(lines)
