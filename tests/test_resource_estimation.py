"""Tests for q_orca.compiler.resources."""

from pathlib import Path
from unittest.mock import patch

import pytest

from q_orca.compiler.resources import (
    clear_resource_cache,
    compile_with_resources,
    estimate_resources,
    format_resource_report,
)
from q_orca.parser.markdown_parser import parse_q_orca_markdown


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load(name: str):
    src = (EXAMPLES / name).read_text()
    result = parse_q_orca_markdown(src)
    return result.file.machines[0]


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_resource_cache()
    yield
    clear_resource_cache()


def test_bell_pair_resources():
    m = _load("bell-entangler.q.orca.md")
    r = estimate_resources(m)
    assert r["gate_count"] == 2
    assert r["depth"] == 2
    assert r["cx_count"] == 1
    assert r["t_count"] == 0
    assert r["logical_qubits"] == 2


def test_ghz_resources():
    m = _load("ghz-state.q.orca.md")
    r = estimate_resources(m)
    assert r["gate_count"] == 3
    assert r["depth"] == 3
    assert r["cx_count"] == 2
    assert r["t_count"] == 0
    assert r["logical_qubits"] == 3


def test_qaoa_maxcut_resources():
    m = _load("qaoa-maxcut.q.orca.md")
    r = estimate_resources(m)
    assert r["gate_count"] == 9
    assert r["depth"] == 5
    assert r["cx_count"] == 6
    assert r["logical_qubits"] == 3
    # t_count comes out via the Clifford+T decomposition of QAOA's
    # parameterized rotations; pin a sane lower bound rather than the
    # exact value, which depends on Qiskit's internal synthesis.
    assert r["t_count"] > 0


def test_memoization_returns_same_dict_no_retranspile():
    m = _load("bell-entangler.q.orca.md")
    first = estimate_resources(m)
    with patch("qiskit.transpile") as transpile_spy:
        second = estimate_resources(m)
        assert transpile_spy.call_count == 0
    assert second is first


def test_unknown_metric_in_resources_section():
    src = """\
# machine Foo

## state |0> [initial]

## state |1> [final]

## transitions
| Source | Event | Guard | Target | Action |
| |0> | go | | |1> | a |

## actions
| Name | Signature |
| a | (qs) -> qs |

## resources
| Metric | Basis |
| nonsense | logical |
"""
    result = parse_q_orca_markdown(src)
    assert any("unknown_resource_metric" in e for e in result.errors)


def test_no_resources_section_uses_default_metrics():
    m = _load("bell-entangler.q.orca.md")
    assert m.resource_metrics == []
    _, resources = compile_with_resources(m)
    assert set(resources.keys()) == {
        "gate_count", "depth", "cx_count", "t_count", "logical_qubits",
    }


def test_format_resource_report_pass_and_fail():
    from q_orca.ast import Invariant
    m = _load("bell-entangler.q.orca.md")
    m.invariants.extend([
        Invariant(kind="resource", qubits=[], op="le", value=2, metric="cx_count"),
        Invariant(kind="resource", qubits=[], op="le", value=0, metric="gate_count"),
    ])
    r = estimate_resources(m)
    report = format_resource_report(m, r)
    assert "cx_count" in report and "<= 2" in report and "✓" in report
    assert "gate_count" in report and "<= 0" in report and "✗" in report
