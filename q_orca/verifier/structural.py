"""Q-Orca structural verification — reachability, deadlock, orphan analysis."""

from typing import Optional

from q_orca.ast import QMachineDef, QStateDef
from q_orca.verifier.types import (
    QVerificationError, QVerificationResult, QStateInfo, QMachineAnalysis,
)


def analyze_machine(machine: QMachineDef) -> QMachineAnalysis:
    state_map: dict[str, QStateInfo] = {}
    final_states: list[QStateDef] = []
    initial_state: Optional[QStateDef] = None

    for state in machine.states:
        state_map[state.name] = QStateInfo(state=state)
        if state.is_final:
            final_states.append(state)
        if state.is_initial:
            initial_state = state

    for transition in machine.transitions:
        source_info = state_map.get(transition.source)
        target_info = state_map.get(transition.target)
        if source_info:
            source_info.outgoing.append(transition)
            source_info.events_handled.add(transition.event)
        if target_info:
            target_info.incoming.append(transition)

    used_events = set()
    used_actions = set()
    for t in machine.transitions:
        used_events.add(t.event)
        if t.action:
            used_actions.add(t.action)
    for s in machine.states:
        if s.on_entry:
            used_actions.add(s.on_entry)
        if s.on_exit:
            used_actions.add(s.on_exit)

    orphan_events = [e.name for e in machine.events if e.name not in used_events]
    orphan_actions = [a.name for a in machine.actions if a.name not in used_actions]

    used_effect_types = {a.effect_type for a in machine.actions if a.has_effect and a.effect_type}
    orphan_effects = [e.name for e in machine.effects if e.name not in used_effect_types]

    return QMachineAnalysis(
        machine=machine,
        state_map=state_map,
        initial_state=initial_state,
        final_states=final_states,
        orphan_events=orphan_events,
        orphan_actions=orphan_actions,
        orphan_effects=orphan_effects,
    )


def check_structural(machine: QMachineDef) -> QVerificationResult:
    analysis = analyze_machine(machine)
    errors: list[QVerificationError] = []

    # Must have an initial state
    if not analysis.initial_state:
        errors.append(QVerificationError(
            code="NO_INITIAL_STATE",
            message="Machine has no initial state",
            severity="error",
            suggestion="Mark one state with [initial] or make it the first ## state heading",
        ))
        return QVerificationResult(valid=False, errors=errors)

    # All states must be declared
    state_names = {s.name for s in machine.states}
    for t in machine.transitions:
        if t.source not in state_names:
            errors.append(QVerificationError(
                code="UNDECLARED_STATE",
                message=f"Transition references undeclared source state '{t.source}'",
                severity="error",
                location={"state": t.source},
                suggestion=f"Add: ## state {t.source}",
            ))
        if t.target not in state_names:
            errors.append(QVerificationError(
                code="UNDECLARED_STATE",
                message=f"Transition references undeclared target state '{t.target}'",
                severity="error",
                location={"state": t.target},
                suggestion=f"Add: ## state {t.target}",
            ))

    # Reachability: BFS from initial state
    reachable: set = set()
    queue = [analysis.initial_state.name]
    while queue:
        current = queue.pop(0)
        if current in reachable:
            continue
        reachable.add(current)
        info = analysis.state_map.get(current)
        if info:
            for t in info.outgoing:
                if t.target not in reachable:
                    queue.append(t.target)

    for state in machine.states:
        if state.name not in reachable:
            errors.append(QVerificationError(
                code="UNREACHABLE_STATE",
                message=f"State '{state.name}' is not reachable from the initial state",
                severity="error",
                location={"state": state.name},
                suggestion="Add a transition leading to this state, or remove it",
            ))

    # Deadlock: non-final states must have outgoing transitions
    for state in machine.states:
        if state.is_final:
            continue
        info = analysis.state_map.get(state.name)
        if info and len(info.outgoing) == 0:
            errors.append(QVerificationError(
                code="DEADLOCK",
                message=f"Non-final state '{state.name}' has no outgoing transitions",
                severity="error",
                location={"state": state.name},
                suggestion="Add transitions from this state or mark it as final",
            ))

    # Orphan warnings
    for e in analysis.orphan_events:
        errors.append(QVerificationError(
            code="ORPHAN_EVENT",
            message=f"Event '{e}' is declared but never used in any transition",
            severity="warning",
            location={"event": e},
        ))
    for a in analysis.orphan_actions:
        errors.append(QVerificationError(
            code="ORPHAN_ACTION",
            message=f"Action '{a}' is declared but never referenced",
            severity="warning",
            location={"action": a},
        ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
