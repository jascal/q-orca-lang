"""Tests and snapshots for DeutschJozsa example."""

import json
from pathlib import Path


from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import verify_skill, compile_skill


DJ_SOURCE = (Path(__file__).parent.parent / "examples" / "deutsch-jozsa.q.orca.md").read_text()


class TestDeutschJozsaParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(DJ_SOURCE)
        assert len(result.file.machines) == 1
        machine = result.file.machines[0]
        assert machine.name == "DeutschJozsa"

    def test_has_5_states(self):
        result = parse_q_orca_markdown(DJ_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.states) == 5

    def test_has_3_events(self):
        result = parse_q_orca_markdown(DJ_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.events) == 3
        assert {e.name for e in machine.events} == {"prepare", "apply_oracle", "measure_result"}


class TestDeutschJozsaVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": DJ_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": DJ_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"


class TestDeutschJozsaCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": DJ_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": DJ_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]


class TestDeutschJozsaSnapshot:
    """Snapshot tests for AST structure."""

    def test_ast_snapshot(self):
        """DeutschJozsa AST structure must match expected snapshot."""
        result = parse_q_orca_markdown(DJ_SOURCE)
        machine = result.file.machines[0]

        snapshot = {
            "name": machine.name,
            "num_states": len(machine.states),
            "num_events": len(machine.events),
            "num_transitions": len(machine.transitions),
            "context_fields": sorted(f.name for f in machine.context),
        }

        expected = {
            "context_fields": ["is_constant", "qubits"],
            "name": "DeutschJozsa",
            "num_events": 3,
            "num_states": 5,
            "num_transitions": 4,
        }

        assert snapshot == expected, (
            f"DeutschJozsa AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )
