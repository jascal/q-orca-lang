"""Tests for Q-Orca skill functions."""

from q_orca.skills import parse_skill, verify_skill, compile_skill


class TestParseSkill:
    def test_parse_from_source(self, bell_source):
        result = parse_skill({"source": bell_source})
        assert result["status"] == "success"
        assert len(result["machines"]) == 1
        assert result["machine"]["name"] == "BellEntangler"

    def test_parse_from_file(self):
        result = parse_skill({"file": "examples/bell-entangler.q.orca.md"})
        assert result["status"] == "success"
        assert result["machine"]["name"] == "BellEntangler"

    def test_parse_returns_states(self, bell_source):
        result = parse_skill({"source": bell_source})
        states = result["machine"]["states"]
        assert "|00>" in states
        assert "|ψ>" in states

    def test_parse_returns_events(self, bell_source):
        result = parse_skill({"source": bell_source})
        events = result["machine"]["events"]
        assert "prepare_H" in events
        assert "entangle" in events

    def test_parse_returns_transitions(self, bell_source):
        result = parse_skill({"source": bell_source})
        transitions = result["machine"]["transitions"]
        assert len(transitions) == 4

    def test_parse_invalid_source(self):
        result = parse_skill({"source": "not a machine"})
        # No machine found — still success but empty
        assert result["status"] == "success"
        assert len(result["machines"]) == 0

    def test_parse_missing_input(self):
        result = parse_skill({})
        assert result["status"] == "error"


class TestVerifySkill:
    def test_verify_valid_machine(self, bell_source):
        result = verify_skill({"source": bell_source})
        assert result["status"] == "valid"
        assert result["machine"] == "BellEntangler"
        assert result["states"] > 0
        assert result["transitions"] > 0

    def test_verify_returns_counts(self, bell_source):
        result = verify_skill({"source": bell_source})
        assert result["states"] == 5
        assert result["events"] == 3
        assert result["transitions"] == 4

    def test_verify_invalid_machine(self):
        source = """\
# machine Bad

## events
- go

## state |0> [initial]
> Start

## state |orphan>
> Unreachable

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
"""
        result = verify_skill({"source": source})
        assert result["status"] == "invalid"
        assert len(result["errors"]) > 0

    def test_verify_skip_completeness(self, bell_source):
        result = verify_skill({"source": bell_source}, skip_completeness=True)
        completeness_errors = [e for e in result["errors"] if e["code"] == "INCOMPLETE_EVENT_HANDLING"]
        assert len(completeness_errors) == 0

    def test_verify_skip_quantum(self, bell_source):
        result = verify_skill({"source": bell_source}, skip_quantum=True)
        quantum_codes = {"UNVERIFIED_UNITARITY", "NO_CLONING_VIOLATION",
                         "NO_ENTANGLEMENT", "INCOMPLETE_COLLAPSE"}
        for e in result["errors"]:
            assert e["code"] not in quantum_codes


class TestCompileSkill:
    def test_compile_mermaid(self, bell_source):
        result = compile_skill({"source": bell_source}, "mermaid")
        assert result["status"] == "success"
        assert result["target"] == "mermaid"
        assert "stateDiagram" in result["output"]

    def test_compile_qasm(self, bell_source):
        result = compile_skill({"source": bell_source}, "qasm")
        assert result["status"] == "success"
        assert result["target"] == "qasm"
        assert "OPENQASM" in result["output"]

    def test_compile_qiskit(self, bell_source):
        result = compile_skill({"source": bell_source}, "qiskit")
        assert result["status"] == "success"
        assert result["target"] == "qiskit"
        assert "QuantumCircuit" in result["output"]

    def test_compile_unknown_target(self, bell_source):
        result = compile_skill({"source": bell_source}, "unknown")
        assert result["status"] == "error"
