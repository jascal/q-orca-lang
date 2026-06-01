"""Role-driven structural verifier rules (add-qubit-role-types).

Two rules that fire automatically (no `## verification rules` opt-in) based on
declared qubit roles:
- `ancilla_reset` — an `ancilla` qubit must be reset between successive
  mid-circuit measurements (`ANCILLA_NOT_RESET`).
- `syndrome_completeness` — a `syndrome` qubit must be measured on every cyclic
  path; uses a strongly-connected-component fallback until bounded-loop
  annotations land (`SYNDROME_NOT_MEASURED`).

(The third role rule, `communication_no_cloning`, escalates the existing
`check_no_cloning` in `quantum.py` rather than living here.)
"""

from __future__ import annotations

import re

from q_orca.ast import QMachineDef
from q_orca.roles import has_nondefault_roles, qubits_with_role
from q_orca.verifier.types import QVerificationError, QVerificationResult

_RESET_RE = re.compile(r"reset\s*\(\s*qs\[(\d+)\]", re.IGNORECASE)


def _reset_targets(action) -> set[int]:
    if not getattr(action, "effect", None):
        return set()
    return {int(m.group(1)) for m in _RESET_RE.finditer(action.effect)}


def _action_gate_targets(action) -> set[int]:
    targets: set[int] = set()
    g = getattr(action, "gate", None)
    if g is not None and getattr(g, "targets", None):
        targets.update(g.targets)
    if getattr(action, "mid_circuit_measure", None) is not None:
        targets.add(action.mid_circuit_measure.qubit_idx)
    return targets


def _measures(action) -> set[int]:
    if getattr(action, "mid_circuit_measure", None) is not None:
        return {action.mid_circuit_measure.qubit_idx}
    return set()


def _check_ancilla_reset(machine: QMachineDef, action_map: dict) -> list[QVerificationError]:
    ancillas = set(qubits_with_role(machine, "ancilla"))
    if not ancillas:
        return []
    initial = next((s for s in machine.states if s.is_initial), None)
    if not initial:
        return []

    errors: list[QVerificationError] = []
    measured: set[int] = set()  # ancilla qubits measured since their last reset
    reported: set[int] = set()
    visited: set[str] = set()
    queue = [initial.name]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for t in machine.transitions:
            if t.source != current:
                continue
            action = action_map.get(t.action) if t.action else None
            if action is not None:
                for k in _reset_targets(action):
                    measured.discard(k)
                for k in _measures(action):
                    if k in ancillas:
                        if k in measured and k not in reported:
                            errors.append(QVerificationError(
                                code="ANCILLA_NOT_RESET",
                                message=(
                                    f"ancilla qubit q{k} is measured again in state "
                                    f"{t.source!r} without an intervening reset"
                                ),
                                severity="error",
                                location={"action": getattr(action, "name", None), "state": t.source, "qubit": k},
                                suggestion=f"insert reset(qs[{k}]) before reusing ancilla q{k} after its measurement",
                            ))
                            reported.add(k)
                        measured.add(k)
            if t.target not in visited:
                queue.append(t.target)
    return errors


def _strongly_connected_components(nodes: list[str], edges: dict[str, list[str]]) -> list[set[str]]:
    """Tarjan's SCC (iterative)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[set[str]] = []
    counter = 0

    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            recursed = False
            succs = edges.get(node, [])
            if pi < len(succs):
                work[-1] = (node, pi + 1)
                nxt = succs[pi]
                if nxt not in index:
                    work.append((nxt, 0))
                    recursed = True
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if recursed:
                continue
            if pi >= len(succs):
                if low[node] == index[node]:
                    comp: set[str] = set()
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.add(w)
                        if w == node:
                            break
                    sccs.append(comp)
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
    return sccs


def _iteration_closing_edges(comp: set[str], entry_name: str, machine: QMachineDef) -> set[tuple[str, str]]:
    """The transitions that close one loop iteration (re-enter the body).

    Prefer explicitly-tagged `loop_back` edges; if none are tagged, fall back
    to in-body edges whose target is the loop entry (the implicit back-edge,
    valid when exactly one cycle exists).
    """
    tagged = {
        (t.source, t.target)
        for t in machine.transitions
        if t.source in comp and getattr(t, "loop_back", False)
    }
    if tagged:
        return tagged
    return {
        (t.source, t.target)
        for t in machine.transitions
        if t.source in comp and t.target == entry_name
    }


def _syndrome_measured_each_iteration(
    entry_name: str, comp: set[str], machine: QMachineDef, action_map: dict, k: int
) -> bool:
    """True if every path from the loop entry to an iteration-closing edge
    measures syndrome qubit `k` (exact per-iteration completeness)."""
    closing = _iteration_closing_edges(comp, entry_name, machine)
    if not closing:
        return True  # no back-edge to anchor an iteration; nothing to enforce

    def measures_on(t) -> bool:
        action = action_map.get(t.action) if t.action else None
        return action is not None and k in _measures(action)

    seen: set[tuple[str, bool]] = set()

    def dfs(state: str, measured: bool) -> bool:
        if (state, measured) in seen:
            return True
        seen.add((state, measured))
        for t in machine.transitions:
            if t.source != state or t.loop_done:
                continue  # loop_done is the exit edge, outside the iteration
            measured_next = measured or measures_on(t)
            if (t.source, t.target) in closing:
                if not measured_next:
                    return False  # closes an iteration without measuring k
                continue  # iteration closed on this branch; do not recurse past
            if t.target in comp and not dfs(t.target, measured_next):
                return False
        return True

    return dfs(entry_name, False)


def _check_syndrome_completeness(machine: QMachineDef, action_map: dict) -> list[QVerificationError]:
    syndromes = qubits_with_role(machine, "syndrome")
    if not syndromes:
        return []

    nodes = [s.name for s in machine.states]
    edges: dict[str, list[str]] = {n: [] for n in nodes}
    for t in machine.transitions:
        if t.source in edges:
            edges[t.source].append(t.target)
    sccs = _strongly_connected_components(nodes, edges)

    # Intra-SCC transitions (both endpoints in the same cyclic component).
    def has_self_loop(n: str) -> bool:
        return any(t.source == n and t.target == n for t in machine.transitions)

    errors: list[QVerificationError] = []
    for comp in sccs:
        is_cyclic = len(comp) > 1 or (len(comp) == 1 and has_self_loop(next(iter(comp))))
        if not is_cyclic:
            continue
        acted: set[int] = set()
        measured: set[int] = set()
        for t in machine.transitions:
            if t.source in comp and t.target in comp and t.action:
                action = action_map.get(t.action)
                if action is None:
                    continue
                acted |= _action_gate_targets(action)
                measured |= _measures(action)

        # A `[loop …]`-annotated body gets the exact per-iteration check;
        # an unannotated cycle keeps the conservative SCC fallback (a measure
        # anywhere in the component satisfies it).
        annotated = [
            s for s in machine.states
            if s.name in comp and getattr(s, "loop", None) is not None
        ]
        per_iteration = len(annotated) == 1
        entry_name = annotated[0].name if per_iteration else None

        for k in syndromes:
            if k not in acted:
                continue
            if per_iteration:
                if not _syndrome_measured_each_iteration(entry_name, comp, machine, action_map, k):
                    errors.append(QVerificationError(
                        code="SYNDROME_NOT_MEASURED",
                        message=(
                            f"syndrome qubit q{k} is acted on inside the "
                            f"[loop …] body entered at {entry_name!r} but is "
                            f"not measured on every iteration before loop_back"
                        ),
                        severity="error",
                        location={"qubit": k, "loop": entry_name, "cycle": sorted(comp)},
                        suggestion=f"measure the syndrome qubit q{k} on every loop iteration before loop_back",
                    ))
            elif k not in measured:
                errors.append(QVerificationError(
                    code="SYNDROME_NOT_MEASURED",
                    message=(
                        f"syndrome qubit q{k} is acted on inside a cyclic path "
                        f"({sorted(comp)}) but never measured within it"
                    ),
                    severity="error",
                    location={"qubit": k, "cycle": sorted(comp)},
                    suggestion=f"measure the syndrome qubit q{k} on every cycle before it repeats",
                ))
    return errors


def check_qubit_roles(machine: QMachineDef) -> QVerificationResult:
    """Run the automatic role-driven structural rules."""
    errors: list[QVerificationError] = []
    if not has_nondefault_roles(machine):
        return QVerificationResult(valid=True, errors=errors)
    action_map = {a.name: a for a in machine.actions}
    errors.extend(_check_ancilla_reset(machine, action_map))
    errors.extend(_check_syndrome_completeness(machine, action_map))
    return QVerificationResult(valid=not any(e.severity == "error" for e in errors), errors=errors)
