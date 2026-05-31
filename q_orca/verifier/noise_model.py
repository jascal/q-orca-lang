"""Verifier rules for the declarative `## noise_model` section.

Four rules plus the deprecation diagnostic (`add-noise-model-section`):
- channel well-formedness (`NOISE_CHANNEL_INVALID`, `NOISE_PARAMETER_AMBIGUOUS`)
- target resolution (`NOISE_TARGET_NO_MATCH`)
- coherence budget (`COHERENCE_BUDGET_EXCEEDED`)
- backend compatibility (`STABILIZER_BACKEND_NOISE_INCOMPATIBLE`,
  `NOISE_DROPPED_FOR_BACKEND`)
plus `NOISE_CONTEXT_FIELD_DEPRECATED` for the legacy alias.
"""

from __future__ import annotations

import re
from typing import Optional

from q_orca.ast import NOISE_CHANNEL_KINDS, QMachineDef
from q_orca.noise import resolve_noise_section
from q_orca.verifier.types import QVerificationError, QVerificationResult

_PROB_PARAMS = {"p", "gamma", "p0given1", "p1given0"}
_TIME_PARAMS = {"T1", "T2"}
# Channels a stabilizer/Stim backend can represent.
_STABILIZER_OK = {"depolarizing", "bit_flip", "phase_flip"}


def _err(code: str, message: str, severity: str = "error", suggestion: str | None = None):
    return QVerificationError(code=code, message=message, severity=severity, suggestion=suggestion)


def _in_unit(p: float) -> bool:
    return isinstance(p, (int, float)) and 0.0 <= p <= 1.0


def _has_time_unit(raw: str, key: str) -> bool:
    return bool(re.search(rf"{key}\s*=\s*[\d.]+\s*(ns|us|ms)", raw, re.IGNORECASE))


def _check_well_formed(ch) -> list[QVerificationError]:
    out: list[QVerificationError] = []
    p = ch.parameters
    kind = ch.kind
    if kind not in NOISE_CHANNEL_KINDS:
        return [_err("NOISE_CHANNEL_INVALID", f"unknown noise channel {kind!r}")]

    has_time = any(k in p for k in _TIME_PARAMS)
    has_prob = any(k in p for k in _PROB_PARAMS)

    if kind in ("depolarizing", "bit_flip", "phase_flip"):
        if "p" not in p or not _in_unit(p.get("p")):
            out.append(_err("NOISE_CHANNEL_INVALID", f"{kind} requires p in [0, 1] (got {p.get('p')!r})"))
        if has_time:
            out.append(_err("NOISE_CHANNEL_INVALID", f"{kind} takes a probability p, not a time parameter"))
    elif kind in ("amplitude_damping", "phase_damping"):
        if "gamma" in p and has_time:
            out.append(_err("NOISE_PARAMETER_AMBIGUOUS",
                            f"{kind} declares both gamma and a time parameter; supply one, not both"))
        elif "gamma" in p:
            if not _in_unit(p["gamma"]):
                out.append(_err("NOISE_CHANNEL_INVALID", f"{kind} gamma must be in [0, 1] (got {p['gamma']!r})"))
        elif not has_time:
            out.append(_err("NOISE_CHANNEL_INVALID", f"{kind} requires gamma in [0, 1] or a time (T1/T2)"))
    elif kind == "thermal":
        if "T1" not in p or "T2" not in p:
            out.append(_err("NOISE_CHANNEL_INVALID", "thermal requires T1 and T2"))
        elif not (_has_time_unit(ch.raw_parameters, "T1") or float(p.get("T1", 0)) > 0):
            out.append(_err("NOISE_CHANNEL_INVALID", "thermal T1/T2 must be time-valued"))
        if has_prob:
            out.append(_err("NOISE_CHANNEL_INVALID", "thermal takes times (T1/T2), not a probability"))
    elif kind == "readout_error":
        for key in ("p0given1", "p1given0"):
            if key not in p or not _in_unit(p.get(key)):
                out.append(_err("NOISE_CHANNEL_INVALID", f"readout_error requires {key} in [0, 1]"))
    elif kind == "pauli":
        probs = p.get("probabilities")
        if not isinstance(probs, list) or len(probs) not in (4, 16):
            out.append(_err("NOISE_CHANNEL_INVALID",
                            "pauli requires a probabilities list of 4 (single-qubit) or 16 (two-qubit) entries"))
        elif abs(sum(float(x) for x in probs) - 1.0) > 1e-6:
            out.append(_err("NOISE_CHANNEL_INVALID", "pauli probabilities must sum to 1"))
    return out


def _machine_gate_names(machine: QMachineDef) -> set[str]:
    names: set[str] = set()
    for a in machine.actions:
        text = a.effect or ""
        for m in re.finditer(r"([A-Za-z][A-Za-z0-9_]*)\s*\(", text):
            names.add(m.group(1).lower())
    return names


def _check_target(ch, machine, qubit_count: int, gate_names: set[str]) -> list[QVerificationError]:
    t = ch.target
    if t.kind == "unknown":
        return [_err("NOISE_TARGET_NO_MATCH", f"unrecognized noise target {t.raw!r}", "warning")]
    if t.kind == "qubit_role":
        return [_err("NOISE_TARGET_NO_MATCH",
                     f"target {t.raw!r} requires the qubit-role-types capability (not yet available); "
                     f"the role selector is parsed but cannot be resolved", "warning")]
    if t.kind == "qubit_index" and (t.index is None or t.index >= qubit_count):
        return [_err("NOISE_TARGET_NO_MATCH",
                     f"target {t.raw!r} indexes qubit {t.index} beyond the declared count ({qubit_count})", "warning")]
    if t.kind == "gate_list":
        missing = [g for g in (x.lower() for x in t.gates) if g not in gate_names]
        if t.gates and len(missing) == len(t.gates):
            return [_err("NOISE_TARGET_NO_MATCH",
                         f"target {t.raw!r} names gate(s) that never appear in the machine", "warning")]
    return []


def _check_coherence(section, machine) -> list[QVerificationError]:
    t2_values = [ch.parameters.get("T2") for ch in section.channels
                 if ch.kind == "thermal" and ch.parameters.get("T2")]
    if not t2_values:
        return []
    gate_dur = None
    for f in machine.context:
        if f.name == "gate_duration_ns" and f.default_value:
            try:
                gate_dur = float(f.default_value)
            except ValueError:
                pass
    if gate_dur is None:
        return []  # no durations declared → check skipped, not failed
    n_gates = sum(len(re.findall(r"[A-Za-z][A-Za-z0-9_]*\s*\(", a.effect or "")) for a in machine.actions)
    circuit_ns = n_gates * gate_dur
    min_t2 = min(t2_values)
    if circuit_ns > min_t2:
        return [_err("COHERENCE_BUDGET_EXCEEDED",
                     f"estimated circuit duration {circuit_ns}ns exceeds the declared T2 {min_t2}ns "
                     f"({n_gates} gates x {gate_dur}ns)", "warning")]
    return []


def _check_backend(section, target: str) -> list[QVerificationError]:
    out: list[QVerificationError] = []
    tgt = (target or "").lower()
    if tgt in ("qasm", "qasm3", "qasm3.0", "openqasm"):
        kinds = ", ".join(ch.kind for ch in section.channels)
        out.append(_err("NOISE_DROPPED_FOR_BACKEND",
                        f"backend {target!r} has no native noise grammar; channels [{kinds}] are "
                        f"emitted as comments only and not simulated", "warning"))
    elif tgt in ("stabilizer", "stim"):
        for ch in section.channels:
            if ch.kind not in _STABILIZER_OK:
                out.append(_err("STABILIZER_BACKEND_NOISE_INCOMPATIBLE",
                                f"channel {ch.kind!r} is not representable on a stabilizer/Stim backend "
                                f"(only depolarizing, bit_flip, phase_flip are)"))
    return out


def _section_suggestion(channel) -> str:
    params = ", ".join(f"{k}={v}" for k, v in channel.parameters.items())
    return ("Replace the `noise:` context field with a `## noise_model` section, e.g. "
            f"`| {channel.kind} | {channel.target.raw} | {params} |`.")


def check_noise_model(machine: QMachineDef, target: Optional[str] = None) -> QVerificationResult:
    """Run the noise-model verifier rules. `target` is the compile target, if known."""
    errors: list[QVerificationError] = []
    section = resolve_noise_section(machine)
    if section is None or not section.channels:
        return QVerificationResult(valid=True, errors=errors)

    if section.from_legacy_field:
        errors.append(_err(
            "NOISE_CONTEXT_FIELD_DEPRECATED",
            "the `noise:` context field is deprecated and will be removed in v0.8; "
            "declare a `## noise_model` section instead",
            "warning", _section_suggestion(section.channels[0])))

    from q_orca.compiler.util import infer_qubit_count
    qubit_count = infer_qubit_count(machine)
    gate_names = _machine_gate_names(machine)

    for ch in section.channels:
        errors.extend(_check_well_formed(ch))
        errors.extend(_check_target(ch, machine, qubit_count, gate_names))
    errors.extend(_check_coherence(section, machine))
    if target is not None:
        errors.extend(_check_backend(section, target))

    return QVerificationResult(valid=not any(e.severity == "error" for e in errors), errors=errors)
