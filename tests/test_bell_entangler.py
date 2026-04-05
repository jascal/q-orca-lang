"""Tests and snapshots for BellEntangler example."""

import json
from pathlib import Path

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import verify_skill, compile_skill


BELL_SOURCE = (Path(__file__).parent.parent / "examples" / "bell-entangler.q.orca.md").read_text()


class TestBellEntanglerParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(BELL_SOURCE)
        assert len(result.file.machines) == 1
        machine = result.file.machines[0]
        assert machine.name == "BellEntangler"

    def test_has_5_states(self):
        result = parse_q_orca_markdown(BELL_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.states) == 5

    def test_has_3_events(self):
        result = parse_q_orca_markdown(BELL_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.events) == 3
        assert {e.name for e in machine.events} == {"prepare_H", "entangle", "measure_done"}

    def test_has_4_transitions(self):
        result = parse_q_orca_markdown(BELL_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.transitions) == 4

    def test_context_qubits(self):
        result = parse_q_orca_markdown(BELL_SOURCE)
        machine = result.file.machines[0]
        # Context has 'qubits' field with list<qubit> type
        qubit_fields = [f for f in machine.context if f.name == "qubits"]
        assert len(qubit_fields) >= 1
        assert qubit_fields[0].name == "qubits"
        # Check it's a qubit list type
        assert qubit_fields[0].type.kind == "list"


class TestBellEntanglerVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": BELL_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": BELL_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": BELL_SOURCE})
        assert result["machine"] == "BellEntangler"
        assert result["states"] == 5
        assert result["events"] == 3
        assert result["transitions"] == 4


class TestBellEntanglerCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": BELL_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]
        assert "|00>" in result["output"]
        assert "|ψ>" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": BELL_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]
        assert "qubit[" in result["output"]

    def test_compile_qiskit(self):
        result = compile_skill({"source": BELL_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]
        assert "Statevector" in result["output"]


class TestBellEntanglerSnapshot:
    """Snapshot tests for AST structure."""

    def test_ast_snapshot(self):
        """BellEntangler AST structure must match expected snapshot."""
        result = parse_q_orca_markdown(BELL_SOURCE)
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
            "events": sorted(["prepare_H", "entangle", "measure_done"]),
            "name": "BellEntangler",
            "num_actions": 4,
            "num_events": 3,
            "num_states": 5,
            "num_transitions": 4,
            "states": sorted(["|00>", "|+0>", "|ψ>", "|00_collapsed>", "|11_collapsed>"]),
        }

        assert snapshot == expected, (
            f"BellEntangler AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )

    def test_verification_snapshot(self):
        """Verification result must match expected structure."""
        result = verify_skill({"source": BELL_SOURCE})

        # Keys must match expected structure
        assert set(result.keys()) == {
            "status", "machine", "states", "events", "transitions", "errors"
        }
        assert result["status"] == "valid"
        assert result["machine"] == "BellEntangler"
