"""Tests for the PredictiveCoderLearning example.

Mirrors `tests/test_quantum_teleportation.py` for parse / verify /
compile / snapshot. Includes structural assertions on the iteration
loop (`continue` and `done` guards on `loop_back` / `finalize`,
`gradient_step` and `tick` actions) which would catch a regression
where the parser or verifier dropped the iteration plumbing.

Behavior testing is intentionally omitted: the machine drives a
classical-context-mutating learning loop whose end-to-end semantics
sit on top of `run-context-updates` plumbing that itself has its
own integration test (`tests/test_run_context_updates*.py`).
Re-running it here would just shadow that coverage.
"""

import json
from pathlib import Path

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.skills import compile_skill, verify_skill


PCL_SOURCE = (
    Path(__file__).parent.parent / "examples" / "predictive-coder-learning.q.orca.md"
).read_text()


class TestPredictiveCoderLearningParse:
    """Parse stage tests."""

    def test_parses_successfully(self):
        result = parse_q_orca_markdown(PCL_SOURCE)
        assert len(result.file.machines) == 1
        assert result.file.machines[0].name == "PredictiveCoderLearning"

    def test_has_7_states(self):
        machine = parse_q_orca_markdown(PCL_SOURCE).file.machines[0]
        names = {s.name for s in machine.states}
        assert names == {
            "|init>", "|prior_ready>", "|joined>",
            "|error_extracted>", "|measured>",
            "|model_updated>", "|converged>",
        }

    def test_has_7_events(self):
        machine = parse_q_orca_markdown(PCL_SOURCE).file.machines[0]
        assert {e.name for e in machine.events} == {
            "prepare_prior", "encode_data", "compute_error",
            "measure_error", "gradient_step", "loop_back", "finalize",
        }

    def test_iteration_context_fields(self):
        machine = parse_q_orca_markdown(PCL_SOURCE).file.machines[0]
        ctx_names = {f.name for f in machine.context}
        assert {"iteration", "max_iter", "eta", "theta_0", "theta_1", "theta_2"} <= ctx_names

    def test_continue_and_done_guards(self):
        """The loop_back -> prior_ready edge must carry a `continue`
        guard and the finalize -> converged edge must carry `done`.
        Without these guards the iterative runtime can't decide when
        to terminate.
        """
        machine = parse_q_orca_markdown(PCL_SOURCE).file.machines[0]
        edges = {(t.source, t.event): t for t in machine.transitions}
        loop_back = edges[("|model_updated>", "loop_back")]
        finalize = edges[("|model_updated>", "finalize")]
        assert loop_back.guard is not None and loop_back.guard.name == "continue"
        assert finalize.guard is not None and finalize.guard.name == "done"

        guard_names = {g.name for g in machine.guards}
        assert {"continue", "done"} <= guard_names

    def test_tick_action_increments_iteration(self):
        """The `tick` action must have an effect that bumps
        `iteration` — the iterative runtime drops out otherwise.
        """
        machine = parse_q_orca_markdown(PCL_SOURCE).file.machines[0]
        actions = {a.name: a for a in machine.actions}
        tick = actions["tick"]
        assert tick.effect is not None and "iteration" in tick.effect


class TestPredictiveCoderLearningVerify:
    """Verification stage tests."""

    def test_verifies_valid(self):
        result = verify_skill({"source": PCL_SOURCE})
        assert result["status"] == "valid"

    def test_no_error_severity(self):
        result = verify_skill({"source": PCL_SOURCE})
        errors = result.get("errors", [])
        assert not any(e["severity"] == "error" for e in errors), f"Has errors: {errors}"

    def test_verification_result_structure(self):
        result = verify_skill({"source": PCL_SOURCE})
        assert result["machine"] == "PredictiveCoderLearning"
        assert result["states"] == 7
        assert result["events"] == 7
        assert result["transitions"] == 7


class TestPredictiveCoderLearningCompile:
    """Compilation stage tests."""

    def test_compile_mermaid(self):
        result = compile_skill({"source": PCL_SOURCE}, "mermaid")
        assert result["status"] == "success"
        assert "stateDiagram-v2" in result["output"]

    def test_compile_qasm(self):
        result = compile_skill({"source": PCL_SOURCE}, "qasm")
        assert result["status"] == "success"
        assert "OPENQASM" in result["output"]
        out = result["output"].lower()
        assert "ry(" in out and "rz(" in out and "rx(" in out
        assert out.count("cx q[") >= 2

    def test_compile_qiskit(self):
        result = compile_skill({"source": PCL_SOURCE}, "qiskit")
        assert result["status"] == "success"
        assert "QuantumCircuit" in result["output"]
        assert "qc.ry(" in result["output"]
        assert "qc.measure(" in result["output"]


class TestPredictiveCoderLearningSnapshot:
    """Snapshot test for AST structure."""

    def test_ast_snapshot(self):
        machine = parse_q_orca_markdown(PCL_SOURCE).file.machines[0]
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
            "name": "PredictiveCoderLearning",
            "num_states": 7,
            "num_events": 7,
            "num_transitions": 7,
            "num_actions": 6,
            "states": sorted([
                "|init>", "|prior_ready>", "|joined>",
                "|error_extracted>", "|measured>",
                "|model_updated>", "|converged>",
            ]),
            "events": sorted([
                "prepare_prior", "encode_data", "compute_error",
                "measure_error", "gradient_step", "loop_back", "finalize",
            ]),
        }
        assert snapshot == expected, (
            f"PredictiveCoderLearning AST snapshot mismatch.\n"
            f"Got:      {json.dumps(snapshot, indent=2)}\n"
            f"Expected: {json.dumps(expected, indent=2)}"
        )
