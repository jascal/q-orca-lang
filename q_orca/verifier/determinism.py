"""Q-Orca determinism verification — guard mutual exclusion."""

import re

from q_orca.ast import QMachineDef, QTransition, QGuardRef, QGuardDef
from q_orca.verifier.types import QVerificationError, QVerificationResult


def check_determinism(machine: QMachineDef) -> QVerificationResult:
    errors: list[QVerificationError] = []

    guard_def_map: dict[str, QGuardDef] = {g.name: g for g in machine.guards}

    # Build (state, event) -> transitions
    transition_map: dict[str, list[QTransition]] = {}
    for t in machine.transitions:
        key = f"{t.source}+{t.event}"
        if key not in transition_map:
            transition_map[key] = []
        transition_map[key].append(t)

    for key, transitions in transition_map.items():
        if len(transitions) <= 1:
            continue

        guards = [t.guard for t in transitions]
        unguarded_count = sum(1 for g in guards if g is None)

        if unguarded_count > 1:
            state_name, event_name = key.split("+")
            errors.append(QVerificationError(
                code="NON_DETERMINISTIC",
                message=f"State '{state_name}' has {unguarded_count} unguarded transitions for event '{event_name}'",
                severity="error",
                location={"state": state_name, "event": event_name},
                suggestion="Add guards to make transitions mutually exclusive",
            ))

        guarded = [t for t in transitions if t.guard]
        if len(guarded) > 1:
            guard_names = [f"{'!' if g.negated else ''}{g.name}" for g in [t.guard for t in guarded]]
            if not _guards_mutually_exclusive([t.guard for t in guarded], guard_def_map):
                state_name, event_name = key.split("+")
                errors.append(QVerificationError(
                    code="GUARD_OVERLAP",
                    message=f"State '{state_name}' guards for event '{event_name}' may overlap: {', '.join(guard_names)}",
                    severity="warning",
                    location={"state": state_name, "event": event_name},
                    suggestion="Ensure guards cover all possibilities without overlap",
                ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )


def _guards_mutually_exclusive(
    guard_refs: list[QGuardRef],
    guard_defs: dict[str, QGuardDef],
) -> bool:
    # Strategy 1: Name-based negation pairs (g and !g)
    for i, g1 in enumerate(guard_refs):
        for g2 in guard_refs[i + 1:]:
            if g1.name == g2.name and g1.negated != g2.negated:
                return True

    # Strategy 2: Syntactic mutual exclusion — same variable, different literals
    # e.g. "oracle == constant" and "oracle == balanced"
    _eq_pat = re.compile(r"^(\w[\w.]*)\s*==\s*(.+)$")
    for i, g1 in enumerate(guard_refs):
        m1 = _eq_pat.match(g1.name)
        if not m1:
            continue
        for g2 in guard_refs[i + 1:]:
            m2 = _eq_pat.match(g2.name)
            if m2 and m1.group(1) == m2.group(1) and m1.group(2).strip() != m2.group(2).strip():
                return True

    # Strategy 3: Named guards with QGuardCompare expressions that have same variable, different values
    for i, g1 in enumerate(guard_refs):
        def1 = guard_defs.get(g1.name)
        if not def1 or not hasattr(def1.expression, "kind") or def1.expression.kind != "compare":
            continue
        if not hasattr(def1.expression, "op") or def1.expression.op != "eq":
            continue
        for g2 in guard_refs[i + 1:]:
            def2 = guard_defs.get(g2.name)
            if not def2 or not hasattr(def2.expression, "kind") or def2.expression.kind != "compare":
                continue
            if not hasattr(def2.expression, "op") or def2.expression.op != "eq":
                continue
            e1, e2 = def1.expression, def2.expression
            if (hasattr(e1, "left") and hasattr(e2, "left") and
                    hasattr(e1.left, "path") and hasattr(e2.left, "path") and
                    e1.left.path == e2.left.path and
                    hasattr(e1, "right") and hasattr(e2, "right") and
                    e1.right.value != e2.right.value):
                return True

    # Strategy 4: Probability guards that sum to 1.0
    resolved = []
    for ref in guard_refs:
        def_ = guard_defs.get(ref.name)
        if not def_:
            continue
        resolved.append((def_.expression, ref.negated))

    prob_values: list[float] = []
    for expr, was_negated in resolved:
        if expr.kind == "probability":
            prob_values.append((1 - expr.outcome.probability) if was_negated else expr.outcome.probability)
        elif expr.kind == "fidelity":
            value = (1 - expr.value) if was_negated else expr.value
            prob_values.append(value)

    if len(prob_values) == len(guard_refs) and prob_values:
        if abs(sum(prob_values) - 1.0) < 0.001:
            return True

    return False
