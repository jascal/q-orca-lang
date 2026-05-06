"""Tests for the ActiveTeleportation example.

Mirrors `tests/test_quantum_teleportation.py` for parse / verify /
compile / snapshot, plus a behavior class that prepares q0 in
`Ry(theta)|0>`, runs the protocol end-to-end (Bell pair, encode, two
mid-circuit measurements, two classical-feedforward Pauli corrections
on Bob's qubit), and checks Bob's q2 recovers the original state by
applying the inverse rotation and asserting q2 is |0>.

The behavior tests would catch a teleportation-style copy-paste bug
(corrections targeting the wrong qubit, or the X/Z mapping swapped
relative to the syndrome bits).
"""

import json
import math
import re
from contextlib import ExitStack
from pathlib import Path

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import compile_skill, verify_skill


AT_SOURCE = (
    Path(__file__).parent.parent / "examples" / "active-teleportation.q.orca.md"
).read_text()


class TestActiveTeleportationParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(AT_SOURCE)
        assert len(result.file.machines) == 1
        assert result.file.machines[0].name == "ActiveTeleportation"

    def test_has_5_states(self):
        machine = parse_q_orca_markdown(AT_SOURCE).file.machines[0]
        names = {s.name for s in machine.states}
        assert names == {
            "|init>", "|bell_ready>", "|alice_encoded>",
            "|measured>", "|teleported>",
        }

    def test_has_6_events(self):
        machine = parse_q_orca_markdown(AT_SOURCE).file.machines[0]
        assert {e.name for e in machine.events} == {
            "create_bell_pair", "encode_alice",
            "measure_alice_x", "measure_alice_z",
            "correct_x", "correct_z",
        }

    def test_corrections_target_bobs_qubit(self):
        """Regression guard: the X and Z corrections must both act on
        Bob's qubit (qs[2]), not Alice's q0/q1. This is the same class
        of copy-paste bug that bit
        `quantum-teleportation.q.orca.md` (commit c2d8eb9).
        """
        machine = parse_q_orca_markdown(AT_SOURCE).file.machines[0]
        actions = {a.name: a for a in machine.actions}

        feedfwd_x = actions["feedfwd_x"].conditional_gate
        feedfwd_z = actions["feedfwd_z"].conditional_gate
        assert feedfwd_x is not None and feedfwd_z is not None

        assert feedfwd_x.gate.kind == "X"
        assert feedfwd_x.gate.targets == [2], (
            f"feedfwd_x targets {feedfwd_x.gate.targets}, expected [2]"
        )
        assert feedfwd_z.gate.kind == "Z"
        assert feedfwd_z.gate.targets == [2], (
            f"feedfwd_z targets {feedfwd_z.gate.targets}, expected [2]"
        )

    def test_correction_bit_mapping(self):
        """Standard teleportation maps b1 -> X correction, b0 -> Z
        correction (where b0 is the q0 measurement after H, b1 is the
        q1 measurement after CNOT).
        """
        machine = parse_q_orca_markdown(AT_SOURCE).file.machines[0]
        actions = {a.name: a for a in machine.actions}
        assert actions["feedfwd_x"].conditional_gate.bit_idx == 1
        assert actions["feedfwd_z"].conditional_gate.bit_idx == 0


class TestActiveTeleportationVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": AT_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": AT_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": AT_SOURCE})
        assert result["machine"] == "ActiveTeleportation"
        assert result["states"] == 5
        assert result["events"] == 6
        assert result["transitions"] == 6


class TestActiveTeleportationCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": AT_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": AT_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]
        assert "if (c[1]) { x q[2]; }" in result["output"]
        assert "if (c[0]) { z q[2]; }" in result["output"]

    def test_compile_qiskit(self):
        result = compile_skill({"source": AT_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]
        assert "with qc.if_test((qc.clbits[1], 1)):" in result["output"]
        assert "with qc.if_test((qc.clbits[0], 1)):" in result["output"]


class TestActiveTeleportationSnapshot:
    """Snapshot test for AST structure."""

    def test_ast_snapshot(self):
        machine = parse_q_orca_markdown(AT_SOURCE).file.machines[0]
        snapshot = {
            "name": machine.name,
            "num_states": len(machine.states),
            "num_events": len(machine.events),
            "num_transitions": len(machine.transitions),
            "num_actions": len(machine.actions),
            "states": sorted(s.name for s in machine.states),
            "events": sorted(e.name for e in machine.events),
        }
        expected = {
            "name": "ActiveTeleportation",
            "num_states": 5,
            "num_events": 6,
            "num_transitions": 6,
            "num_actions": 6,
            "states": sorted([
                "|init>", "|bell_ready>", "|alice_encoded>",
                "|measured>", "|teleported>",
            ]),
            "events": sorted([
                "create_bell_pair", "encode_alice",
                "measure_alice_x", "measure_alice_z",
                "correct_x", "correct_z",
            ]),
        }
        assert snapshot == expected, (
            f"ActiveTeleportation AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )


def _build_teleportation_circuit(theta: float):
    """Construct the full active-teleportation circuit from the parsed
    machine, with q0 prepared as `Ry(theta)|0>` and a final
    `Ry(-theta)` followed by a Z-basis measurement on Bob's qubit q2.

    If teleportation succeeded, q2 holds Ry(theta)|0> after the two
    feedforward corrections. The trailing Ry(-theta) rotates that back
    to |0>, so the Z-basis measurement on q2 must be 0 deterministically.

    Bits layout: c0=meas(q0), c1=meas(q1), c2=meas(q2). The behavior
    assertion is on c2 only.
    """
    from qiskit import QuantumCircuit

    from q_orca.compiler.qiskit import _apply_gate_to_circuit

    machine = parse_q_orca_markdown(AT_SOURCE).file.machines[0]
    actions = {a.name: a for a in machine.actions}

    qc = QuantumCircuit(3, 3)

    qc.ry(theta, 0)

    for piece in actions["make_bell"].effect.split(";"):
        m = re.match(r"\s*Hadamard\(qs\[(\d+)\]\)\s*", piece)
        if m:
            qc.h(int(m.group(1)))
            continue
        m = re.match(r"\s*CNOT\(qs\[(\d+)\], qs\[(\d+)\]\)\s*", piece)
        if m:
            qc.cx(int(m.group(1)), int(m.group(2)))

    for piece in actions["encode_alice"].effect.split(";"):
        m = re.match(r"\s*CNOT\(qs\[(\d+)\], qs\[(\d+)\]\)\s*", piece)
        if m:
            qc.cx(int(m.group(1)), int(m.group(2)))
            continue
        m = re.match(r"\s*Hadamard\(qs\[(\d+)\]\)\s*", piece)
        if m:
            qc.h(int(m.group(1)))

    for name in ("meas_q0", "meas_q1"):
        mcm = actions[name].mid_circuit_measure
        qc.measure(mcm.qubit_idx, mcm.bit_idx)

    for name in ("feedfwd_x", "feedfwd_z"):
        cg = actions[name].conditional_gate
        with ExitStack() as stack:
            for bit_idx, value in cg.conditions:
                stack.enter_context(qc.if_test((qc.clbits[bit_idx], value)))
            _apply_gate_to_circuit(qc, cg.gate)

    qc.ry(-theta, 2)
    qc.measure(2, 2)
    return qc


class TestActiveTeleportationBehavior:
    """Round-trip simulation: prepare q0 in Ry(theta)|0>, run the
    protocol, and assert Bob's qubit recovers the original state.

    A target-qubit copy-paste bug or an X/Z bit-mapping swap would
    surface here as a non-zero c2 outcome on at least one of the four
    measurement branches.
    """

    @pytest.fixture(scope="class")
    def simulator(self):
        pytest.importorskip("qiskit_aer", reason="qiskit-aer not installed")
        from qiskit_aer import AerSimulator

        return AerSimulator(seed_simulator=42)

    @pytest.mark.parametrize(
        "theta, label",
        [
            (math.pi / 5, "theta_pi_over_5"),
            (math.pi / 3, "theta_pi_over_3"),
            (2 * math.pi / 7, "theta_2pi_over_7"),
            (1.234, "theta_1.234"),
        ],
    )
    def test_bob_recovers_original_state(self, simulator, theta, label):
        from qiskit import transpile

        qc = _build_teleportation_circuit(theta)
        compiled = transpile(qc, simulator)
        result = simulator.run(compiled, shots=512).result()
        counts = result.get_counts()
        # c2 (the trailing Bob-side measurement after Ry(-theta)) must be
        # 0 on every shot. Qiskit's bitstring is MSB-first across all 3
        # classical bits, so c2 is the leftmost character.
        for bitstring, n in counts.items():
            if n == 0:
                continue
            clean = bitstring.replace(" ", "")
            assert clean[0] == "0", (
                f"Bob did not recover original state for {label}: "
                f"bitstring={bitstring} ({n} shots), counts={counts}"
            )
