"""Tests for the composed-machine execution engine (add-composed-runtime §5)."""

from pathlib import Path

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.runtime.composed import run_composed
from q_orca.runtime.iterative import simulate_iterative
from q_orca.runtime.types import QIterativeRuntimeError, QIterativeSimulationOptions


def _file(src):
    result = parse_q_orca_markdown(src)
    assert not result.errors, result.errors
    return result.file


def _opts(**kw):
    return QIterativeSimulationOptions(seed_simulator=42, **kw)


# A classical child that exposes a context field as a return.
_CLASSICAL_CHILD = """
---
# machine Counter
## context
| Field  | Type | Default |
| seed   | int  | 0       |
| result | int  | 7       |
## state |c0> [initial]
## state |c1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |c0> | g | | |c1> | |
## returns
| Name   | Type | Statistics |
| result | int  |            |
| seed   | int  |            |
"""


def _classical_parent(arg=""):
    return (
        "# machine Orchestrator\n## context\n| Field | Type | Default |\n"
        "| iteration | int | 3 |\n| out | int | -1 |\n| seen | int | -1 |\n"
        "## state |idle> [initial]\n"
        f"## state |step> [invoke: Counter({arg})]\n"
        "> returns: out=result, seen=seed\n"
        "## state |done> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n"
        "| |idle> | advance | | |step> | |\n| |step> | advance | | |done> | |\n"
        + _CLASSICAL_CHILD
    )


class TestComposedRuntime:
    def test_single_machine_runs_unchanged(self):
        src = (
            "# machine Solo\n## context\n| Field | Type | Default |\n| n | int | 5 |\n"
            "## state |a> [initial]\n## state |b> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n| |a> | g | | |b> | |\n"
        )
        f = _file(src)
        composed = run_composed(f, f.machines[0], _opts())
        direct = simulate_iterative(f.machines[0], _opts())
        assert composed.final_state == direct.final_state
        assert composed.final_context == direct.final_context

    def test_classical_child_returns_flow_into_parent(self):
        f = _file(_classical_parent())
        res = run_composed(f, f.machines[0], _opts())
        assert res.success and res.final_state == "|done>"
        assert res.final_context["out"] == 7  # bound from child return `result`

    def test_arg_bindings_seed_child_context(self):
        # Parent iteration=3 → child seed=3 → returned back into parent `seen`.
        f = _file(_classical_parent(arg="seed=iteration"))
        res = run_composed(f, f.machines[0], _opts())
        assert res.final_context["seen"] == 3

    def test_quantum_shot_batched_aggregate(self):
        fixture = Path(__file__).parent / "fixtures" / "composed_predictive_coder.q.orca.md"
        f = _file(fixture.read_text())
        res = run_composed(f, f.machines[0], _opts())
        child = res.child_runs[0]
        assert child["shots"] == 1024
        assert child["child"] == "QForward"
        prob = child["returns"]["prob_bits_0"]
        hist = child["returns"]["hist_bits_0"]
        assert 0.0 <= prob <= 1.0
        assert hist[0] + hist[1] == 1024
        # bound into the parent context
        assert res.final_context["prob"] == prob

    def test_quantum_single_shot_binds_raw(self):
        src = (
            "# machine P\n## context\n| Field | Type | Default |\n| theta | float | 0.0 |\n| b | int | -1 |\n"
            "## state |i> [initial]\n"
            "## state |s> [invoke: QC(theta=theta)]\n"
            "> returns: b=bits[0]\n"
            "## state |d> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n"
            "| |i> | advance | | |s> | |\n| |s> | advance | | |d> | |\n"
            "\n---\n"
            "# machine QC\n## context\n| Field | Type | Default |\n| theta | float | 0.0 |\n"
            "## state |q0> [initial]\n## state |qm> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n| |q0> | m | | |qm> | meas |\n"
            "## actions\n| Name | Signature | Effect |\n| meas | (qs) -> qs | measure(qs[0]) -> bits[0] |\n"
            "## returns\n| Name | Type | Statistics |\n| bits[0] | bit | |\n"
        )
        f = _file(src)
        res = run_composed(f, f.machines[0], _opts())
        # theta=0 → qubit stays |0> → measured bit 0 (raw)
        assert res.final_context["b"] == 0

    def test_depth_ceiling_guards_recursion(self):
        # A self-invoking machine would recurse forever without the ceiling.
        src = (
            "# machine Loop\n## context\n| Field | Type | Default |\n| x | int | 0 |\n"
            "## state |a> [initial]\n## state |b> [invoke: Loop(x=x)]\n## state |c> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n"
            "| |a> | g | | |b> | |\n| |b> | g | | |c> | |\n"
        )
        f = _file(src)
        with pytest.raises(QIterativeRuntimeError):
            run_composed(f, f.machines[0], _opts(), depth_ceiling=3)
