"""Tests and snapshots for VQE Heisenberg example."""

import json
from pathlib import Path


from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import verify_skill, compile_skill


VQE_SOURCE = (Path(__file__).parent.parent / "examples" / "vqe-heisenberg.q.orca.md").read_text()


class TestVQEParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(VQE_SOURCE)
        assert len(result.file.machines) == 1
        machine = result.file.machines[0]
        assert machine.name == "VQEH"

    def test_has_6_states(self):
        result = parse_q_orca_markdown(VQE_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.states) == 6

    def test_has_5_events(self):
        result = parse_q_orca_markdown(VQE_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.events) == 5
        assert {e.name for e in machine.events} == {
            "init", "apply_ansatz", "eval_energy", "update_theta", "check_convergence"
        }

    def test_has_34_transitions(self):
        result = parse_q_orca_markdown(VQE_SOURCE)
        machine = result.file.machines[0]
        assert len(machine.transitions) == 34

    def test_has_convergence_guards(self):
        result = parse_q_orca_markdown(VQE_SOURCE)
        machine = result.file.machines[0]
        guard_names = {g.name for g in machine.guards}
        assert "energy_ok" in guard_names
        assert "iter_max" in guard_names

    def test_context_has_theta_float(self):
        result = parse_q_orca_markdown(VQE_SOURCE)
        machine = result.file.machines[0]
        context_types = {f.name: f.type.kind for f in machine.context}
        assert context_types.get("theta") == "float"
        assert context_types.get("energy") == "float"
        assert context_types.get("iteration") == "int"


class TestVQEVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": VQE_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": VQE_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_no_superposition_leak_warnings(self):
        result = verify_skill({"source": VQE_SOURCE})
        errors = result.get("errors", [])
        leak_errors = [e for e in errors if e["code"] == "SUPERPOSITION_LEAK"]
        assert len(leak_errors) == 0, f"Unexpected superposition leaks: {leak_errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": VQE_SOURCE})
        assert result["machine"] == "VQEH"
        assert result["states"] == 6
        assert result["events"] == 5
        assert result["transitions"] == 34


class TestVQECompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": VQE_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]
        assert "|ψ_ansatz>" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": VQE_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]

    def test_compile_qiskit(self):
        result = compile_skill({"source": VQE_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]
        # Should include parameterized gate Ry
        assert "ry" in result["output"].lower()


class TestVQESnapshot:
    """Snapshot tests for AST structure."""

    def test_ast_snapshot(self):
        """VQEH AST structure must match expected snapshot."""
        result = parse_q_orca_markdown(VQE_SOURCE)
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
            "context_fields": ["energy", "iteration", "qubits", "theta"],
            "events": sorted(["apply_ansatz", "check_convergence", "eval_energy", "init", "update_theta"]),
            "name": "VQEH",
            "num_actions": 3,
            "num_events": 5,
            "num_states": 6,
            "num_transitions": 34,
            "states": sorted(["|converged>", "|measured>", "|not_converged>", "|start>", "|updated>", "|ψ_ansatz>"]),
        }

        assert snapshot == expected, (
            f"VQEH AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )

    def test_verification_snapshot(self):
        """Verification result must match expected structure."""
        result = verify_skill({"source": VQE_SOURCE})
        assert set(result.keys()) == {
            "status", "machine", "states", "events", "transitions", "errors"
        }
        assert result["status"] == "valid"
        assert result["machine"] == "VQEH"
