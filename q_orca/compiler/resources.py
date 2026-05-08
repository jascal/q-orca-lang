"""Static resource estimation for compiled Q-Orca circuits.

`estimate_resources(machine)` builds the Qiskit circuit (reusing
`q_orca.compiler.qiskit.build_circuit_for_iteration`) and computes:

    gate_count       — un-transpiled circuit op count (incl. measurements).
    depth            — `transpile(qc, optimization_level=1).depth()`.
    cx_count         — count of `cx` after transpiling to `['u3', 'cx']`.
    t_count          — count of `t` + `tdg` after transpiling to
                       `['h', 's', 'cx', 't', 'tdg']`.
    logical_qubits   — declared qubit count from `## context`.

Results are memoized per machine (`id(machine)` key) so the verifier and
compiler entry points can call this freely without paying the Qiskit
transpile cost twice. A `weakref.finalize` callback evicts each entry
when its machine is garbage-collected, so the next allocation that
reuses that memory address cannot get a stale cache hit.
"""

import weakref
from collections import Counter
from typing import Union

from q_orca.ast import QMachineDef


_RESOURCE_CACHE: dict[int, dict[str, Union[int, str]]] = {}


def _count_basis_ops(qc, basis_gates: list[str]) -> Counter:
    """Count gates in `qc` after decomposing to `basis_gates`, descending
    into control-flow blocks when the top-level transpile rejects them.

    Qiskit ≥ 2.4's `BasisTranslator` raises `TranspilerError` on circuits
    containing `if_else` (or `while_loop`/`switch_case`/…) because no
    equivalence rule decomposes a control-flow op into the explicit basis.
    The fallback splits the circuit: flat instructions transpile together,
    and each control-flow op's body — itself a self-contained
    `QuantumCircuit` — transpiles separately and recursively. The
    control-flow op is counted by its own name (so a compound conditional
    that nests `if_else` inside `if_else` per
    `extend-conditional-gate-compound-bits` collapses to a single
    top-level `if_else` count, matching `count_ops()` semantics on
    qiskit 2.3.x).
    """
    from qiskit import transpile
    from qiskit.transpiler.exceptions import TranspilerError

    try:
        return Counter(
            transpile(qc, basis_gates=basis_gates, optimization_level=1).count_ops()
        )
    except TranspilerError:
        pass

    flat_qc = qc.copy_empty_like()
    cf_counts: Counter = Counter()
    for instr in qc.data:
        op = instr.operation
        if getattr(op, "blocks", None):
            cf_counts[op.name] += 1
            for block in op.blocks:
                cf_counts.update(_count_basis_ops(block, basis_gates))
        else:
            flat_qc.append(instr)

    flat_counts = Counter(
        transpile(flat_qc, basis_gates=basis_gates, optimization_level=1).count_ops()
    )
    return flat_counts + cf_counts


def estimate_resources(machine: QMachineDef) -> dict[str, Union[int, str]]:
    cached = _RESOURCE_CACHE.get(id(machine))
    if cached is not None:
        return cached

    from qiskit import transpile

    from q_orca.compiler.qiskit import build_circuit_for_iteration, _infer_qubit_count

    qc = build_circuit_for_iteration(machine, {}, list(machine.actions))

    gate_count = sum(qc.count_ops().values())
    depth = transpile(qc, optimization_level=1).depth()
    cx_count = _count_basis_ops(qc, ["u3", "cx"]).get("cx", 0)
    t_ops = _count_basis_ops(qc, ["h", "s", "cx", "t", "tdg"])
    t_count = t_ops.get("t", 0) + t_ops.get("tdg", 0)
    logical_qubits = _infer_qubit_count(machine)

    result: dict[str, Union[int, str]] = {
        "gate_count": gate_count,
        "depth": depth,
        "cx_count": cx_count,
        "t_count": t_count,
        "logical_qubits": logical_qubits,
    }
    machine_id = id(machine)
    _RESOURCE_CACHE[machine_id] = result
    weakref.finalize(machine, _RESOURCE_CACHE.pop, machine_id, None)
    return result


def clear_resource_cache() -> None:
    """Drop memoized estimates. Used by tests."""
    _RESOURCE_CACHE.clear()


_OP_SYMBOL = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}
_OP_CHECK = {
    "eq": lambda v, b: v == b,
    "ne": lambda v, b: v != b,
    "lt": lambda v, b: v < b,
    "le": lambda v, b: v <= b,
    "gt": lambda v, b: v > b,
    "ge": lambda v, b: v >= b,
}


def format_resource_report(
    machine: QMachineDef, resources: dict[str, Union[int, str]]
) -> str:
    """One-screen summary table: `metric : value [<= bound] [✓|✗]`.

    Bound and pass/fail are omitted when no resource invariant pins
    that metric. Metric order follows the machine's `## resources`
    declaration if present, else the canonical default order.
    """
    metrics = list(machine.resource_metrics) or [
        "gate_count", "depth", "cx_count", "t_count", "logical_qubits",
    ]
    bounds: dict[str, tuple[str, float]] = {
        inv.metric: (inv.op, inv.value)
        for inv in machine.invariants
        if inv.kind == "resource" and inv.metric is not None and inv.value is not None
    }
    width = max((len(m) for m in metrics), default=0)
    lines: list[str] = []
    for m in metrics:
        v = resources.get(m, "?")
        line = f"  {m.ljust(width)} : {v}"
        if m in bounds:
            op, bound = bounds[m]
            line += f"  {_OP_SYMBOL.get(op, op)} {int(bound)}"
            if isinstance(v, int):
                ok = _OP_CHECK[op](v, bound)
                line += "  ✓" if ok else "  ✗"
        lines.append(line)
    return "\n".join(lines)


def compile_with_resources(
    machine: QMachineDef, options=None
) -> tuple[str, dict[str, Union[int, str]]]:
    """Compile the machine to a Qiskit script AND estimate resources.

    Returns `(script, resources)`. The same `QSimulationOptions` accepted
    by `compile_to_qiskit` is accepted here.
    """
    from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions

    if options is None:
        options = QSimulationOptions()
    script = compile_to_qiskit(machine, options)
    resources = estimate_resources(machine)
    return script, resources
