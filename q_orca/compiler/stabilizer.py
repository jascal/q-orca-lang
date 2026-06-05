"""Clifford classification for the stabilizer fast-path backend.

`is_clifford(machine)` walks every gate a machine can apply — bare-action
gates and per-call-site expansions of parametric actions, the same walk the
static unitarity check uses — and reports whether the whole circuit is
Clifford-only. A Clifford circuit can be verified on a stabilizer tableau in
polynomial time instead of the `O(2^n)` state-vector path.

The Clifford gate set is `{H, S, Sdg, X, Y, Z, CNOT/CX, CY, CZ, SWAP}` plus
`Rx/Ry/Rz` at angles that are integer multiples of `pi/2`. Gate-name
membership is cross-checked against the canonical `KNOWN_UNITARY_GATES` so a
newly added gate is treated as non-Clifford until it is explicitly classified
here.
"""

from __future__ import annotations

import math
from typing import Any

from q_orca.ast import QMachineDef, QuantumGate
from q_orca.compiler.parametric import expand_action_call
from q_orca.compiler.qiskit import _build_angle_context, _parse_effect_string
from q_orca.verifier.quantum import KNOWN_UNITARY_GATES

#: Fixed (angle-free) Clifford gates, by upper-cased gate kind. `CX` and
#: `CNOT` are the same gate under two spellings; both are accepted.
CLIFFORD_FIXED = {"H", "X", "Y", "Z", "S", "SDG", "CNOT", "CX", "CY", "CZ", "SWAP"}

#: Single-qubit rotations that are Clifford only at `pi/2` multiples.
CLIFFORD_ROTATIONS = {"RX", "RY", "RZ"}

_HALF_PI = math.pi / 2


def is_clifford_angle(theta: float, tol: float = 1e-9) -> bool:
    """True iff ``theta`` is (within ``tol``) an integer multiple of ``pi/2``.

    Reuses no symbolic machinery — the parser has already evaluated the angle
    to a float via ``q_orca/angle.py`` and stored it on ``QuantumGate.parameter``.
    An angle that *could* fold to a Clifford multiple but reaches us un-folded
    (the evaluator left it as, say, ``0.7853981 + 0.7853981``) simply reads as
    its float sum here, so genuine `pi/2` multiples are still recognized.
    """
    ratio = theta / _HALF_PI
    return abs(ratio - round(ratio)) < tol


def _gate_is_clifford(gate: QuantumGate) -> bool:
    kind = (gate.kind or "").upper()
    if kind in CLIFFORD_FIXED:
        return True
    if kind in CLIFFORD_ROTATIONS:
        return gate.parameter is not None and is_clifford_angle(float(gate.parameter))
    # T, CCNOT/CCZ/CSWAP, MCX/MCZ, controlled/two-qubit rotations, and custom
    # gates are all non-Clifford for the v1 fast path.
    return False


def _iter_machine_gates(machine: QMachineDef):
    """Yield ``(QuantumGate, location)`` for every gate the machine can apply.

    Bare (non-parametric) gate-bearing actions contribute their effect's gates
    once; parametric actions are expanded per transition call site so an
    ``Rz(theta)`` action is judged at each bound angle. Non-gate effects
    (classical mutations, measurements) parse to no gates and are skipped —
    they never make a circuit non-Clifford.
    """
    angle_ctx = _build_angle_context(machine)
    action_map = {a.name: a for a in machine.actions}

    for action in machine.actions:
        if action.parameters:
            continue  # handled per call site below
        location = {"action": action.name}
        if action.effect:
            for gate in _safe_parse(action.effect, angle_ctx):
                yield gate, location
        elif action.gate is not None:
            yield action.gate, location

    for t in machine.transitions:
        if t.bound_arguments is None:
            continue
        action = action_map.get(t.action or "")
        if action is None or not action.parameters:
            continue
        effect = expand_action_call(action, t.bound_arguments)
        if not effect:
            continue
        location = {
            "action": t.action,
            "transition": f"{t.source} --{t.event}--> {t.target}",
            "call": t.action_label or t.action,
        }
        for gate in _safe_parse(effect, angle_ctx):
            yield gate, location


def _safe_parse(effect: str, angle_ctx) -> list[QuantumGate]:
    """Parse an effect string to gates, tolerating non-gate effects."""
    try:
        return _parse_effect_string(effect, angle_context=angle_ctx)
    except Exception:
        return []


def is_clifford(machine: QMachineDef) -> tuple[bool, list[dict[str, Any]]]:
    """Classify a machine as Clifford-only.

    Returns ``(True, [])`` when every gate is Clifford, else
    ``(False, offenders)`` where each offender is
    ``{"kind", "parameter", "location"}`` for a gate that is not Clifford.
    The offender list preserves walk order, so ``offenders[0]`` is the first
    non-Clifford gate — the one the stabilizer backend names when it refuses.
    """
    offenders: list[dict[str, Any]] = []
    for gate, location in _iter_machine_gates(machine):
        if not _gate_is_clifford(gate):
            offenders.append({
                "kind": gate.custom_name or gate.kind,
                "parameter": gate.parameter,
                "location": location,
            })
    return (not offenders, offenders)


# Sanity: every fixed-Clifford spelling we accept is a known unitary gate (or a
# spelling alias of one), so this set cannot silently drift from the canonical
# gate registry. CX is the alias spelling of CNOT; SDG/CY are accepted
# defensively even if the parser does not emit them yet.
_KNOWN_UPPER = {g.upper() for g in KNOWN_UNITARY_GATES} | {"CX", "SDG", "CY"}
assert CLIFFORD_FIXED <= _KNOWN_UPPER, (
    f"Clifford gate set drifted from KNOWN_UNITARY_GATES: "
    f"{CLIFFORD_FIXED - _KNOWN_UPPER}"
)
