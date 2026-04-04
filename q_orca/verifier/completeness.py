"""Q-Orca completeness verification — (state, event) coverage."""

from q_orca.ast import QMachineDef
from q_orca.verifier.types import QVerificationError, QVerificationResult
from q_orca.verifier.structural import analyze_machine


def has_quantum_preparation_path(machine: QMachineDef) -> bool:
    has_measure = any(
        "measure" in e.name.lower() or "collapse" in e.name.lower()
        for e in machine.events
    )
    if not has_measure:
        return False

    analysis = analyze_machine(machine)
    single_path = 0
    for state in machine.states:
        if state.is_final:
            continue
        info = analysis.state_map.get(state.name)
        if info and len(info.outgoing) == 1:
            single_path += 1

    non_final = len([s for s in machine.states if not s.is_final])
    return non_final > 0 and single_path / non_final > 0.5


def check_completeness(machine: QMachineDef) -> QVerificationResult:
    analysis = analyze_machine(machine)
    errors: list[QVerificationError] = []

    # Build (state, event) -> transitions map
    transition_map: dict = {}
    for t in machine.transitions:
        key = f"{t.source}+{t.event}"
        if key not in transition_map:
            transition_map[key] = []
        transition_map[key].append(t)

    is_quantum_path = has_quantum_preparation_path(machine)

    event_index = {e.name: i for i, e in enumerate(machine.events)}

    state_first_event_idx: dict = {}
    for state in machine.states:
        if state.is_final:
            state_first_event_idx[state.name] = float("inf")
            continue
        min_idx = float("inf")
        for event in machine.events:
            key = f"{state.name}+{event.name}"
            if key in transition_map:
                idx = event_index[event.name]
                if idx < min_idx:
                    min_idx = idx
        state_first_event_idx[state.name] = min_idx if min_idx != float("inf") else 0

    for state in machine.states:
        if state.is_final:
            continue

        first_event_idx = state_first_event_idx[state.name]

        for event in machine.events:
            key = f"{state.name}+{event.name}"
            if key not in transition_map:
                event_idx = event_index[event.name]
                if is_quantum_path and event_idx != first_event_idx:
                    continue
                errors.append(QVerificationError(
                    code="INCOMPLETE_EVENT_HANDLING",
                    message=f"State '{state.name}' does not handle event '{event.name}'",
                    severity="error",
                    location={"state": state.name, "event": event.name},
                    suggestion=f"Add transition: {state.name} + {event.name} -> <target>",
                ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
