"""Shared gate-effect-string parser for Q-Orca.

Single source of truth for recognizing gate effect strings like
``Hadamard(qs[0])``, ``CRx(qs[0], qs[1], beta)``, or
``MCX(qs[0], qs[1], qs[2], qs[3])``. Consumed by:

- ``q_orca.parser.markdown_parser._parse_gate_from_effect`` (AST nodes)
- ``q_orca.compiler.qiskit._parse_single_gate`` (AST nodes, compiler path)
- ``q_orca.verifier.dynamic._parse_single_gate_to_dict`` (gate dicts)

Each call site adapts ``ParsedGate`` to its preferred shape. The parser
itself owns regex ordering and anchoring so that a single edit here
covers every downstream backend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional

from q_orca.angle import evaluate_angle


ARITY_ERROR_MARKER = "requires at least"


@dataclass(frozen=True)
class ParsedGate:
    """Backend-agnostic shape for a parsed gate effect.

    ``name`` uses the canonical AST spelling: mixed-case for rotations
    (``Rx``, ``Ry``, ``Rz``, ``CRx``, ``CRy``, ``CRz``), upper-case for
    Pauli-product rotations (``RXX``, ``RYY``, ``RZZ``) and Pauli/Clifford
    primitives (``H``, ``X``, ``Y``, ``Z``, ``S``, ``T``, ``CNOT``, ``CZ``,
    ``SWAP``, ``CCNOT``, ``CCZ``, ``CSWAP``, ``MCX``, ``MCZ``).
    """

    name: str
    targets: tuple[int, ...]
    controls: tuple[int, ...] = ()
    parameter: Optional[float] = None
    custom_name: Optional[str] = None


_TWO_QUBIT_PARAM_KIND_MAP = {
    "CRX": "CRx",
    "CRY": "CRy",
    "CRZ": "CRz",
    "RXX": "RXX",
    "RYY": "RYY",
    "RZZ": "RZZ",
}


def parse_single_gate(
    effect_str: str,
    angle_context: Optional[Mapping[str, float]] = None,
    errors: Optional[list[str]] = None,
    action_name: str = "",
) -> Optional[ParsedGate]:
    """Parse one gate from an effect string.

    Returns ``None`` if no pattern matches or the input is recognized but
    malformed (wrong arity, bad angle, wrong argument order). When
    ``errors`` is supplied, structured messages for the malformed cases
    are appended to it so the markdown parser can surface them.
    """
    if not effect_str:
        return None
    s = effect_str.strip()

    # Hadamard(qs[N]) — accept multi-index `Hadamard(qs[0 1 2])` for
    # parallel single-qubit Hadamard application (markdown-parser legacy).
    m = re.match(
        r"^Hadamard\(\s*\w+\[(\d+(?:\s+\d+)*)\]\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        indices = tuple(int(x) for x in m.group(1).split())
        return ParsedGate(name="H", targets=indices)

    # CCX / CCNOT / Toffoli / CCZ — exactly two controls + one target.
    m = re.match(
        r"^(CCX|CCNOT|Toffoli|CCZ)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).upper()
        c0, c1, tgt = int(m.group(2)), int(m.group(3)), int(m.group(4))
        kind = "CCZ" if raw == "CCZ" else "CCNOT"
        return ParsedGate(name=kind, targets=(tgt,), controls=(c0, c1))

    # MCX / MCZ — variable arity (≥3 args), last argument is the target.
    m = re.match(
        r"^(MCX|MCZ)\(\s*((?:\w+\[\d+\]\s*,\s*){2,}\w+\[\d+\])\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        kind = m.group(1).upper()
        indices = [int(x) for x in re.findall(r"\d+", m.group(2))]
        return ParsedGate(name=kind, targets=(indices[-1],), controls=tuple(indices[:-1]))

    # MCX/MCZ with the wrong arity — promote to a structured parser error.
    m_bad_mc = re.match(
        r"^(MCX|MCZ)\(\s*((?:\w+\[\d+\](?:\s*,\s*)?)*)\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m_bad_mc:
        kind = m_bad_mc.group(1).upper()
        n_args = len(re.findall(r"\w+\[\d+\]", m_bad_mc.group(2)))
        if errors is not None:
            prefix = f"action {action_name!r}: " if action_name else ""
            alt = "CCX" if kind == "MCX" else "CCZ"
            errors.append(
                f"{prefix}{kind} {ARITY_ERROR_MARKER} 3 qubit arguments "
                f"(≥2 controls + 1 target), got {n_args}. Use {alt} for the 2-control case."
            )
        return None

    # CSWAP / Fredkin — exactly 1 control + 2 swap targets.
    m = re.match(
        r"^CSWAP\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        ctrl, t1, t2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return ParsedGate(name="CSWAP", targets=(t1, t2), controls=(ctrl,))

    # CSWAP with wrong arity — structured parser error.
    m_bad_cswap = re.match(
        r"^CSWAP\(\s*((?:\w+\[\d+\](?:\s*,\s*)?)*)\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m_bad_cswap:
        n_args = len(re.findall(r"\w+\[\d+\]", m_bad_cswap.group(1)))
        if errors is not None:
            prefix = f"action {action_name!r}: " if action_name else ""
            errors.append(
                f"{prefix}CSWAP {ARITY_ERROR_MARKER} 3 qubit arguments "
                f"(1 control + 2 swap targets), got {n_args}."
            )
        return None

    # Two-qubit parameterized: CRx/CRy/CRz/RXX/RYY/RZZ. Anchored and
    # placed before the single-qubit rotation branch so `CRx(...)` cannot
    # be substring-matched as `Rx(...)`.
    m = re.match(
        r"^(CRx|CRy|CRz|RXX|RYY|RZZ)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).upper()
        kind = _TWO_QUBIT_PARAM_KIND_MAP[raw]
        i = int(m.group(2))
        j = int(m.group(3))
        angle_str = m.group(4).strip()
        try:
            theta = evaluate_angle(angle_str, angle_context)
        except ValueError as exc:
            if errors is not None:
                prefix = f"action {action_name!r}: " if action_name else ""
                errors.append(
                    f"{prefix}two-qubit gate {kind} has unrecognized angle {angle_str!r}. {exc}"
                )
            return None
        if kind in ("CRx", "CRy", "CRz"):
            return ParsedGate(name=kind, targets=(j,), controls=(i,), parameter=theta)
        return ParsedGate(name=kind, targets=(i, j), parameter=theta)

    # CNOT / CX — controls=[c], targets=[t].
    m = re.match(
        r"^(?:CNOT|CX)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        return ParsedGate(name="CNOT", targets=(int(m.group(2)),), controls=(int(m.group(1)),))

    # CZ — controls=[c], targets=[t].
    m = re.match(
        r"^CZ\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        return ParsedGate(name="CZ", targets=(int(m.group(2)),), controls=(int(m.group(1)),))

    # SWAP — symmetric, targets=[a, b].
    m = re.match(
        r"^SWAP\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        return ParsedGate(name="SWAP", targets=(int(m.group(1)), int(m.group(2))))

    # Single-qubit rotation: Rx/Ry/Rz(qs[N], <angle>). Anchored.
    m = re.match(
        r"^R([XYZ])\(\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m:
        axis = m.group(1).lower()
        idx = int(m.group(2))
        angle_str = m.group(3).strip()
        kind = f"R{axis}"
        try:
            theta = evaluate_angle(angle_str, angle_context)
        except ValueError as exc:
            if errors is not None:
                prefix = f"action {action_name!r}: " if action_name else ""
                errors.append(
                    f"{prefix}rotation gate {kind} has unrecognized angle {angle_str!r}. {exc}"
                )
            return None
        return ParsedGate(name=kind, targets=(idx,), parameter=theta)

    # Detect angle-first rotation order (legacy/wrong) and emit a hint.
    m_wrong = re.match(
        r"^R([XYZ])\(\s*([^,)]+)\s*,\s*\w+\[\d+\]\s*\)\s*$",
        s,
        re.IGNORECASE,
    )
    if m_wrong:
        axis = m_wrong.group(1).lower()
        if errors is not None:
            prefix = f"action {action_name!r}: " if action_name else ""
            errors.append(
                f"{prefix}rotation gate R{axis} uses angle-first argument order. "
                f"The canonical form is qubit-first: R{axis}(qs[N], <angle>)."
            )
        return None

    # Pauli/Clifford single-qubit primitives: X / Y / Z / S / T / I.
    m = re.match(
        r"^([XYZSTI])\(\s*\w+\[(\d+)\]\s*\)\s*$",
        s,
    )
    if m:
        return ParsedGate(name=m.group(1).upper(), targets=(int(m.group(2)),))

    # Generic single-qubit fallback: <Name>(qs[N]).
    m = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\(\s*\w+\[(\d+)\]\s*\)\s*$", s)
    if m:
        raw = m.group(1)
        idx = int(m.group(2))
        canonical_known = {"H", "X", "Y", "Z", "T", "S", "I"}
        upper = raw.upper()
        if upper in canonical_known:
            return ParsedGate(name=upper, targets=(idx,))
        return ParsedGate(name="custom", targets=(idx,), custom_name=upper)

    return None


def parse_effect_string(
    effect_str: str,
    angle_context: Optional[Mapping[str, float]] = None,
    errors: Optional[list[str]] = None,
    action_name: str = "",
) -> list[ParsedGate]:
    """Parse a semicolon-delimited effect string into a list of gates.

    Empty parts (from trailing ``;``) are skipped silently. Parts that
    don't match any pattern are dropped (mirrors the existing
    behavior of every call site).
    """
    if not effect_str:
        return []
    out: list[ParsedGate] = []
    for part in effect_str.split(";"):
        part = part.strip()
        if not part:
            continue
        gate = parse_single_gate(
            part,
            angle_context=angle_context,
            errors=errors,
            action_name=action_name,
        )
        if gate is not None:
            out.append(gate)
    return out
