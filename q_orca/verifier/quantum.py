"""Q-Orca quantum verification — unitarity, no-cloning, entanglement, collapse completeness."""

import re

from q_orca.ast import QMachineDef, QuantumGate
from q_orca.compiler.parametric import expand_action_call
from q_orca.compiler.qiskit import _parse_effect_string
from q_orca.verifier.types import QVerificationError, QVerificationResult


KNOWN_UNITARY_GATES = {
    "H", "X", "Y", "Z", "CNOT", "CZ", "SWAP", "T", "S", "Rx", "Ry", "Rz", "CCNOT", "CSWAP",
    "CRx", "CRy", "CRz", "RXX", "RYY", "RZZ",
    "CCZ", "MCX", "MCZ",
}

ENTANGLED_PATTERNS = [
    re.compile(r"\(?\s*\|(\d+)>\s*[+\-]\s*\|(\d+)>\s*\)?\s*\/\s*√?2"),
    re.compile(r"bell", re.IGNORECASE),
    re.compile(r"ghz", re.IGNORECASE),
    re.compile(r"epr", re.IGNORECASE),
    re.compile(r"entangl", re.IGNORECASE),
]


def _has_rule(machine: QMachineDef, kind: str) -> bool:
    return any(
        r.kind == kind
        or r.kind == kind.replace("_", "-")
        or r.custom_name == kind
        or r.custom_name == kind.replace("_", "-")
        for r in machine.verification_rules
    )


def _count_qubits(machine: QMachineDef) -> int:
    # First: check context fields for explicit qubit declarations
    for field in machine.context:
        if hasattr(field.type, "element_type") and field.type.element_type == "qubit":
            # list<qubit> field — count from default value (e.g., [q0, q1] → 2 qubits)
            if field.default_value:
                indices = [int(m.group(1)) for m in re.finditer(r'q(\d+)', str(field.default_value))]
                if indices:
                    return max(indices) + 1
            # Fallback: count from state ket notation
            max_bits = 0
            for s in machine.states:
                m = re.search(r"\|([01]+)>", s.name)
                if m:
                    max_bits = max(max_bits, len(m.group(1)))
            if max_bits > 0:
                return max_bits
        if hasattr(field.type, "kind") and field.type.kind == "qubit":
            return 1
    # Fallback: count from state ket notation
    for s in machine.states:
        m = re.search(r"\|([01]+)>", s.name)
        if m:
            return len(m.group(1))
    return 0


def _check_gate_unitarity(
    gate: QuantumGate,
    qubit_count: int,
    label: str,
    location: dict,
    errors: list[QVerificationError],
) -> None:
    """Apply the unitarity checks to a single gate.

    ``label`` is a human-readable prefix for the error message (e.g.
    ``action 'apply_h'`` or ``call site query_concept(3) on transition
    ...``). ``location`` is attached to each emitted error unchanged.
    """
    if gate.kind not in KNOWN_UNITARY_GATES:
        if gate.kind == "custom":
            errors.append(QVerificationError(
                code="UNVERIFIED_UNITARITY",
                message=f"Custom gate '{gate.custom_name or 'unknown'}' in {label} cannot be statically verified as unitary",
                severity="warning",
                location=location,
                suggestion="Provide a unitary matrix definition or use a known gate",
            ))

    if qubit_count > 0:
        for idx in gate.targets:
            if idx >= qubit_count:
                errors.append(QVerificationError(
                    code="QUBIT_INDEX_OUT_OF_RANGE",
                    message=f"Gate '{gate.kind}' in {label} targets qubit {idx}, but machine only has {qubit_count} qubit(s)",
                    severity="error",
                    location=location,
                ))

        if gate.controls:
            for idx in gate.controls:
                if idx >= qubit_count:
                    errors.append(QVerificationError(
                        code="QUBIT_INDEX_OUT_OF_RANGE",
                        message=f"Gate '{gate.kind}' in {label} uses control qubit {idx}, but machine only has {qubit_count} qubit(s)",
                        severity="error",
                        location=location,
                    ))

    if gate.controls and gate.targets:
        overlap = [c for c in gate.controls if c in gate.targets]
        if overlap:
            errors.append(QVerificationError(
                code="CONTROL_TARGET_OVERLAP",
                message=f"Gate '{gate.kind}' in {label} has overlapping control and target qubits: {', '.join(str(x) for x in overlap)}",
                severity="error",
                location=location,
            ))


def check_unitarity(machine: QMachineDef) -> QVerificationResult:
    errors: list[QVerificationError] = []

    if not _has_rule(machine, "unitarity"):
        return QVerificationResult(valid=True, errors=errors)

    qubit_count = _count_qubits(machine)

    # Bare-name actions retain the existing per-action check — the action's
    # pre-parsed `gate` is a fully-literal `QuantumGate`, so one check covers
    # every transition that invokes it.
    for action in machine.actions:
        if action.parameters:
            continue
        if not action.gate:
            continue
        _check_gate_unitarity(
            action.gate,
            qubit_count,
            f"action '{action.name}'",
            {"action": action.name},
            errors,
        )

    # Parametric actions are verified per call site: expand the template
    # with the transition's bound arguments and run the same gate-level
    # checks on the resulting literal gate. N call sites = up to N errors,
    # which the design explicitly accepts so users see every affected row.
    action_map = {a.name: a for a in machine.actions}
    for t in machine.transitions:
        if t.bound_arguments is None:
            continue
        action = action_map.get(t.action or "")
        if action is None or not action.parameters:
            continue
        effect = expand_action_call(action, t.bound_arguments)
        gates = _parse_effect_string(effect) if effect else []
        site_label = t.action_label or t.action
        transition_ref = f"{t.source} --{t.event}--> {t.target}"
        for gate in gates:
            _check_gate_unitarity(
                gate,
                qubit_count,
                f"call site {site_label} on transition {transition_ref}",
                {"action": t.action, "transition": transition_ref, "call": site_label},
                errors,
            )

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )


def check_no_cloning(machine: QMachineDef) -> QVerificationResult:
    errors: list[QVerificationError] = []

    if not _has_rule(machine, "no_cloning"):
        return QVerificationResult(valid=True, errors=errors)

    for action in machine.actions:
        if not action.effect:
            continue

        effect_lower = action.effect.lower()
        if any(kw in effect_lower for kw in ["copy", "clone", "duplicate"]):
            errors.append(QVerificationError(
                code="NO_CLONING_VIOLATION",
                message=f"Action '{action.name}' appears to clone quantum state: '{action.effect}'",
                severity="error",
                location={"action": action.name},
                suggestion="Quantum states cannot be copied (no-cloning theorem). Use entanglement or teleportation instead.",
            ))
        elif "fanout" in effect_lower and "cnot" not in effect_lower:
            errors.append(QVerificationError(
                code="NO_CLONING_VIOLATION",
                message=f"Action '{action.name}' uses fanout which may violate no-cloning: '{action.effect}'",
                severity="warning",
                location={"action": action.name},
                suggestion="Ensure this is a controlled operation, not a state copy",
            ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )


def check_entanglement(machine: QMachineDef) -> QVerificationResult:
    errors: list[QVerificationError] = []

    if not _has_rule(machine, "entanglement"):
        return QVerificationResult(valid=True, errors=errors)

    entangled_states = [
        s for s in machine.states
        if s.state_expression and any(p.search(s.state_expression) for p in ENTANGLED_PATTERNS)
    ]

    if not entangled_states:
        has_entangled_name = any(
            any(p.search(s.name) for p in ENTANGLED_PATTERNS)
            for s in machine.states
        )
        if not has_entangled_name:
            errors.append(QVerificationError(
                code="NO_ENTANGLEMENT",
                message="Entanglement verification rule specified but no entangled states found",
                severity="warning",
                suggestion="Add a state with an entangled state expression, e.g., ## state |ψ> = (|00> + |11>)/√2",
            ))

    entangling_kinds = {"CNOT", "CZ", "SWAP", "CSWAP"}
    for state in entangled_states:
        incoming = [t for t in machine.transitions if t.target == state.name]
        has_entangling = False
        for t in incoming:
            if not t.action:
                continue
            action = next((a for a in machine.actions if a.name == t.action), None)
            if action and action.gate and action.gate.kind in entangling_kinds:
                has_entangling = True
                break

        if not has_entangling:
            errors.append(QVerificationError(
                code="ENTANGLEMENT_WITHOUT_GATE",
                message=f"State '{state.name}' is declared as entangled but no entangling gate (CNOT, CZ, etc.) leads to it",
                severity="warning",
                location={"state": state.name},
                suggestion="Add a transition with a CNOT or other entangling gate action",
            ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )


def check_collapse_completeness(machine: QMachineDef) -> QVerificationResult:
    errors: list[QVerificationError] = []

    if not _has_rule(machine, "completeness"):
        return QVerificationResult(valid=True, errors=errors)

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
            probabilities: list[float] = []
            for t in transitions:
                if not t.guard:
                    continue
                guard_def = next((g for g in machine.guards if g.name == t.guard.name), None)
                if guard_def and guard_def.expression.kind == "probability":
                    probabilities.append(guard_def.expression.outcome.probability)

            if probabilities:
                total = sum(probabilities)
                if abs(total - 1.0) > 0.01:
                    errors.append(QVerificationError(
                        code="INCOMPLETE_COLLAPSE",
                        message=f"Measurement branches from state '{source}' on event '{event.name}' have probabilities summing to {total:.4f}, expected 1.0",
                        severity="error",
                        location={"state": source, "event": event.name},
                        suggestion="Ensure all collapse outcomes are covered and probabilities sum to 1.0",
                    ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )


def check_mid_circuit_coherence(machine: QMachineDef) -> QVerificationResult:
    """Activated by 'mid_circuit_coherence' rule.

    Errors if any action applies a unitary gate to a qubit that was already
    measured mid-circuit by a prior action in the BFS gate sequence (without a
    reset in between).
    """
    errors: list[QVerificationError] = []

    if not _has_rule(machine, "mid_circuit_coherence"):
        return QVerificationResult(valid=True, errors=errors)

    action_map = {a.name: a for a in machine.actions}
    measured_qubits: set[int] = set()

    initial = next((s for s in machine.states if s.is_initial), None)
    if not initial:
        return QVerificationResult(valid=True, errors=errors)

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
            if t.action:
                action = action_map.get(t.action)
                if action:
                    if action.mid_circuit_measure is not None:
                        measured_qubits.add(action.mid_circuit_measure.qubit_idx)
                    elif action.gate is not None:
                        for idx in action.gate.targets:
                            if idx in measured_qubits:
                                errors.append(QVerificationError(
                                    code="MID_CIRCUIT_COHERENCE_VIOLATION",
                                    message=(
                                        f"Action '{action.name}' applies gate "
                                        f"'{action.gate.kind}' to qubit {idx} which "
                                        "was already measured mid-circuit without a reset"
                                    ),
                                    severity="error",
                                    location={"action": action.name},
                                    suggestion="Add a reset gate before reusing a measured qubit, or use a fresh qubit",
                                ))

            # Continue BFS through mid-circuit measurement transitions; stop only
            # at terminal (end-of-circuit) measurement events.
            t_action = action_map.get(t.action) if t.action else None
            is_mid_circuit = t_action is not None and t_action.mid_circuit_measure is not None
            is_terminal_measure = (
                ("measure" in t.event.lower() or "collapse" in t.event.lower())
                and not is_mid_circuit
            )
            if not is_terminal_measure and t.target not in visited:
                queue.append(t.target)

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )


def check_feedforward_completeness(machine: QMachineDef) -> QVerificationResult:
    """Activated by 'feedforward_completeness' rule.

    Warns if the machine has mid-circuit measurements but no conditional gate
    (feedforward) action uses the measured bit — i.e. the measurement result
    is discarded.
    """
    errors: list[QVerificationError] = []

    if not _has_rule(machine, "feedforward_completeness"):
        return QVerificationResult(valid=True, errors=errors)

    measured_bits: set[int] = set()
    feedforward_bits: set[int] = set()

    for action in machine.actions:
        if action.mid_circuit_measure is not None:
            measured_bits.add(action.mid_circuit_measure.bit_idx)
        if action.conditional_gate is not None:
            feedforward_bits.add(action.conditional_gate.bit_idx)

    unused = measured_bits - feedforward_bits
    for bit_idx in sorted(unused):
        errors.append(QVerificationError(
            code="FEEDFORWARD_UNUSED",
            message=(
                f"Classical bit {bit_idx} is written by a mid-circuit measurement "
                "but never read by a conditional gate (feedforward unused)"
            ),
            severity="warning",
            location={"bit_idx": bit_idx},
            suggestion="Add an 'if bits[M] == val: Gate(qs[K])' action that consumes this measurement result",
        ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )


def verify_quantum(machine: QMachineDef) -> QVerificationResult:
    results = [
        check_unitarity(machine),
        check_no_cloning(machine),
        check_entanglement(machine),
        check_collapse_completeness(machine),
        check_mid_circuit_coherence(machine),
        check_feedforward_completeness(machine),
    ]
    all_errors = [e for r in results for e in r.errors]
    return QVerificationResult(
        valid=not any(e.severity == "error" for e in all_errors),
        errors=all_errors,
    )
