"""Q-Orca Mermaid compiler — compiles QMachineDef → Mermaid stateDiagram-v2."""

import re
from typing import Optional

from q_orca.ast import QMachineDef, QOrcaFile, QStateDef
from q_orca.compiler.util import format_assertion_expr
from q_orca.compiler.loops import analyze_loops, LoopBoundError


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name.strip("|").strip(">").strip("<")).strip("_") or "unnamed"


def compile_to_mermaid(
    machine: QMachineDef, file: Optional[QOrcaFile] = None, import_graph=None
) -> str:
    lines = []

    lines.append("stateDiagram-v2")
    lines.append("  direction LR")
    lines.append("")

    sanitize = _sanitize

    def state_id(s: QStateDef) -> str:
        return sanitize(s.name)

    # Bounded-loop annotations: label the loop entry state and its back-edge
    # (×N for fixed, condensed `until …` predicate for adaptive) rather than
    # rendering an unrolled linear chain. Fall back to the unevaluated bound
    # expression if a fixed bound can't be resolved at render time.
    try:
        loops = analyze_loops(machine, evaluate=True)
    except LoopBoundError:
        loops = analyze_loops(machine, evaluate=False)

    # Add state descriptions. Assertions are appended to the description text
    # only. Invoke states are labeled `invoke: <Child>` (and their child is
    # rendered as a nested composite state below when the file is available).
    for state in machine.states:
        if state.invoke is not None:
            label = f"invoke: {state.invoke.child_name}"
        else:
            label = state.name
            if state.state_expression:
                label += f" = {state.state_expression}"
        if state.assertions:
            summary = "; ".join(format_assertion_expr(a, "qs") for a in state.assertions)
            label += f" — assert: {summary}"
        if state.name in loops:
            label += f" ⟲ {loops[state.name].label}"
        lines.append(f"  {sanitize(state.name)} : {label}")
    lines.append("")

    # Initial state transition
    initial = next((s for s in machine.states if s.is_initial), None)
    if initial:
        lines.append(f"  [*] --> {state_id(initial)}")

    # Final states
    for state in machine.states:
        if state.is_final:
            lines.append(f"  {state_id(state)} --> [*]")
    lines.append("")

    # Transitions
    for t in machine.transitions:
        label = t.event
        if t.guard:
            label += f" [{'!' if t.guard.negated else ''}{t.guard.name}]"
        if t.action:
            # Parametric call sites carry the source-form Action cell text
            # (`query_concept(3)`) on `action_label`; bare-name refs use
            # `action` directly.
            label += f" / {t.action_label or t.action}"
        if t.loop_back:
            info = next((i for i in loops.values() if t.source in i.body_states), None)
            if info is not None:
                label += f" ⟲{info.label}"
        lines.append(f"  {sanitize(t.source)} --> {sanitize(t.target)} : {label}")

    # Nested composite blocks for each resolved invoked child machine (same-file
    # or imported), so the composed diagram is self-contained. Imported children
    # carry the import path so the diagram shows where they came from.
    by_name = {m.name: m for m in file.machines} if file is not None else {}
    rendered: set[str] = set()
    for state in machine.states:
        if state.invoke is None:
            continue
        alias = state.invoke.child_name
        child = by_name.get(alias)
        import_path = None
        if child is None and import_graph is not None:
            child = import_graph.lookup_machine(alias)
            sources = import_graph.alias_sources.get(alias) if child is not None else None
            import_path = sources[0] if sources else None
        if child is None or alias in rendered:
            continue
        rendered.add(alias)
        lines.append("")
        if import_path is not None:
            lines.append(f"  %% {alias} imported from {import_path}")
        lines.append(f"  state {sanitize(alias)} {{")
        for cs in child.states:
            lines.append(f"    {sanitize(alias)}_{sanitize(cs.name)} : {cs.name}")
        for ct in child.transitions:
            lines.append(
                f"    {sanitize(alias)}_{sanitize(ct.source)} --> "
                f"{sanitize(alias)}_{sanitize(ct.target)} : {ct.event}"
            )
        lines.append("  }")

    # Verification rules note
    if machine.verification_rules:
        first = initial or machine.states[0]
        lines.append("")
        lines.append(f"  note right of {state_id(first)}")
        lines.append("    Verification Rules:")
        for rule in machine.verification_rules:
            lines.append(f"    - {rule.kind}: {rule.description}")
        lines.append("  end note")

    return "\n".join(lines)


def compile_import_graph_to_mermaid(import_graph, root_label: str = "root") -> str:
    """Render a `ResolvedImportGraph` as a Mermaid flowchart of files + edges.

    Used by `q-orca imports show`. Each file is a node (basename), each import is
    a directed edge. Diagnostics (cycles, missing files) are listed as comments.
    """
    import os

    lines = ["flowchart LR"]
    nodes: dict[str, str] = {}

    def node_id(path: str) -> str:
        if path not in nodes:
            nodes[path] = f"n{len(nodes)}"
        return nodes[path]

    edges = getattr(import_graph, "import_edges", []) or []
    for importer, imported in edges:
        a, b = node_id(importer), node_id(imported)
        lines.append(f"  {a}[{os.path.basename(importer)}] --> {b}[{os.path.basename(imported)}]")
    if not edges:
        lines.append(f"  {node_id(root_label)}[{root_label}]")
    for diag in getattr(import_graph, "errors", []) or []:
        lines.append(f"  %% {diag.code}: {diag.message}")
    return "\n".join(lines)
