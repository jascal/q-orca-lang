"""Tests for the BitFlipSyndrome example.

Mirrors `tests/test_quantum_teleportation.py` for parse / verify / compile,
plus a behavior class that runs all four syndrome patterns through the
classical-feedforward circuit and asserts the data register ends in |000>.
The behavior tests would FAIL on the pre-fix example, where every
single-condition `if bits[0] == 1` correction silently corrupts the
(1,1) syndrome (X-applied to q0 instead of q1).
"""

import json
import re
from contextlib import ExitStack
from pathlib import Path

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import compile_skill, verify_skill


BFS_SOURCE = (
    Path(__file__).parent.parent / "examples" / "bit-flip-syndrome.q.orca.md"
).read_text()


class TestBitFlipSyndromeParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(BFS_SOURCE)
        assert len(result.file.machines) == 1
        machine = result.file.machines[0]
        assert machine.name == "BitFlipSyndrome"

    def test_has_7_states(self):
        machine = parse_q_orca_markdown(BFS_SOURCE).file.machines[0]
        assert len(machine.states) == 7
        names = {s.name for s in machine.states}
        assert "|init>" in names
        assert "|corrected>" in names

    def test_has_6_events(self):
        machine = parse_q_orca_markdown(BFS_SOURCE).file.machines[0]
        assert {e.name for e in machine.events} == {
            "entangle",
            "measure_s0",
            "measure_s1",
            "correct_q0",
            "correct_q1",
            "correct_q2",
        }

    def test_has_6_transitions(self):
        machine = parse_q_orca_markdown(BFS_SOURCE).file.machines[0]
        assert len(machine.transitions) == 6

    def test_corrections_are_compound_conditional(self):
        """All three correction actions must carry 2-clause conditions."""
        machine = parse_q_orca_markdown(BFS_SOURCE).file.machines[0]
        actions = {a.name: a for a in machine.actions}
        for name in ("correct_q0", "correct_q1", "correct_q2"):
            cg = actions[name].conditional_gate
            assert cg is not None, f"{name} missing conditional_gate"
            assert len(cg.conditions) == 2, f"{name} has {len(cg.conditions)} clauses"

    def test_correction_clause_values(self):
        """Each correction's clauses must encode its syndrome pattern."""
        machine = parse_q_orca_markdown(BFS_SOURCE).file.machines[0]
        actions = {a.name: a for a in machine.actions}
        # syndrome (1, 0) -> q0
        assert actions["correct_q0"].conditional_gate.conditions == [(0, 1), (1, 0)]
        # syndrome (1, 1) -> q1
        assert actions["correct_q1"].conditional_gate.conditions == [(0, 1), (1, 1)]
        # syndrome (0, 1) -> q2
        assert actions["correct_q2"].conditional_gate.conditions == [(0, 0), (1, 1)]


class TestBitFlipSyndromeVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": BFS_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": BFS_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": BFS_SOURCE})
        assert result["machine"] == "BitFlipSyndrome"
        assert result["states"] == 7
        assert result["events"] == 6
        assert result["transitions"] == 6


class TestBitFlipSyndromeCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": BFS_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": BFS_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]
        # Each correction emits a compound `&&` guard.
        assert "if (c[0] && !c[1]) { x q[0]; }" in result["output"]
        assert "if (c[0] && c[1]) { x q[1]; }" in result["output"]
        assert "if (!c[0] && c[1]) { x q[2]; }" in result["output"]

    def test_compile_qiskit(self):
        result = compile_skill({"source": BFS_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]
        assert "with qc.if_test((qc.clbits[0], 1)):" in result["output"]
        assert "with qc.if_test((qc.clbits[1], 1)):" in result["output"]


class TestBitFlipSyndromeSnapshot:
    """Snapshot test for AST structure."""

    def test_ast_snapshot(self):
        machine = parse_q_orca_markdown(BFS_SOURCE).file.machines[0]
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
            "name": "BitFlipSyndrome",
            "num_states": 7,
            "num_events": 6,
            "num_transitions": 6,
            "num_actions": 6,
            "states": sorted([
                "|init>", "|entangled>", "|s0_measured>", "|s1_measured>",
                "|q0_corrected>", "|q1_corrected>", "|corrected>",
            ]),
            "events": sorted([
                "entangle", "measure_s0", "measure_s1",
                "correct_q0", "correct_q1", "correct_q2",
            ]),
        }
        assert snapshot == expected, (
            f"BitFlipSyndrome AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )


def _build_syndrome_circuit(error_qubit: int | None):
    """Construct the full syndrome+correction circuit from the parsed
    machine, with an optional X error pre-injected on a data qubit and
    final data-register measurements appended.

    Classical bits 0..1 carry the syndrome; bits 2..4 carry the post-
    correction data measurements (q0->c2, q1->c3, q2->c4). Cleanly
    decoded, we expect c2=c3=c4=0 for every input pattern.
    """
    from qiskit import QuantumCircuit

    from q_orca.compiler.qiskit import _apply_gate_to_circuit

    machine = parse_q_orca_markdown(BFS_SOURCE).file.machines[0]
    actions = {a.name: a for a in machine.actions}

    qc = QuantumCircuit(5, 5)

    if error_qubit is not None:
        qc.x(error_qubit)

    # Apply all CNOTs from `entangle_data.effect`. The parser only stores
    # the first parsed gate on `action.gate`, so we walk the effect string
    # to recover the full sequence.
    for piece in actions["entangle_data"].effect.split(";"):
        match = re.match(r"\s*CNOT\(qs\[(\d+)\], qs\[(\d+)\]\)\s*", piece)
        if match:
            qc.cx(int(match.group(1)), int(match.group(2)))

    for name in ("measure_s0", "measure_s1"):
        mcm = actions[name].mid_circuit_measure
        qc.measure(mcm.qubit_idx, mcm.bit_idx)

    for name in ("correct_q0", "correct_q1", "correct_q2"):
        cg = actions[name].conditional_gate
        with ExitStack() as stack:
            for bit_idx, value in cg.conditions:
                stack.enter_context(qc.if_test((qc.clbits[bit_idx], value)))
            _apply_gate_to_circuit(qc, cg.gate)

    qc.measure(0, 2)
    qc.measure(1, 3)
    qc.measure(2, 4)
    return qc


def _data_bits_zero(counts: dict) -> bool:
    """All shots return c4=c3=c2=0 (data register = |000>).

    Qiskit returns counts as space-separated bitstrings, MSB on the left.
    With 5 classical bits the format is `c4c3c2c1c0` (no spaces).
    """
    for bitstring, n in counts.items():
        if n == 0:
            continue
        # Strip any whitespace Qiskit may insert between registers.
        clean = bitstring.replace(" ", "")
        # Bits 2, 3, 4 are the leftmost three characters (MSB first).
        c4, c3, c2 = clean[0], clean[1], clean[2]
        if (c4, c3, c2) != ("0", "0", "0"):
            return False
    return True


class TestBitFlipSyndromeBehavior:
    """Round-trip simulation: every syndrome pattern must restore |000>.

    The behavior tests would silently fail on the pre-fix example
    (single-condition corrections) for the (1,1) pattern: `correct_q0`
    would fire on syndrome (1,1) and X q0, producing |110> instead of
    |010> -> |000>. The compound-condition fix gates each correction on
    the exact syndrome pair.
    """

    @pytest.fixture(scope="class")
    def simulator(self):
        pytest.importorskip("qiskit_aer", reason="qiskit-aer not installed")
        from qiskit_aer import AerSimulator

        return AerSimulator(seed_simulator=42)

    @pytest.mark.parametrize(
        "error_qubit, label",
        [
            (None, "no_error_(0,0)"),
            (0, "error_q0_(1,0)"),
            (1, "error_q1_(1,1)"),
            (2, "error_q2_(0,1)"),
        ],
    )
    def test_data_register_recovers_to_zero(self, simulator, error_qubit, label):
        from qiskit import transpile

        qc = _build_syndrome_circuit(error_qubit)
        compiled = transpile(qc, simulator)
        result = simulator.run(compiled, shots=256).result()
        counts = result.get_counts()
        assert _data_bits_zero(counts), (
            f"data register not recovered for {label}: counts={counts}"
        )
