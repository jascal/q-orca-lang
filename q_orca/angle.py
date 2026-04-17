"""Shared symbolic angle evaluator for Q-Orca parsers."""

import math
import re
from typing import Mapping, Optional


def evaluate_angle(
    text: str,
    context: Optional[Mapping[str, float]] = None,
) -> float:
    """Evaluate a symbolic angle expression to a float.

    Accepted literal forms (with optional leading minus):
      - decimal literal: 1.5708, -0.5
      - pi
      - pi/<int>: pi/4
      - <int>*pi or <int>pi: 2*pi, 2pi
      - <int>*pi/<int>: 3*pi/4

    When ``context`` is provided, identifiers found in it (mapping name → float)
    additionally resolve as:
      - bare identifier: gamma
      - <int>*name or <int>name: 2*gamma, 2gamma
      - name/<int>: gamma/2
      - name*pi or pi*name: gamma*pi, pi*gamma
    A leading minus is permitted on every form.

    Literal forms are tried first, so a context field literally named ``pi``
    cannot shadow the ``pi`` literal.

    Raises ValueError for anything else.
    """
    text = text.strip()
    sign = 1
    if text.startswith("-"):
        sign = -1
        text = text[1:].strip()

    # Decimal literal
    try:
        return sign * float(text)
    except ValueError:
        pass

    # pi/<int>
    m = re.fullmatch(r"pi\s*/\s*(\d+)", text)
    if m:
        return sign * math.pi / int(m.group(1))

    # <int>*pi/<int> or <int>pi/<int>
    m = re.fullmatch(r"(\d+)\s*\*?\s*pi\s*/\s*(\d+)", text)
    if m:
        return sign * int(m.group(1)) * math.pi / int(m.group(2))

    # <int>*pi or <int>pi
    m = re.fullmatch(r"(\d+)\s*\*?\s*pi", text)
    if m:
        return sign * int(m.group(1)) * math.pi

    # bare pi
    if text == "pi":
        return sign * math.pi

    # Context-reference forms (only when context is provided).
    if context:
        identifier_re = r"[A-Za-z_][A-Za-z_0-9]*"

        # name*pi or pi*name
        m = re.fullmatch(rf"({identifier_re})\s*\*\s*pi", text) or \
            re.fullmatch(rf"pi\s*\*\s*({identifier_re})", text)
        if m and m.group(1) in context:
            return sign * context[m.group(1)] * math.pi

        # <int>*name or <int>name
        m = re.fullmatch(rf"(\d+)\s*\*?\s*({identifier_re})", text)
        if m and m.group(2) in context:
            return sign * int(m.group(1)) * context[m.group(2)]

        # name/<int>
        m = re.fullmatch(rf"({identifier_re})\s*/\s*(\d+)", text)
        if m and m.group(1) in context:
            return sign * context[m.group(1)] / int(m.group(2))

        # bare identifier
        m = re.fullmatch(identifier_re, text)
        if m and text in context:
            return sign * context[text]

        # An identifier syntactically appears but isn't a recognized
        # numeric context field — produce a more informative error.
        bare = re.fullmatch(identifier_re, text)
        if bare:
            available = ", ".join(sorted(context)) or "(none)"
            raise ValueError(
                f"Unrecognized angle identifier {text!r}. "
                f"Numeric context fields available: {available}. "
                "Supported forms: decimal, pi, pi/<int>, <int>*pi, "
                "<int>*pi/<int>, <name>, -<name>, <int>*<name>, "
                "<name>/<int>, <name>*pi, pi*<name>."
            )

    raise ValueError(
        f"Unrecognized angle expression {text!r}. "
        "Supported forms: decimal, pi, pi/<int>, <int>*pi, <int>*pi/<int>"
        + (
            ", and context-field references: <name>, -<name>, "
            "<int>*<name>, <name>/<int>, <name>*pi, pi*<name>."
            if context
            else "."
        )
    )
