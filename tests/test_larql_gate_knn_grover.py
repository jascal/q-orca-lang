"""Tests for the LarqlGateKnnGrover example.

Mirrors `tests/test_quantum_teleportation.py` for parse / verify /
compile / snapshot. Behavior is intentionally not retested here:
`tests/test_regression.py::test_grover_compiles_and_recovers_marked_state`
already runs this exact circuit through the qiskit pipeline and
asserts P(|1010>) > 0.96, so duplicating the simulation here would
just shadow that coverage.
"""

import json
from pathlib import Path

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import compile_skill, verify_skill


GROVER_SOURCE = (
    Path(__file__).parent.parent / "examples" / "larql-gate-knn-grover.q.orca.md"
).read_text()


class TestLarqlGateKnnGroverParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(GROVER_SOURCE)
        assert len(result.file.machines) == 1
        assert result.file.machines[0].name == "LarqlGateKnnGrover"

    def test_has_10_states(self):
        machine = parse_q_orca_markdown(GROVER_SOURCE).file.machines[0]
        assert len(machine.states) == 10
        names = {s.name for s in machine.states}
        # Sanity-check the iteration scaffolding and both terminal branches.
        assert {"idle", "uniform", "hit_france_paris", "hit_other"} <= names
        assert {"marked_iter1", "amplified_iter1"} <= names
        assert {"marked_iter3", "amplified_iter3"} <= names

    def test_has_4_events(self):
        machine = parse_q_orca_markdown(GROVER_SOURCE).file.machines[0]
        assert {e.name for e in machine.events} == {
            "load_query", "oracle_mark", "diffuse", "measure_done",
        }

    def test_three_oracle_diffusion_iterations(self):
        """N=16, M=1 Grover needs floor(pi/4 sqrt(16)) = 3 iterations.
        Loosening to 2 or 4 oracle marks drops fidelity below 96%, so
        this is a load-bearing structural property of the example.
        """
        machine = parse_q_orca_markdown(GROVER_SOURCE).file.machines[0]
        oracle_edges = [t for t in machine.transitions if t.event == "oracle_mark"]
        diffuse_edges = [t for t in machine.transitions if t.event == "diffuse"]
        assert len(oracle_edges) == 3, (
            f"expected 3 oracle marks, got {len(oracle_edges)}"
        )
        assert len(diffuse_edges) == 3, (
            f"expected 3 diffusions, got {len(diffuse_edges)}"
        )

    def test_marked_index_is_1010(self):
        """The phase oracle must mark |1010> = bitstring 1010 = the
        France->Paris edge. Encoding: X q0; X q2; MCZ; X q0; X q2.
        A miswired X bracket would shift the marked basis state.
        """
        machine = parse_q_orca_markdown(GROVER_SOURCE).file.machines[0]
        actions = {a.name: a for a in machine.actions}
        oracle_effect = actions["apply_phase_oracle"].effect
        # Bracket the MCZ with X on indices that are 0 in the target
        # bitstring 1010 (qs[0] and qs[2], reading high-to-low).
        assert "X(qs[0])" in oracle_effect
        assert "X(qs[2])" in oracle_effect
        assert "MCZ(qs[0], qs[1], qs[2], qs[3])" in oracle_effect


class TestLarqlGateKnnGroverVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": GROVER_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": GROVER_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": GROVER_SOURCE})
        assert result["machine"] == "LarqlGateKnnGrover"
        assert result["states"] == 10
        assert result["events"] == 4
        assert result["transitions"] == 9


class TestLarqlGateKnnGroverCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": GROVER_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": GROVER_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]

    def test_compile_qiskit(self):
        result = compile_skill({"source": GROVER_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]
        assert "qc.h(" in result["output"]


class TestLarqlGateKnnGroverSnapshot:
    """Snapshot test for AST structure."""

    def test_ast_snapshot(self):
        machine = parse_q_orca_markdown(GROVER_SOURCE).file.machines[0]
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
            "name": "LarqlGateKnnGrover",
            "num_states": 10,
            "num_events": 4,
            "num_transitions": 9,
            "num_actions": 5,
            "states": sorted([
                "idle", "uniform",
                "marked_iter1", "amplified_iter1",
                "marked_iter2", "amplified_iter2",
                "marked_iter3", "amplified_iter3",
                "hit_france_paris", "hit_other",
            ]),
            "events": sorted([
                "load_query", "oracle_mark", "diffuse", "measure_done",
            ]),
        }
        assert snapshot == expected, (
            f"LarqlGateKnnGrover AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )
