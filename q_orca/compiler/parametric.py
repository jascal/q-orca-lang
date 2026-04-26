"""Q-Orca parametric action expansion — call-site substitution into templates."""

import re

from q_orca.ast import BoundArg, QActionSignature


# Only `qs[...]` subscripts get int-parameter substitution. Classical
# subscripts like `bits[0]` carry their own indexing semantics and are
# left untouched.
_SUBSCRIPT_RE = re.compile(r"(qs)\[([^\]]+)\]")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def _format_angle_literal(value: float) -> str:
    """Render an angle value as a decimal literal the angle evaluator accepts.

    Uses ``repr`` so round-trip precision is preserved (e.g. ``pi/4`` →
    ``0.7853981633974483``). ``repr(float)`` switches to scientific notation
    for magnitudes below ~1e-4 and above ~1e16; for the angle range
    rotation gates take in practice (≈ ±2π) this stays in decimal form.
    """
    return repr(float(value))


def expand_action_call(
    action: QActionSignature,
    bound_arguments: list[BoundArg] | None,
) -> str:
    """Return the action's effect string with parameter slots substituted.

    Integer-typed parameters replace identifier subscripts inside ``qs[...]``
    slots; angle-typed parameters replace bare-identifier references anywhere
    in the effect string outside a subscript position. The resulting string is
    a fully-literal effect that the standard gate-effect parser can consume.

    ``bound_arguments`` is assumed pre-validated against ``action.parameters``
    (arity, types) by the transitions-table resolver; this function does not
    re-check those invariants. A ``None`` or empty bound-arguments list is
    accepted as a convenience so callers can pass through bare-name
    transitions without branching.
    """
    effect = action.effect or ""
    if not effect:
        return ""

    if not action.parameters or not bound_arguments:
        return effect

    int_subs: dict[str, str] = {}
    angle_subs: dict[str, str] = {}
    for param, bound in zip(action.parameters, bound_arguments):
        if param.type == "int":
            int_subs[param.name] = str(int(bound.value))
        elif param.type == "angle":
            angle_subs[param.name] = _format_angle_literal(bound.value)

    # 1. Substitute identifier subscripts inside qs[...] slots.
    def _sub_subscript(m: re.Match[str]) -> str:
        head, inner = m.group(1), m.group(2)

        def _replace_ident(id_m: re.Match[str]) -> str:
            name = id_m.group(0)
            return int_subs.get(name, name)

        return f"{head}[{_IDENTIFIER_RE.sub(_replace_ident, inner)}]"

    effect = _SUBSCRIPT_RE.sub(_sub_subscript, effect)

    # 2. Substitute angle parameters outside subscript positions. Word-boundary
    #    replacement is safe now that subscripts contain only digits.
    for name, literal in angle_subs.items():
        effect = re.sub(rf"\b{re.escape(name)}\b", literal, effect)

    return effect
