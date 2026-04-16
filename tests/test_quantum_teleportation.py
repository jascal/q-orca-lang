"""Tests and snapshots for QuantumTeleportation example."""

import json
from pathlib import Path


from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import verify_skill, compile_skill


QT_SOURCE = (Path(__file__).parent.parent / "examples" / "quantum-teleportation.q.orca.md").read_text()


class TestQuantumTeleportationParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(QT_SOURCE)
        assert len(result.file.machines) == 1
        machine = result.file.machines[0]
        assert machine.name == "QuantumTeleportation"

    def test_has_7_states(self):
        result = parse_q_orca_markdown(QT_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.states) == 7

    def test_has_3_events(self):
        result = parse_q_orca_markdown(QT_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.events) == 3
        assert {e.name for e in machine.events} == {"prepare", "alice_measure", "bob_correct"}

    def test_has_9_transitions(self):
        result = parse_q_orca_markdown(QT_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.transitions) == 9

    def test_bell_outcome_states(self):
        result = parse_q_orca_markdown(QT_SOURCE)
        machine = result.file.machines[0]
        state_names = {s.name for s in machine.states}
        # Four Bell measurement outcomes + teleported state
        assert "|bell_Φ+>" in state_names
        assert "|bell_Φ->" in state_names
        assert "|bell_Ψ+>" in state_names
        assert "|bell_Ψ->" in state_names


class TestQuantumTeleportationVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": QT_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": QT_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": QT_SOURCE})
        assert result["machine"] == "QuantumTeleportation"
        assert result["states"] == 7
        assert result["events"] == 3
        assert result["transitions"] == 9


class TestQuantumTeleportationCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": QT_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]
        assert "|ψ00>" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": QT_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]

    def test_compile_qiskit(self):
        result = compile_skill({"source": QT_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]


class TestQuantumTeleportationSnapshot:
    """Snapshot tests for AST structure."""

    def test_ast_snapshot(self):
        """QuantumTeleportation AST structure must match expected snapshot."""
        result = parse_q_orca_markdown(QT_SOURCE)
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
            "events": sorted(["alice_measure", "bob_correct", "prepare"]),
            "name": "QuantumTeleportation",
            "num_actions": 9,
            "num_events": 3,
            "num_states": 7,
            "num_transitions": 9,
            "states": sorted([
                "|bell_Φ+>", "|bell_Φ->", "|bell_Ψ+>", "|bell_Ψ->",
                "|teleported>", "|ψ00>", "|ψΦ+>"
            ]),
        }

        assert snapshot == expected, (
            f"QuantumTeleportation AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )

    def test_verification_snapshot(self):
        """Verification result must match expected structure."""
        result = verify_skill({"source": QT_SOURCE})
        assert set(result.keys()) == {
            "status", "machine", "states", "events", "transitions", "errors"
        }
        assert result["status"] == "valid"
        assert result["machine"] == "QuantumTeleportation"
