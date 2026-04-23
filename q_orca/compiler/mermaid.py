"""Q-Orca Mermaid compiler — compiles QMachineDef → Mermaid stateDiagram-v2."""

import re

from q_orca.ast import QMachineDef, QStateDef


def compile_to_mermaid(machine: QMachineDef) -> str:
    lines = []

    lines.append("stateDiagram-v2")
    lines.append("  direction LR")
    lines.append("")

    def sanitize(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_]", "_", name.strip("|").strip(">").strip("<")).strip("_") or "unnamed"

    def state_id(s: QStateDef) -> str:
        return sanitize(s.name)

    # Add state descriptions
    for state in machine.states:
        label = state.name
        if state.state_expression:
            label += f" = {state.state_expression}"
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
        lines.append(f"  {sanitize(t.source)} --> {sanitize(t.target)} : {label}")

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
