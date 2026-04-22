"""Q-Orca classical-context verification.

Two static checks on context-update actions:

1. Static typing — the LHS of every mutation must reference a declared
   context field of the right kind, and list-index LHSs must be within
   the field's default-value bounds. RHS field refs must also be
   declared numeric fields.

2. Feedforward completeness — any context-update effect that reads
   `bits[i]` in its condition must be preceded, on every reachable
   path from the initial state, by a transition that writes
   `bits[i]` (via `measure(qs[_]) -> bits[i]`).
"""

import re

from q_orca.ast import (
    QMachineDef,
    QActionSignature,
    QContextMutation,
    ContextField,
    QGuardAnd,
    QGuardCompare,
    QGuardNot,
    QGuardOr,
    QTypeScalar,
    QTypeList,
)
from q_orca.verifier.types import QVerificationError, QVerificationResult


_NUMERIC_SCALARS = {"int", "float"}


def _context_field_by_name(machine: QMachineDef, name: str) -> ContextField | None:
    for f in machine.context:
        if f.name == name:
            return f
    return None


def _list_default_length(default_value: str | None) -> int | None:
    if not default_value:
        return None
    inner = default_value.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1].strip()
    if not inner:
        return 0
    # Split on commas at the top level (defaults in this grammar are
    # flat numeric lists — no nested brackets to worry about).
    return len([p for p in inner.split(",") if p.strip()])


def _check_mutation_typing(
    mut: QContextMutation,
    machine: QMachineDef,
    action_name: str,
) -> list[QVerificationError]:
    errors: list[QVerificationError] = []

    field = _context_field_by_name(machine, mut.target_field)
    if field is None:
        errors.append(QVerificationError(
            code="UNDECLARED_CONTEXT_FIELD",
            message=(
                f"Action '{action_name}' mutates undeclared context field "
                f"'{mut.target_field}'"
            ),
            severity="error",
            location={"action": action_name, "field": mut.target_field},
            suggestion=f"Declare '{mut.target_field}' in the ## context table.",
        ))
    else:
        # Typing: scalar LHS must be `int`; list-element LHS must be `list<float>`.
        if mut.target_idx is None:
            if not (isinstance(field.type, QTypeScalar) and field.type.kind == "int"):
                errors.append(QVerificationError(
                    code="CONTEXT_FIELD_TYPE_MISMATCH",
                    message=(
                        f"Action '{action_name}': scalar context mutation "
                        f"requires an `int` field, but '{mut.target_field}' "
                        f"has a different type."
                    ),
                    severity="error",
                    location={"action": action_name, "field": mut.target_field},
                ))
        else:
            if not (
                isinstance(field.type, QTypeList)
                and field.type.element_type.strip() == "float"
            ):
                errors.append(QVerificationError(
                    code="CONTEXT_FIELD_TYPE_MISMATCH",
                    message=(
                        f"Action '{action_name}': indexed context mutation "
                        f"requires a `list<float>` field, but '{mut.target_field}' "
                        f"has a different type."
                    ),
                    severity="error",
                    location={"action": action_name, "field": mut.target_field},
                ))
            else:
                length = _list_default_length(field.default_value)
                if length is not None and mut.target_idx >= length:
                    errors.append(QVerificationError(
                        code="CONTEXT_INDEX_OUT_OF_RANGE",
                        message=(
                            f"Action '{action_name}': index {mut.target_idx} is "
                            f"outside the default-value length ({length}) of "
                            f"list field '{mut.target_field}'."
                        ),
                        severity="error",
                        location={"action": action_name, "field": mut.target_field},
                    ))

    # RHS field refs: must exist and be numeric scalar.
    if mut.rhs_field is not None:
        rhs = _context_field_by_name(machine, mut.rhs_field)
        if rhs is None:
            errors.append(QVerificationError(
                code="UNDECLARED_CONTEXT_FIELD",
                message=(
                    f"Action '{action_name}' references undeclared context "
                    f"field '{mut.rhs_field}' as a mutation RHS."
                ),
                severity="error",
                location={"action": action_name, "field": mut.rhs_field},
            ))
        elif not (isinstance(rhs.type, QTypeScalar) and rhs.type.kind in _NUMERIC_SCALARS):
            errors.append(QVerificationError(
                code="CONTEXT_FIELD_TYPE_MISMATCH",
                message=(
                    f"Action '{action_name}': RHS field '{mut.rhs_field}' must "
                    f"be an `int` or `float` scalar."
                ),
                severity="error",
                location={"action": action_name, "field": mut.rhs_field},
            ))

    return errors


def _action_writes_bit(action: QActionSignature, bit_idx: int) -> bool:
    """True if this action writes `bits[bit_idx]` via a measurement effect."""
    if action.mid_circuit_measure is not None and action.mid_circuit_measure.bit_idx == bit_idx:
        return True
    # Also honor any effect string that declares `measure(qs[_]) -> bits[i]`
    # — `mid_circuit_measure` should be set in this case, but we double-check
    # here to stay robust against parser changes.
    if action.effect:
        for m in re.finditer(
            r"measure\s*\(\s*\w+\[\d+\]\s*\)\s*->\s*bits\[(\d+)\]",
            action.effect,
            re.IGNORECASE,
        ):
            if int(m.group(1)) == bit_idx:
                return True
    return False


def _check_feedforward_completeness(
    machine: QMachineDef,
) -> list[QVerificationError]:
    """For each bit-gated context-update, confirm every path to its
    transition writes that bit first. Emit BIT_READ_BEFORE_WRITE on
    any path missing the write.
    """
    errors: list[QVerificationError] = []
    action_map = {a.name: a for a in machine.actions}

    initial = next((s for s in machine.states if s.is_initial), None)
    if initial is None:
        return errors  # structural stage will flag this.

    outgoing: dict[str, list] = {}
    for t in machine.transitions:
        outgoing.setdefault(t.source, []).append(t)

    def _transition_action(t) -> QActionSignature | None:
        return action_map.get(t.action) if t.action else None

    already_reported: set[tuple[str, int]] = set()

    def _enumerate_paths_to(target_state: str) -> list[list]:
        """Return every acyclic list-of-transitions from initial to target_state.

        The empty list represents the case where initial == target_state
        (i.e., the update fires on the first transition out of initial).
        """
        results: list[list] = []

        def dfs(state: str, visited_states: set, transitions_acc: list) -> None:
            if state == target_state:
                results.append(list(transitions_acc))
                # Don't return — the same state may be reachable through
                # multiple acyclic prefixes; but *on this branch* we stop
                # because continuing past would revisit.
                return
            for out in outgoing.get(state, []):
                if out.target in visited_states:
                    continue
                dfs(
                    out.target,
                    visited_states | {out.target},
                    transitions_acc + [out],
                )

        dfs(initial.name, {initial.name}, [])
        return results

    for t_target in machine.transitions:
        act = _transition_action(t_target)
        if act is None or act.context_update is None:
            continue
        cu = act.context_update
        if cu.bit_idx is None:
            continue
        bit_idx = cu.bit_idx

        paths = _enumerate_paths_to(t_target.source)
        violation = False
        if not paths:
            # The transition's source isn't reachable from initial; the
            # structural stage already flags unreachable states, so skip.
            continue

        for path_transitions in paths:
            writes_bit = any(
                _transition_action(tp) is not None
                and _action_writes_bit(_transition_action(tp), bit_idx)
                for tp in path_transitions
            )
            if not writes_bit:
                violation = True
                break

        if violation and (act.name, bit_idx) not in already_reported:
            errors.append(QVerificationError(
                code="BIT_READ_BEFORE_WRITE",
                message=(
                    f"Action '{act.name}' reads bits[{bit_idx}] in a "
                    f"context-update condition, but some path from the "
                    f"initial state reaches it without a prior "
                    f"measure(...) -> bits[{bit_idx}]."
                ),
                severity="error",
                location={"action": act.name, "bit": bit_idx},
                suggestion=(
                    f"Add a mid-circuit measurement writing bits[{bit_idx}] "
                    f"on every path leading to this action."
                ),
            ))
            already_reported.add((act.name, bit_idx))

    return errors


_BOUNDING_OPS = {"lt", "le", "gt", "ge"}


def _int_field_names(machine: QMachineDef) -> set[str]:
    out: set[str] = set()
    for f in machine.context:
        if isinstance(f.type, QTypeScalar) and f.type.kind == "int":
            out.add(f.name)
    return out


def _compare_uses_int_bound(
    expr: QGuardCompare, int_fields: set[str]
) -> bool:
    if expr.op not in _BOUNDING_OPS:
        return False
    left = expr.left
    if left is None or not left.path:
        return False
    # Path forms we accept: ["ctx", "field"] or ["field"]. Either way the
    # trailing segment is the field name.
    field = left.path[-1]
    return field in int_fields


def _guard_has_int_bound(expr, int_fields: set[str]) -> bool:
    if expr is None:
        return False
    if isinstance(expr, QGuardCompare):
        return _compare_uses_int_bound(expr, int_fields)
    if isinstance(expr, QGuardNot):
        return _guard_has_int_bound(expr.expr, int_fields)
    if isinstance(expr, (QGuardAnd, QGuardOr)):
        return (
            _guard_has_int_bound(expr.left, int_fields)
            or _guard_has_int_bound(expr.right, int_fields)
        )
    return False


def check_iterative_termination(
    machine: QMachineDef,
) -> list[QVerificationError]:
    """Warn when an iterative machine has no guard that could plausibly
    terminate its context-update loop.

    Conservative v1 heuristic: a machine is considered bounded if any
    declared guard (or transition-inline guard) contains a `<`, `<=`, `>`,
    or `>=` comparison whose LHS resolves to an int context field.
    """
    if not any(a.context_update is not None for a in machine.actions):
        return []

    int_fields = _int_field_names(machine)
    if not int_fields:
        return [_unbounded_warning(machine)]

    for gdef in machine.guards:
        if _guard_has_int_bound(gdef.expression, int_fields):
            return []

    return [_unbounded_warning(machine)]


def _unbounded_warning(machine: QMachineDef) -> QVerificationError:
    return QVerificationError(
        code="UNBOUNDED_CONTEXT_LOOP",
        message=(
            f"Machine '{machine.name}' has context-update actions but no "
            "bounding guard on an `int` context field (e.g., "
            "`ctx.iteration < max_iter`). The iterative runtime will rely "
            "on its iteration ceiling to terminate."
        ),
        severity="warning",
        location={"machine": machine.name},
        suggestion=(
            "Add a guard comparing an `int` context field against a literal "
            "or another bound (`<`, `<=`, `>`, `>=`) on at least one path "
            "to a [final] state."
        ),
    )


def check_classical_context(machine: QMachineDef) -> QVerificationResult:
    errors: list[QVerificationError] = []

    for action in machine.actions:
        cu = action.context_update
        if cu is None:
            continue
        for mut in list(cu.then_mutations) + list(cu.else_mutations):
            errors.extend(_check_mutation_typing(mut, machine, action.name))

    errors.extend(_check_feedforward_completeness(machine))
    errors.extend(check_iterative_termination(machine))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
