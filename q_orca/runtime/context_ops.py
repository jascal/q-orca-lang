"""Runtime interpreter for `QEffectContextUpdate` AST nodes.

Each call returns a fresh context snapshot (the input snapshot is not
mutated). Shared by the iterative runtime and any future code that needs
to apply a context-update effect outside a simulator loop.
"""

from copy import deepcopy

from q_orca.ast import QContextMutation, QEffectContextUpdate
from q_orca.runtime.types import QIterativeRuntimeError


def apply(effect: QEffectContextUpdate, ctx: dict, bits: dict) -> dict:
    """Apply a context-update effect to `ctx` and return a new snapshot.

    - `ctx` is a dict mapping context-field name to value.
    - `bits` is a dict mapping bit index (int) to 0/1.
    - The bit condition (if present) picks the then/else branch; each
      mutation in the chosen branch is applied in declaration order.
    """
    if effect is None:
        return dict(ctx)

    branch = _choose_branch(effect, bits)
    snapshot = deepcopy(ctx)
    for mutation in branch:
        _apply_mutation(mutation, snapshot)
    return snapshot


def _choose_branch(effect: QEffectContextUpdate, bits: dict) -> list:
    if effect.bit_idx is None:
        return effect.then_mutations
    if effect.bit_idx not in bits:
        raise QIterativeRuntimeError(
            f"context-update effect gated on bits[{effect.bit_idx}] but no "
            f"measurement has populated that bit"
        )
    return (
        effect.then_mutations
        if bits[effect.bit_idx] == effect.bit_value
        else effect.else_mutations
    )


def _apply_mutation(mutation: QContextMutation, snapshot: dict) -> None:
    field = mutation.target_field
    if field not in snapshot:
        raise QIterativeRuntimeError(
            f"context-update targets unknown field {field!r}"
        )
    rhs = _resolve_rhs(mutation, snapshot)
    current = snapshot[field]

    if mutation.target_idx is None:
        snapshot[field] = _combine(mutation.op, current, rhs, field=field)
        return

    # List-element mutation.
    if not isinstance(current, list):
        raise QIterativeRuntimeError(
            f"context-update indexes {field}[{mutation.target_idx}] but "
            f"{field!r} is not a list (got {type(current).__name__})"
        )
    idx = mutation.target_idx
    if idx >= len(current):
        raise QIterativeRuntimeError(
            f"context-update indexes {field}[{idx}] beyond length {len(current)}"
        )
    current[idx] = _combine(mutation.op, current[idx], rhs, field=f"{field}[{idx}]")


def _resolve_rhs(mutation: QContextMutation, snapshot: dict):
    if mutation.rhs_literal is not None:
        return mutation.rhs_literal
    if mutation.rhs_field is not None:
        if mutation.rhs_field not in snapshot:
            raise QIterativeRuntimeError(
                f"context-update RHS references unknown field {mutation.rhs_field!r}"
            )
        return snapshot[mutation.rhs_field]
    raise QIterativeRuntimeError(
        "context-update mutation has neither literal nor field RHS"
    )


def _combine(op: str, current, rhs, *, field: str):
    if op == "=":
        return rhs
    if op in ("+=", "-="):
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            raise QIterativeRuntimeError(
                f"context-update op {op} on {field} requires a numeric target "
                f"(got {type(current).__name__})"
            )
        if not isinstance(rhs, (int, float)) or isinstance(rhs, bool):
            raise QIterativeRuntimeError(
                f"context-update op {op} on {field} requires a numeric RHS "
                f"(got {type(rhs).__name__})"
            )
        return current + rhs if op == "+=" else current - rhs
    raise QIterativeRuntimeError(f"unsupported context-update op: {op!r}")
