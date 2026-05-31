"""Shared helpers for the declarative `## noise_model` section.

Resolves a machine's effective `NoiseModelSection`, including the deprecated
`noise:` context-field alias, and exposes the gate-class lists the verifier and
the Qiskit compiler both need. See `add-noise-model-section`.
"""

from __future__ import annotations

import re
from typing import Optional

from q_orca.ast import (
    ContextField,
    NoiseChannel,
    NoiseModelSection,
    NoiseTarget,
    QMachineDef,
    QTypeScalar,
)

# Gate-class membership used to resolve broad target selectors. The combined
# list (and its order) is kept identical to the legacy single-channel emission
# so the deprecated-field alias compiles byte-for-byte.
SINGLE_QUBIT_GATES = ["h", "x", "y", "z", "rx", "ry", "rz", "t", "s"]
TWO_QUBIT_GATES = ["cnot", "cx", "cz", "swap"]
ALL_GATES = SINGLE_QUBIT_GATES + TWO_QUBIT_GATES


def legacy_noise_field(machine: QMachineDef) -> Optional[ContextField]:
    """Return the deprecated `noise: noise_model` context field, if present."""
    for f in machine.context:
        if (
            f.name == "noise"
            and isinstance(f.type, QTypeScalar)
            and f.type.kind == "noise_model"
        ):
            return f
    return None


def parse_legacy_noise_string(text: str) -> Optional[NoiseChannel]:
    """Parse a legacy `noise:` default string into a single `all_gates` channel.

    Mirrors the historical regex parser; returns None for an unrecognized kind
    (no noise applied), preserving forward compatibility.
    """
    if not text:
        return None
    text = text.strip()
    all_gates = NoiseTarget(kind="all_gates", raw="all_gates")

    m = re.match(r"depolarizing\(\s*([\d.]+)\s*\)", text, re.IGNORECASE)
    if m:
        return NoiseChannel("depolarizing", all_gates, {"p": float(m.group(1))}, text)

    m = re.match(r"amplitude[_-]?damping\(\s*([\d.]+)\s*\)", text, re.IGNORECASE)
    if m:
        return NoiseChannel("amplitude_damping", all_gates, {"gamma": float(m.group(1))}, text)

    m = re.match(r"phase[_-]?damping\(\s*([\d.]+)\s*\)", text, re.IGNORECASE)
    if m:
        return NoiseChannel("phase_damping", all_gates, {"gamma": float(m.group(1))}, text)

    m = re.match(r"thermal\(\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)", text, re.IGNORECASE)
    if m:
        t1 = float(m.group(1))
        t2 = float(m.group(2)) if m.group(2) else t1
        return NoiseChannel("thermal", all_gates, {"T1": t1, "T2": t2}, text)

    return None


def resolve_noise_section(machine: QMachineDef) -> Optional[NoiseModelSection]:
    """Return the machine's effective noise model.

    Prefers an explicit `## noise_model` section; otherwise falls back to the
    deprecated `noise:` context field, wrapping it in a single-row section
    flagged `from_legacy_field=True`.
    """
    if machine.noise_model is not None:
        return machine.noise_model
    field = legacy_noise_field(machine)
    if field and field.default_value:
        channel = parse_legacy_noise_string(field.default_value)
        if channel is not None:
            return NoiseModelSection(channels=[channel], from_legacy_field=True)
    return None
