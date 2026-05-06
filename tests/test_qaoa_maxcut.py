"""Tests for the QAOAMaxCut example.

Mirrors `tests/test_quantum_teleportation.py` for parse / verify /
compile / snapshot. Behavior class executes the compiled Qiskit
script in analytic mode and asserts the output probability
distribution is normalized and non-uniform (the per-layer cost+mixer
unitary actually moves mass off the equal-superposition baseline).
"""

import json
from pathlib import Path

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import compile_skill, verify_skill


QAOA_SOURCE = (
    Path(__file__).parent.parent / "examples" / "qaoa-maxcut.q.orca.md"
).read_text()


class TestQAOAMaxCutParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(QAOA_SOURCE)
        assert len(result.file.machines) == 1
        assert result.file.machines[0].name == "QAOAMaxCut"

    def test_has_5_states(self):
        machine = parse_q_orca_markdown(QAOA_SOURCE).file.machines[0]
        names = {s.name for s in machine.states}
        assert names == {"|000>", "|+++ >", "|cost_applied>", "|mixed>", "|measured>"}

    def test_has_4_events(self):
        machine = parse_q_orca_markdown(QAOA_SOURCE).file.machines[0]
        assert {e.name for e in machine.events} == {
            "init", "apply_cost", "apply_mixer", "readout",
        }

    def test_context_has_gamma_beta_depth(self):
        machine = parse_q_orca_markdown(QAOA_SOURCE).file.machines[0]
        ctx_names = {f.name for f in machine.context}
        assert {"qubits", "gamma", "beta", "depth"} <= ctx_names

    def test_resource_invariants_declared(self):
        machine = parse_q_orca_markdown(QAOA_SOURCE).file.machines[0]
        metrics = {
            inv.metric for inv in machine.invariants if inv.kind == "resource"
        }
        assert {"gate_count", "depth", "cx_count", "logical_qubits"} <= metrics


class TestQAOAMaxCutVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": QAOA_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": QAOA_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": QAOA_SOURCE})
        assert result["machine"] == "QAOAMaxCut"
        assert result["states"] == 5
        assert result["events"] == 4
        assert result["transitions"] == 4


class TestQAOAMaxCutCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": QAOA_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": QAOA_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]
        out = result["output"].lower()
        # Per-layer prep: 3 H gates, 3 RZZ edges (decomposed as cx;rz;cx),
        # and 3 Rx mixer rotations.
        assert out.count("h q[") >= 3
        assert "rz(" in out
        assert out.count("cx q[") >= 6  # 2 CX per RZZ edge × 3 edges
        assert "rx(" in out

    def test_compile_qiskit(self):
        result = compile_skill({"source": QAOA_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]
        assert "qc.rzz(" in result["output"]
        assert "qc.rx(" in result["output"]


class TestQAOAMaxCutSnapshot:
    """Snapshot test for AST structure."""

    def test_ast_snapshot(self):
        machine = parse_q_orca_markdown(QAOA_SOURCE).file.machines[0]
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
            "name": "QAOAMaxCut",
            "num_states": 5,
            "num_events": 4,
            "num_transitions": 4,
            "num_actions": 3,
            "states": sorted([
                "|000>", "|+++ >", "|cost_applied>", "|mixed>", "|measured>",
            ]),
            "events": sorted([
                "init", "apply_cost", "apply_mixer", "readout",
            ]),
        }
        assert snapshot == expected, (
            f"QAOAMaxCut AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )


class TestQAOAMaxCutBehavior:
    """Analytic-mode probability check.

    With the shipped defaults (gamma=0.5, beta=0.25) the per-layer
    cost+mixer unitary moves probability mass off the uniform 1/8
    baseline. We assert the output distribution is normalized and
    non-uniform — a strict QAOA-optimality assertion would over-bind
    the test to specific parameter choices.
    """

    @pytest.fixture(scope="class")
    def probabilities(self):
        pytest.importorskip("qiskit", reason="qiskit not installed")

        from q_orca.compiler.qiskit import QSimulationOptions, compile_to_qiskit
        from q_orca.runtime.python import run_simulation

        machine = parse_q_orca_markdown(QAOA_SOURCE).file.machines[0]
        script = compile_to_qiskit(
            machine,
            QSimulationOptions(analytic=True, run=True, skip_qutip=True),
        )
        sim = run_simulation(script)
        assert sim.success, f"simulation failed: {sim.error}\n{sim.stderr}"
        return sim.probabilities

    def test_distribution_is_normalized(self, probabilities):
        total = sum(probabilities.values())
        assert abs(total - 1.0) < 1e-9, f"probabilities sum to {total}"

    def test_distribution_keys_are_three_bit_strings(self, probabilities):
        keys = set(probabilities.keys())
        assert keys == {format(i, "03b") for i in range(8)}

    def test_distribution_is_non_uniform(self, probabilities):
        """The cost + mixer must move probability off the uniform
        baseline. If the gates compiled to identities or got dropped,
        we'd see a flat 1/8 distribution.
        """
        uniform = 1.0 / 8
        max_dev = max(abs(p - uniform) for p in probabilities.values())
        assert max_dev > 0.01, (
            f"distribution is too close to uniform (max deviation = "
            f"{max_dev:.4f}); the QAOA layer may not be acting"
        )

    def test_distribution_is_z2_symmetric(self, probabilities):
        """K3 has Z_2 symmetry under bit-flip (x_i -> 1-x_i): the cost
        function is even in this symmetry, so QAOA preserves it. Each
        bitstring's probability should match its complement's. This
        also catches accidental phase-vs-amplitude bugs in the RZZ
        encoding.
        """
        for i in range(8):
            bs = format(i, "03b")
            comp = format(7 - i, "03b")
            assert abs(probabilities[bs] - probabilities[comp]) < 1e-6, (
                f"Z_2 symmetry broken: P({bs})={probabilities[bs]:.6f} "
                f"vs P({comp})={probabilities[comp]:.6f}"
            )
