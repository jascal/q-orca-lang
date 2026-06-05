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


class StabilizerCompileError(ValueError):
    """Raised when a machine cannot be compiled to a stabilizer sampling circuit."""

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


def _quantum_gate_to_dict(g: QuantumGate) -> dict[str, Any]:
    """Convert a `QuantumGate` AST node to the verifier gate-dict shape that
    `clifford_gate_to_stim_ops` consumes."""
    return {
        "name": g.kind,
        "targets": list(g.targets),
        "controls": list(g.controls) if g.controls else [],
        "params": {"theta": g.parameter} if g.parameter is not None else {},
    }


#: Pauli correction kind -> Stim measurement-record-controlled gate.
_FEEDFORWARD_OP = {"X": "CX", "Y": "CY", "Z": "CZ"}


def compile_to_stim(machine: QMachineDef):
    """Compile a Clifford machine to a runnable `stim.Circuit` (with measurements).

    Walks the machine's linearised action stream (fixed `[loop N]` bodies
    unrolled) emitting: Clifford gates via the shared
    `clifford_gate_to_stim_ops` mapping; `measure(qs[i]) -> bits[j]` as `M i`,
    tracking a `bit -> measurement-record` index; and a single-clause Pauli
    feedforward (`if bits[j] == 1: X/Y/Z(qs[k])`) as Stim's record-controlled
    `CX`/`CY`/`CZ rec[-N]` instruction, where `N` is `bits[j]`'s offset from the
    current end of the record at emit time.

    Raises `StabilizerCompileError` (never a silently-wrong circuit) on a
    non-Clifford machine, a non-Pauli or `== 0` / multi-clause feedforward, a
    feedforward on an unmeasured bit, or an adaptive `[loop until:]` body.

    Note: `MR` (measure-and-reset) is not emitted — q-orca has no `reset` syntax
    yet, so every measurement is `M`. `MR` support arrives with reset syntax.
    """
    import stim
    from q_orca.compiler.loops import LOOP_END, LOOP_START
    from q_orca.compiler.qiskit import _extract_gate_sequence
    from q_orca.verifier.stabilizer_entanglement import clifford_gate_to_stim_ops

    is_cliff, offenders = is_clifford(machine)
    if not is_cliff:
        first = offenders[0]
        raise StabilizerCompileError(
            f"Gate '{first['kind']}' is not Clifford — compile_to_stim requires a "
            f"Clifford-only machine (location: {first['location']})"
        )

    action_map = {a.name: a for a in machine.actions}
    circuit = stim.Circuit()
    bit_to_record: dict[int, int] = {}
    n_records = 0

    for action_name, gates, comment in _extract_gate_sequence(machine, unroll_loops=True):
        if action_name in (LOOP_START, LOOP_END):
            raise StabilizerCompileError(
                "compile_to_stim cannot sample an adaptive `[loop until:]` body; "
                "only fixed `[loop N]` loops (unrolled) are supported"
            )
        action = action_map.get(action_name)
        if action is not None and action.mid_circuit_measure is not None:
            mcm = action.mid_circuit_measure
            # Single change point for MR: when q-orca gains `reset` syntax, emit
            # "MR" here if an unconditional reset(qs[i]) follows (see design D2).
            circuit.append("M", [mcm.qubit_idx])
            bit_to_record[mcm.bit_idx] = n_records
            n_records += 1
        elif action is not None and action.conditional_gate is not None:
            _emit_feedforward(circuit, action.conditional_gate, bit_to_record, n_records, stim)
        elif action is not None and action.context_update is not None:
            continue  # classical mutation — no circuit effect
        else:
            for g in gates:
                for op, tgts in clifford_gate_to_stim_ops(_quantum_gate_to_dict(g)):
                    circuit.append(op, tgts)

    return circuit


def compile_to_qiskit_stabilizer(machine: QMachineDef):
    """Compile a Clifford machine to a Qiskit `QuantumCircuit` for the
    `AerSimulator(method="stabilizer")` engine — the secondary sampling target /
    fallback when Stim is absent but `qiskit-aer` is present.

    Same action-stream walk and diagnostics as `compile_to_stim`; feedforward
    uses Qiskit's `if_test` on the measured clbit. Raises `StabilizerCompileError`
    on unsupported constructs (incl. an `Ry` at a `π/2` multiple, which Stim
    handles natively but has no direct Qiskit stabilizer gate — use `compile_to_stim`).
    """
    from qiskit import QuantumCircuit
    from q_orca.compiler.loops import LOOP_END, LOOP_START
    from q_orca.compiler.qiskit import _extract_gate_sequence
    from q_orca.compiler.util import infer_qubit_count

    is_cliff, offenders = is_clifford(machine)
    if not is_cliff:
        raise StabilizerCompileError(
            f"Gate '{offenders[0]['kind']}' is not Clifford — "
            f"compile_to_qiskit_stabilizer requires a Clifford-only machine"
        )

    n_qubits = infer_qubit_count(machine)
    n_bits = _classical_bit_count(machine)
    qc = QuantumCircuit(n_qubits, max(n_bits, 1))
    action_map = {a.name: a for a in machine.actions}

    for action_name, gates, comment in _extract_gate_sequence(machine, unroll_loops=True):
        if action_name in (LOOP_START, LOOP_END):
            raise StabilizerCompileError("adaptive `[loop until:]` body cannot be sampled")
        action = action_map.get(action_name)
        if action is not None and action.mid_circuit_measure is not None:
            mcm = action.mid_circuit_measure
            qc.measure(mcm.qubit_idx, mcm.bit_idx)
        elif action is not None and action.conditional_gate is not None:
            _emit_qiskit_feedforward(qc, action.conditional_gate)
        elif action is not None and action.context_update is not None:
            continue
        else:
            for g in gates:
                _apply_clifford_to_qc(qc, g)
    return qc


def _classical_bit_count(machine: QMachineDef) -> int:
    """Number of classical bits a machine measures into (max bit index + 1)."""
    return max(
        (a.mid_circuit_measure.bit_idx + 1
         for a in machine.actions if a.mid_circuit_measure is not None),
        default=0,
    )


#: Single-qubit fixed Clifford gates → Qiskit `QuantumCircuit` method name.
_QISKIT_1Q = {"H": "h", "X": "x", "NOT": "x", "Y": "y", "Z": "z", "S": "s", "SDG": "sdg", "SDAG": "sdg"}


def _apply_clifford_to_qc(qc, g: QuantumGate) -> None:
    kind = (g.kind or "").upper()
    t = g.targets
    if kind in _QISKIT_1Q:
        getattr(qc, _QISKIT_1Q[kind])(t[0])
    elif kind in ("CNOT", "CX"):
        qc.cx(g.controls[0] if g.controls else t[0], t[-1])
    elif kind == "CZ":
        qc.cz(g.controls[0] if g.controls else t[0], t[0])
    elif kind == "SWAP":
        qc.swap(t[0], t[1])
    elif kind in ("RX", "RZ"):
        method = qc.sx if kind == "RX" else qc.s
        for _ in range(round((g.parameter or 0.0) / _HALF_PI) % 4):
            method(t[0])
    elif kind == "RY":
        raise StabilizerCompileError(
            "Ry at a π/2 multiple has no direct Qiskit stabilizer gate; "
            "use compile_to_stim (Stim handles √Y natively)"
        )
    else:
        raise StabilizerCompileError(f"gate '{g.kind}' unsupported in the Aer stabilizer target")


def _emit_qiskit_feedforward(qc, cg) -> None:
    if len(cg.conditions) != 1:
        raise StabilizerCompileError("only single-clause feedforward is supported")
    bit_idx, value = cg.conditions[0]
    pauli = (cg.gate.kind or "").upper()
    if pauli not in ("X", "Y", "Z"):
        raise StabilizerCompileError(f"feedforward correction must be a Pauli; got '{cg.gate.kind}'")
    with qc.if_test((qc.clbits[bit_idx], value)):
        {"X": qc.x, "Y": qc.y, "Z": qc.z}[pauli](cg.gate.targets[0])


def sample_stim_circuit(circuit, shots: int, seed: int | None = None) -> dict[str, int]:
    """Sample a compiled `stim.Circuit` and return an ``outcome-bitstring -> count``
    dict. The bitstring lists measurement records in emission order (one char per
    measurement); seeded for reproducibility."""
    samples = circuit.compile_sampler(seed=seed).sample(shots)
    counts: dict[str, int] = {}
    for row in samples:
        key = "".join("1" if b else "0" for b in row)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _emit_feedforward(circuit, cg, bit_to_record: dict, n_records: int, stim) -> None:
    """Emit a Pauli feedforward correction as a record-controlled gate."""
    if len(cg.conditions) != 1:
        raise StabilizerCompileError(
            "compile_to_stim supports only single-clause feedforward; got "
            f"{len(cg.conditions)} AND-clauses. Multi-clause syndrome decoding "
            "(e.g. bit-flip / surface codes) is a decoder concern — a planned "
            "follow-on using Stim DETECTOR annotations + PyMatching, not an "
            "in-circuit rec[-N] correction"
        )
    bit_idx, value = cg.conditions[0]
    if value != 1:
        raise StabilizerCompileError(
            f"compile_to_stim supports only `bits[{bit_idx}] == 1` feedforward "
            f"(got == {value}); `== 0` is a follow-on"
        )
    pauli = (cg.gate.kind or "").upper()
    if pauli not in _FEEDFORWARD_OP:
        raise StabilizerCompileError(
            f"feedforward correction must be a Pauli (X/Y/Z); got '{cg.gate.kind}'"
        )
    if bit_idx not in bit_to_record:
        raise StabilizerCompileError(
            f"feedforward on bits[{bit_idx}] but no measurement has populated it"
        )
    rel = n_records - bit_to_record[bit_idx]  # relative offset: rec[-rel]
    circuit.append(_FEEDFORWARD_OP[pauli], [stim.target_rec(-rel), cg.gate.targets[0]])


# Sanity: every fixed-Clifford spelling we accept is a known unitary gate (or a
# spelling alias of one), so this set cannot silently drift from the canonical
# gate registry. CX is the alias spelling of CNOT; SDG/CY are accepted
# defensively even if the parser does not emit them yet.
_KNOWN_UPPER = {g.upper() for g in KNOWN_UNITARY_GATES} | {"CX", "SDG", "CY"}
assert CLIFFORD_FIXED <= _KNOWN_UPPER, (
    f"Clifford gate set drifted from KNOWN_UNITARY_GATES: "
    f"{CLIFFORD_FIXED - _KNOWN_UPPER}"
)
