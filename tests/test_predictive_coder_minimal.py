"""Tests for the PredictiveCoderMinimal example.

Mirrors `tests/test_quantum_teleportation.py` for parse / verify /
compile / snapshot, plus a behavior class that exercises the parity
CNOT chain with both default thetas (q1=|+> => uniform ancilla) and
hand-built variants where q0 and q1 are forced to Z-eigenstates so
the ancilla is deterministic. The variants form the truth table of
q0 XOR q1 — a direct check that the CNOT(q0->q2);CNOT(q1->q2) chain
encodes parity correctly.
"""

import json
import re
from pathlib import Path

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import compile_skill, verify_skill


PCM_SOURCE = (
    Path(__file__).parent.parent / "examples" / "predictive-coder-minimal.q.orca.md"
).read_text()


class TestPredictiveCoderMinimalParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(PCM_SOURCE)
        assert len(result.file.machines) == 1
        assert result.file.machines[0].name == "PredictiveCoderMinimal"

    def test_has_5_states(self):
        machine = parse_q_orca_markdown(PCM_SOURCE).file.machines[0]
        names = {s.name for s in machine.states}
        assert names == {
            "|init>", "|prior_ready>", "|joined>",
            "|error_extracted>", "|bit_read>",
        }

    def test_has_4_events(self):
        machine = parse_q_orca_markdown(PCM_SOURCE).file.machines[0]
        assert {e.name for e in machine.events} == {
            "prepare_prior", "encode_data", "compute_error", "measure_error",
        }

    def test_context_has_three_thetas(self):
        machine = parse_q_orca_markdown(PCM_SOURCE).file.machines[0]
        ctx_names = {f.name for f in machine.context}
        assert {"qubits", "bits", "theta_0", "theta_1", "theta_2"} <= ctx_names


class TestPredictiveCoderMinimalVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": PCM_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": PCM_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": PCM_SOURCE})
        assert result["machine"] == "PredictiveCoderMinimal"
        assert result["states"] == 5
        assert result["events"] == 4
        assert result["transitions"] == 4


class TestPredictiveCoderMinimalCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": PCM_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": PCM_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]
        out = result["output"].lower()
        assert "ry(" in out and "rz(" in out and "rx(" in out
        assert out.count("cx q[") >= 2  # parity CNOTs to ancilla

    def test_compile_qiskit(self):
        result = compile_skill({"source": PCM_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]
        assert "qc.ry(" in result["output"]
        assert "qc.cx(" in result["output"]
        assert "qc.measure(" in result["output"]


class TestPredictiveCoderMinimalSnapshot:
    """Snapshot test for AST structure."""

    def test_ast_snapshot(self):
        machine = parse_q_orca_markdown(PCM_SOURCE).file.machines[0]
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
            "name": "PredictiveCoderMinimal",
            "num_states": 5,
            "num_events": 4,
            "num_transitions": 4,
            "num_actions": 4,
            "states": sorted([
                "|init>", "|prior_ready>", "|joined>",
                "|error_extracted>", "|bit_read>",
            ]),
            "events": sorted([
                "prepare_prior", "encode_data", "compute_error", "measure_error",
            ]),
        }
        assert snapshot == expected, (
            f"PredictiveCoderMinimal AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )


def _build_parity_circuit(model_x: bool, data_x: bool):
    """Build a variant of the predictive-coder circuit where q0 is
    optionally pre-flipped with X (instead of the Ry/Rz/Rx ansatz)
    and q1 is optionally pre-flipped with X (instead of H). This
    forces both registers into Z-eigenstates so the ancilla parity
    is deterministic.
    """
    from qiskit import QuantumCircuit

    machine = parse_q_orca_markdown(PCM_SOURCE).file.machines[0]
    actions = {a.name: a for a in machine.actions}

    qc = QuantumCircuit(3, 1)

    if model_x:
        qc.x(0)
    if data_x:
        qc.x(1)

    for piece in actions["parity_to_ancilla"].effect.split(";"):
        m = re.match(r"\s*CNOT\(qs\[(\d+)\], qs\[(\d+)\]\)\s*", piece)
        if m:
            qc.cx(int(m.group(1)), int(m.group(2)))

    mcm = actions["measure_ancilla"].mid_circuit_measure
    qc.measure(mcm.qubit_idx, mcm.bit_idx)
    return qc


class TestPredictiveCoderMinimalBehavior:
    """Behavior tests for the parity CNOT chain.

    The default-thetas case asserts the ancilla is uniform (q1=|+>
    makes parity XOR with a uniform random bit, which is uniform
    regardless of the model q0 distribution). The XOR truth-table
    cases force q0 and q1 into Z-eigenstates so parity is
    deterministic — these would catch a swapped CNOT direction or a
    target/control miswiring in the parity action.
    """

    @pytest.fixture(scope="class")
    def simulator(self):
        pytest.importorskip("qiskit_aer", reason="qiskit-aer not installed")
        from qiskit_aer import AerSimulator

        return AerSimulator(seed_simulator=42)

    def test_default_ancilla_is_uniform(self):
        """With q1 prepared as |+> (encode_datum=H), the ancilla
        parity is uniform regardless of the model's Z-basis bias.
        Build the unitary portion of the circuit (no measure) and
        compute the q2 marginal analytically — `run_simulation` can't
        statevector-evaluate a circuit with a mid-circuit measure.
        """
        pytest.importorskip("qiskit", reason="qiskit not installed")

        from qiskit import QuantumCircuit
        from qiskit.quantum_info import Statevector

        machine = parse_q_orca_markdown(PCM_SOURCE).file.machines[0]
        ctx = {f.name: float(f.default_value) for f in machine.context
               if f.type.kind == "float"}

        qc = QuantumCircuit(3)
        qc.ry(ctx["theta_0"], 0)
        qc.rz(ctx["theta_1"], 0)
        qc.rx(ctx["theta_2"], 0)
        qc.h(1)
        qc.cx(0, 2)
        qc.cx(1, 2)

        sv = Statevector(qc)
        probs = sv.probabilities()
        # Qiskit's `probabilities()` returns one entry per 3-qubit
        # basis state in little-endian (q2 q1 q0) order, so q2 is the
        # MSB of the 3-bit index.
        p_anc_one = sum(p for i, p in enumerate(probs) if (i >> 2) & 1)
        assert abs(p_anc_one - 0.5) < 1e-9, (
            f"P(ancilla=1) = {p_anc_one}, expected 0.5 (q1=|+> makes parity uniform)"
        )

    @pytest.mark.parametrize(
        "model_x, data_x, expected_bit, label",
        [
            (False, False, 0, "00_xor_0"),
            (True, False, 1, "10_xor_1"),
            (False, True, 1, "01_xor_1"),
            (True, True, 0, "11_xor_0"),
        ],
    )
    def test_parity_truth_table(self, simulator, model_x, data_x, expected_bit, label):
        """Force q0,q1 into Z-eigenstates (skipping the ansatz/H) and
        verify ancilla = q0 XOR q1 deterministically. This pins down
        the CNOT direction in `parity_to_ancilla` — a flipped CNOT
        (q2 controlling q0/q1) would corrupt the model/data registers
        without changing the ancilla, but a wrong target qubit on
        either CNOT would surface here as a mismatched ancilla bit.
        """
        from qiskit import transpile

        qc = _build_parity_circuit(model_x, data_x)
        compiled = transpile(qc, simulator)
        result = simulator.run(compiled, shots=256).result()
        counts = result.get_counts()
        # Single-bit classical register: bitstring is just '0' or '1'.
        for bitstring, n in counts.items():
            if n == 0:
                continue
            clean = bitstring.replace(" ", "")
            assert clean == str(expected_bit), (
                f"parity mismatch for {label}: bitstring={bitstring} "
                f"({n} shots), expected={expected_bit}, counts={counts}"
            )
