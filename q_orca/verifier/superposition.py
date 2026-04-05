"""Q-Orca superposition leak verification — static analysis of superposition coherence."""

import re

from q_orca.ast import QMachineDef, QStateDef
from q_orca.verifier.types import QVerificationError, QVerificationResult
from q_orca.verifier.structural import analyze_machine


SUPERPOSITION_PATTERNS = [
    re.compile(r"\+"),          # Contains +
    re.compile(r"-"),            # Contains -
    re.compile(r"bell", re.IGNORECASE),
    re.compile(r"ghz", re.IGNORECASE),
    re.compile(r"epr", re.IGNORECASE),
    re.compile(r"entangl", re.IGNORECASE),
]

SUPERPOSITION_GATES = {"H", "Rx", "Ry", "Rz", "CNOT", "CZ", "SWAP", "CCNOT", "CSWAP"}
COLLAPSE_SENSITIVE_GATES = {"CNOT", "CZ", "SWAP", "CCNOT", "CSWAP"}


def _gate_kinds_in_effect(effect_str: str) -> set[str]:
    """Extract all gate kind names from an effect string."""
    if not effect_str:
        return set()
    kinds = set()
    for name in SUPERPOSITION_GATES:
        if name in effect_str:
            kinds.add(name)
    return kinds


def infer_superposition_states(machine: QMachineDef) -> list[QStateDef]:
    superposition_states: list[QStateDef] = []
    action_map = {a.name: a for a in machine.actions}

    for state in machine.states:
        if state.state_expression and any(p.search(state.state_expression) for p in SUPERPOSITION_PATTERNS):
            superposition_states.append(state)
            continue

        if any(p.search(state.name) for p in SUPERPOSITION_PATTERNS):
            superposition_states.append(state)
            continue

        incoming = [t for t in machine.transitions if t.target == state.name]
        for t in incoming:
            if t.action:
                action = action_map.get(t.action)
                if action:
                    # Check action.gate (single gate from signature)
                    if action.gate and action.gate.kind in SUPERPOSITION_GATES:
                        superposition_states.append(state)
                        break
                    # Check action.effect string for multi-gate effects
                    if action.effect and _gate_kinds_in_effect(action.effect):
                        superposition_states.append(state)
                        break

    return superposition_states


def check_superposition_leaks(machine: QMachineDef) -> QVerificationResult:
    errors: list[QVerificationError] = []
    superposition_states = {s.name for s in infer_superposition_states(machine)}

    if not superposition_states:
        return QVerificationResult(valid=True, errors=[])

    analysis = analyze_machine(machine)

    for state in machine.states:
        if state.name not in superposition_states:
            continue

        state_info = analysis.state_map.get(state.name)
        if not state_info:
            continue

        for t in state_info.outgoing:
            is_measure = "measure" in t.event.lower() or "collapse" in t.event.lower()

            if is_measure:
                if not t.guard:
                    target = next((s for s in machine.states if s.name == t.target), None)
                    is_final = target.is_final if target else False

                    if is_final:
                        errors.append(QVerificationError(
                            code="SUPERPOSITION_LEAK",
                            message=f"Measurement from superposition state '{state.name}' to final state will collapse superposition",
                            severity="warning",
                            location={"state": state.name, "event": t.event, "transition": f"{t.source} -> {t.target}"},
                            suggestion="This is expected behavior for collapse-based protocols",
                        ))
                    else:
                        errors.append(QVerificationError(
                            code="SUPERPOSITION_LEAK",
                            message=f"Unguarded measurement from non-final superposition state '{state.name}' may cause undefined behavior",
                            severity="warning",
                            location={"state": state.name, "event": t.event, "transition": f"{t.source} -> {t.target}"},
                            suggestion="Add probability guards or ensure measurement is the terminal step",
                        ))

            target_in_superposition = t.target in superposition_states
            if not target_in_superposition and not is_measure:
                action = next((a for a in machine.actions if a.name == t.action), None)
                if action and action.gate and action.gate.kind in COLLAPSE_SENSITIVE_GATES:
                    errors.append(QVerificationError(
                        code="SUPERPOSITION_LEAK",
                        message=f"Transition '{action.name}' from superposition state '{state.name}' to non-superposition state '{t.target}' may collapse superposition",
                        severity="warning",
                        location={"state": state.name, "event": t.event, "transition": t, "action": t.action},
                        suggestion="Ensure the gate preserves superposition or add proper decoherence handling",
                    ))

    # Check measurement branch coverage
    measure_events = [
        e for e in machine.events
        if "measure" in e.name.lower() or "collapse" in e.name.lower()
    ]

    for event in measure_events:
        transitions_by_source: dict = {}
        for t in machine.transitions:
            if t.event != event.name:
                continue
            if t.source not in transitions_by_source:
                transitions_by_source[t.source] = []
            transitions_by_source[t.source].append(t)

        for source, transitions in transitions_by_source.items():
            if source not in superposition_states:
                continue

            guarded = [t for t in transitions if t.guard]
            if not guarded and transitions:
                all_targets_final = all(
                    getattr(next((s for s in machine.states if s.name == t.target), None), "is_final", False)
                    for t in transitions
                )
                has_subsequent = any(
                    len([tr for tr in machine.transitions if tr.source == t.target]) > 0
                    for t in transitions
                )
                is_teleportation = not all_targets_final and has_subsequent

                errors.append(QVerificationError(
                    code="SUPERPOSITION_LEAK",
                    message=(
                        "Measurement from superposition state '"
                        + source
                        + "' to final states - intentional collapse"
                        if all_targets_final
                        else f"Measurement event '{event.name}' from non-final superposition state '{source}' has no probability guards"
                    ),
                    severity="warning",
                    location={"state": source, "event": event.name},
                    suggestion="This is expected for quantum communication protocols" if is_teleportation or all_targets_final else "Add probability guards or ensure measurement is the terminal step",
                ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
