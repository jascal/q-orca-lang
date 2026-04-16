"""Tests and snapshots for GHZState example."""

import json
from pathlib import Path


from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import verify_skill, compile_skill


GHZ_SOURCE = (Path(__file__).parent.parent / "examples" / "ghz-state.q.orca.md").read_text()


class TestGHZParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(GHZ_SOURCE)
        assert len(result.file.machines) == 1
        machine = result.file.machines[0]
        assert machine.name == "GHZState"

    def test_has_6_states(self):
        result = parse_q_orca_markdown(GHZ_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.states) == 6

    def test_has_4_events(self):
        result = parse_q_orca_markdown(GHZ_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.events) == 4
        assert {e.name for e in machine.events} == {"init", "entangle_q1", "entangle_q2", "measure_done"}

    def test_has_5_transitions(self):
        result = parse_q_orca_markdown(GHZ_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.transitions) == 5


class TestGHZVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": GHZ_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": GHZ_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": GHZ_SOURCE})
        assert result["machine"] == "GHZState"
        assert result["states"] == 6
        assert result["events"] == 4
        assert result["transitions"] == 5


class TestGHZCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": GHZ_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]
        assert "|GHZ>" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": GHZ_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]
        assert "qubit[" in result["output"]

    def test_compile_qiskit(self):
        result = compile_skill({"source": GHZ_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]


class TestGHZSnapshot:
    """Snapshot tests for AST structure."""

    def test_ast_snapshot(self):
        """GHZState AST structure must match expected snapshot."""
        result = parse_q_orca_markdown(GHZ_SOURCE)
        machine = result.file.machines[0]

        snapshot = {
            "name": machine.name,
            "num_states": len(machine.states),
            "num_events": len(machine.events),
            "num_transitions": len(machine.transitions),
            "num_actions": len(machine.actions),
            "states": sorted(s.name for s in machine.states),
            "events": sorted(e.name for e in machine.events),
            "context_fields": sorted(f.name for f in machine.context),
        }

        expected = {
            "context_fields": ["outcome", "qubits"],
            "events": sorted(["init", "entangle_q1", "entangle_q2", "measure_done"]),
            "name": "GHZState",
            "num_actions": 5,
            "num_events": 4,
            "num_states": 6,
            "num_transitions": 5,
            "states": sorted(["|+00>", "|000>", "|000_result>", "|111_result>", "|GHZ>", "|Φ00_10>"]),
        }

        assert snapshot == expected, (
            f"GHZState AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )

    def test_verification_snapshot(self):
        """Verification result must match expected structure."""
        result = verify_skill({"source": GHZ_SOURCE})
        assert set(result.keys()) == {
            "status", "machine", "states", "events", "transitions", "errors"
        }
        assert result["status"] == "valid"
        assert result["machine"] == "GHZState"
