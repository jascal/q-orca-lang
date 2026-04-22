"""Runtime guard evaluator.

Interprets `QGuardExpression` AST nodes against a live Python context and
bit record. Shared by the iterative runtime (`run-context-updates`) and
future changes that need shot-to-shot guard evaluation.
"""

from typing import Any

from q_orca.ast import (
    QGuardAnd,
    QGuardCompare,
    QGuardExpression,
    QGuardFalse,
    QGuardFidelity,
    QGuardNot,
    QGuardOr,
    QGuardProbability,
    QGuardTrue,
    ValueRef,
    VariableRef,
)
from q_orca.runtime.types import QIterativeRuntimeError


def evaluate_guard(
    expr: QGuardExpression,
    ctx: dict,
    bits: dict,
) -> bool:
    """Evaluate a guard expression against the current context and bits.

    - `ctx` is a dict mapping context-field name to value.
    - `bits` is a dict mapping bit index (int) to 0/1.
    - Missing guard (None) and `QGuardTrue` both evaluate True.
    """
    if expr is None:
        return True

    if isinstance(expr, QGuardTrue):
        return True

    if isinstance(expr, QGuardFalse):
        return False

    if isinstance(expr, QGuardNot):
        return not evaluate_guard(expr.expr, ctx, bits)

    if isinstance(expr, QGuardAnd):
        return evaluate_guard(expr.left, ctx, bits) and evaluate_guard(
            expr.right, ctx, bits
        )

    if isinstance(expr, QGuardOr):
        return evaluate_guard(expr.left, ctx, bits) or evaluate_guard(
            expr.right, ctx, bits
        )

    if isinstance(expr, QGuardCompare):
        return _eval_compare(expr, ctx, bits)

    if isinstance(expr, QGuardProbability):
        return _eval_probability(expr, bits)

    if isinstance(expr, QGuardFidelity):
        raise QIterativeRuntimeError(
            "fidelity guards are not evaluable by the iterative runtime "
            "(they are a static verifier concern)"
        )

    raise QIterativeRuntimeError(f"unsupported guard expression: {type(expr).__name__}")


def _eval_compare(expr: QGuardCompare, ctx: dict, bits: dict) -> bool:
    left = _resolve_variable(expr.left, ctx, bits)
    right = _resolve_value(expr.right, ctx)
    return _apply_op(expr.op, left, right)


def _resolve_variable(ref: VariableRef, ctx: dict, bits: dict) -> Any:
    path = list(ref.path)
    if not path:
        raise QIterativeRuntimeError("empty variable reference in guard")

    # Drop a leading `ctx.` qualifier so `ctx.iteration` and `iteration`
    # both resolve against the context dict.
    if path[0] == "ctx":
        path = path[1:]
        if not path:
            raise QIterativeRuntimeError("bare `ctx` reference in guard")

    head, rest = path[0], path[1:]
    if head not in ctx:
        raise QIterativeRuntimeError(f"guard references unknown context field: {head!r}")

    value = ctx[head]
    for attr in rest:
        # List-element reference shaped as a numeric path segment —
        # the parser splits on `.` so `theta.0` comes through as such.
        if isinstance(value, (list, tuple)) and attr.isdigit():
            idx = int(attr)
            if idx >= len(value):
                raise QIterativeRuntimeError(
                    f"guard indexes {head}[{idx}] beyond length {len(value)}"
                )
            value = value[idx]
            continue
        raise QIterativeRuntimeError(
            f"guard reference {'.'.join(ref.path)} cannot resolve segment {attr!r}"
        )
    return value


def _resolve_value(ref: ValueRef, ctx: dict) -> Any:
    if ref is None:
        raise QIterativeRuntimeError("guard compare has no right-hand value")
    if ref.type == "number":
        return ref.value
    if ref.type == "boolean":
        return bool(ref.value)
    if ref.type == "null":
        return None
    if ref.type == "string":
        # A bare string on the RHS is either a literal or a context-field
        # reference. The parser uses string type for either; try context
        # first so `ctx.iteration < max_iter` works.
        if isinstance(ref.value, str) and ref.value in ctx:
            return ctx[ref.value]
        return ref.value
    raise QIterativeRuntimeError(f"unsupported value type in guard: {ref.type!r}")


_OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": lambda a, b: a < b,
    "gt": lambda a, b: a > b,
    "le": lambda a, b: a <= b,
    "ge": lambda a, b: a >= b,
    "approx": lambda a, b: abs(float(a) - float(b)) < 1e-9,
}


def _apply_op(op: str, left: Any, right: Any) -> bool:
    fn = _OPS.get(op)
    if fn is None:
        raise QIterativeRuntimeError(f"unsupported comparison op: {op!r}")
    try:
        return bool(fn(left, right))
    except TypeError as exc:
        raise QIterativeRuntimeError(
            f"guard op {op!r} got incompatible operands {left!r} vs {right!r}"
        ) from exc


def _eval_probability(expr: QGuardProbability, bits: dict) -> bool:
    """Per design §Guard evaluator, v1 reads probability guards from the
    most-recent observed measurement rather than analytic probability.

    A `prob('0') > 0.5` style guard becomes "the most recently measured
    bit is 0". Multi-bit bitstrings are rejected until the runtime
    tracks a per-qubit history.
    """
    if not bits:
        raise QIterativeRuntimeError(
            "probability guard evaluated before any measurement produced a bit"
        )
    outcome = expr.outcome
    if outcome is None or not outcome.bitstring:
        raise QIterativeRuntimeError("probability guard has no outcome bitstring")
    bitstring = outcome.bitstring
    if len(bitstring) != 1 or bitstring not in ("0", "1"):
        raise QIterativeRuntimeError(
            f"probability guard bitstring {bitstring!r} is not a single bit; "
            "multi-bit outcomes are not supported by the v1 iterative runtime"
        )
    # "Most recent" = highest bit index seen so far.
    last_idx = max(bits.keys())
    return bits[last_idx] == int(bitstring)
