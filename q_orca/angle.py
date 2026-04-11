"""Shared symbolic angle evaluator for Q-Orca parsers."""

import math
import re


def evaluate_angle(text: str) -> float:
    """Evaluate a symbolic angle expression to a float.

    Accepted forms (with optional leading minus):
      - decimal literal: 1.5708, -0.5
      - pi
      - pi/<int>: pi/4
      - <int>*pi or <int>pi: 2*pi, 2pi
      - <int>*pi/<int>: 3*pi/4

    Raises ValueError for anything else (e.g. bare identifiers).
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

    raise ValueError(
        f"Unrecognized angle expression {text!r}. "
        "Supported forms: decimal, pi, pi/<int>, <int>*pi, <int>*pi/<int>."
    )
