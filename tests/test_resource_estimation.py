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


def test_cache_entry_evicted_when_machine_gc_collected():
    import gc

    from q_orca.compiler.resources import _RESOURCE_CACHE

    m = _load("bell-entangler.q.orca.md")
    estimate_resources(m)
    machine_id = id(m)
    assert machine_id in _RESOURCE_CACHE

    del m
    gc.collect()

    assert machine_id not in _RESOURCE_CACHE, (
        "weakref.finalize must drop the cache entry once the machine is "
        "collected — otherwise a future allocation reusing the same id "
        "gets a stale cache hit."
    )


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
    src = """\
# machine NoResources

## context
| Field | Type | Default |
| qubits | list<qubit> | [q0, q1] |

## state |0> [initial]

## state |1> [final]

## transitions
| Source | Event | Guard | Target | Action |
| |0> | go | | |1> | a |

## actions
| Name | Signature | Effect |
| a | (qs) -> qs | H(qs[0]) |
"""
    m = parse_q_orca_markdown(src).file.machines[0]
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


def test_compound_conditional_counts_as_single_gate():
    """A compound `if bits[0]==1 and bits[1]==0 and bits[2]==1: X(qs[3])`
    must contribute 1 to top-level `count_ops()` (the outer `if_else`
    op) — the conjunction is classical control flow and SHALL NOT
    inflate the un-transpiled op count past the gate inside the
    conditional. We assert against `count_ops()` directly because
    Qiskit 2.4+'s default transpile target rejects `if_else`, so
    `estimate_resources()` is exercised separately on a clean
    no-conditional fixture.
    """
    pytest.importorskip("qiskit", reason="qiskit not installed")

    from q_orca.compiler.qiskit import build_circuit_for_iteration

    src = """\
# machine ThreeClauseConditional

## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0, q1, q2, q3] |
| bits | list<bit> | [b0, b1, b2] |

## events
- seed
- m0
- m1
- m2
- correct

## state |a> [initial]
## state |b>
## state |c>
## state |d>
## state |e>
## state |f> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |a> | seed | | |b> | seed |
| |b> | m0 | | |c> | meas0 |
| |c> | m1 | | |d> | meas1 |
| |d> | m2 | | |e> | meas2 |
| |e> | correct | | |f> | corr_compound |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| seed | (qs) -> qs | H(qs[0]) |
| meas0 | (qs) -> qs | measure(qs[0]) -> bits[0] |
| meas1 | (qs) -> qs | measure(qs[1]) -> bits[1] |
| meas2 | (qs) -> qs | measure(qs[2]) -> bits[2] |
| corr_compound | (qs) -> qs | if bits[0] == 1 and bits[1] == 0 and bits[2] == 1: X(qs[3]) |
"""
    m = parse_q_orca_markdown(src).file.machines[0]
    qc = build_circuit_for_iteration(m, {}, list(m.actions))
    ops = qc.count_ops()
    # 1 H + 3 measures + 1 outer if_else (compound nests fold into one
    # top-level op) = 5. Critically, the 3 clauses do NOT inflate this
    # to 7 (which would happen if every nested if_test were a separate
    # top-level op).
    assert sum(ops.values()) == 5
    assert ops.get("if_else", 0) == 1
    assert ops.get("h", 0) == 1
    assert ops.get("measure", 0) == 3
    # No top-level X — the X lives inside the if_else block.
    assert ops.get("x", 0) == 0
    assert ops.get("cx", 0) == 0
    assert ops.get("t", 0) == 0


def test_bit_flip_syndrome_compound_conditional_op_count():
    """Bit-flip-syndrome has three compound conditional corrections;
    each must collapse to a single top-level `if_else` op. If the
    compiler unrolled clauses, the count would jump from 3 to 6.
    """
    pytest.importorskip("qiskit", reason="qiskit not installed")

    from q_orca.compiler.qiskit import build_circuit_for_iteration

    m = _load("bit-flip-syndrome.q.orca.md")
    qc = build_circuit_for_iteration(m, {}, list(m.actions))
    ops = qc.count_ops()
    # 4 CNOT (entangle) + 2 measure + 3 if_else (one per compound
    # correction) = 9. If compound conditionals were unrolled per
    # clause, this would jump to 13.
    assert sum(ops.values()) == 9
    assert ops.get("cx", 0) == 4
    assert ops.get("measure", 0) == 2
    assert ops.get("if_else", 0) == 3
    # No top-level X gates — they all live inside if_else blocks.
    assert ops.get("x", 0) == 0


def test_estimate_resources_single_conditional_machine():
    """Single-condition correction (`if bits[0] == 1: X(qs[1])`).

    `estimate_resources` must complete without `TranspilerError` even
    when the circuit contains an `if_else` op — under qiskit ≥ 2.4 the
    `BasisTranslator` rejects circuits containing control-flow ops
    when transpiling to a basis like `['u3', 'cx']` that doesn't
    enumerate them. Pin the un-transpiled count shape (1 H + 1 measure
    + 1 if_else) and the basis-derived counts (no cx / t in this
    circuit since the conditional body holds an X).
    """
    src = """\
# machine SingleCond

## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0, q1] |
| bits | list<bit> | [b0] |

## events
- prepare
- measure_q0
- correct

## state |a> [initial]
## state |b>
## state |c>
## state |d> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |a> | prepare | | |b> | seed |
| |b> | measure_q0 | | |c> | meas0 |
| |c> | correct | | |d> | corr |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| seed | (qs) -> qs | H(qs[0]) |
| meas0 | (qs) -> qs | measure(qs[0]) -> bits[0] |
| corr | (qs) -> qs | if bits[0] == 1: X(qs[1]) |
"""
    m = parse_q_orca_markdown(src).file.machines[0]
    r = estimate_resources(m)
    # 1 H + 1 measure + 1 if_else = 3 top-level ops.
    assert r["gate_count"] == 3
    # No top-level cx or T; the conditional's X lives inside the
    # if_else body and is not a cx/t under either basis decomposition.
    assert r["cx_count"] == 0
    assert r["t_count"] == 0
    assert r["logical_qubits"] == 2


def test_estimate_resources_compound_conditional_machine():
    """Bit-flip-syndrome's three compound conditional corrections
    (each `if bits[0]==X and bits[1]==Y: X(qs[k])` nesting an inner
    `if_else` inside an outer `if_else` per
    `extend-conditional-gate-compound-bits`).

    Before §5.17 this raised `TranspilerError` under qiskit ≥ 2.4 —
    the worked-around tests in this file checked `count_ops()`
    directly on the un-transpiled circuit to dodge it. With the
    structural fallback in `_count_basis_ops`, `estimate_resources`
    completes and the basis-derived counts agree with the
    un-transpiled-circuit shape.
    """
    m = _load("bit-flip-syndrome.q.orca.md")
    r = estimate_resources(m)
    # 4 cx (entangle) + 2 measure + 3 outer if_else = 9 top-level ops.
    assert r["gate_count"] == 9
    # 4 top-level cx gates from the entanglement ladder; the if_else
    # bodies hold X gates only, which contribute 0 to cx_count.
    assert r["cx_count"] == 4
    # No T gates anywhere in the circuit.
    assert r["t_count"] == 0
    assert r["logical_qubits"] == 5


def test_count_basis_ops_fallback_descends_into_if_else_bodies(monkeypatch):
    """Force the top-level basis transpile to raise `TranspilerError`
    so the structural fallback in `_count_basis_ops` is exercised
    regardless of qiskit version. The helper must:

      • count the `if_else` op itself once at the top level
        (matching `count_ops()` semantics on qiskit 2.3.x);
      • count the `cx` *inside* the `if_else` body via recursion
        (the body's transpile to `['u3','cx']` succeeds because the
        block has no nested control flow); and
      • count the `measure` at top level via the flat-only sub-circuit.
    """
    pytest.importorskip("qiskit", reason="qiskit not installed")

    import qiskit
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
    from qiskit.transpiler.exceptions import TranspilerError

    from q_orca.compiler.resources import _count_basis_ops

    q = QuantumRegister(2, "q")
    c = ClassicalRegister(1, "c")
    qc = QuantumCircuit(q, c)
    qc.measure(0, 0)
    with qc.if_test((c, 1)):
        qc.cx(0, 1)

    real_transpile = qiskit.transpile
    calls = {"n": 0}

    def fake_transpile(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TranspilerError("forced for test")
        return real_transpile(*args, **kwargs)

    monkeypatch.setattr(qiskit, "transpile", fake_transpile)

    counts = _count_basis_ops(qc, ["u3", "cx"])

    assert counts["if_else"] == 1
    assert counts["measure"] == 1
    assert counts["cx"] == 1, (
        "cx inside the if_else body must be counted via the recursive "
        "block walk — without the descent it would silently report 0."
    )
