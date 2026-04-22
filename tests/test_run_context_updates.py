"""Tests for the iterative runtime (`run-context-updates` change).

Currently covers:
- Section 2: guard evaluator (`q_orca.runtime.guards`).
- Section 3: context-mutation interpreter (`q_orca.runtime.context_ops`).

Further sections (iterative walker, runtime dispatch, verifier warning,
end-to-end QPC) extend this file.
"""

import pytest

from q_orca.ast import (
    CollapseOutcome,
    QContextMutation,
    QEffectContextUpdate,
    QGuardAnd,
    QGuardCompare,
    QGuardFalse,
    QGuardFidelity,
    QGuardNot,
    QGuardOr,
    QGuardProbability,
    QGuardTrue,
    ValueRef,
    VariableRef,
)
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.runtime.context_ops import apply
from q_orca.runtime.guards import evaluate_guard
from q_orca.runtime.iterative import simulate_iterative
from q_orca.runtime.types import QIterativeRuntimeError, QIterativeSimulationOptions


# ============================================================
# Section 2: guard evaluator
# ============================================================


def _ctx_lt(field: str, literal) -> QGuardCompare:
    return QGuardCompare(
        op="lt",
        left=VariableRef(path=["ctx", field]),
        right=ValueRef(type="number", value=float(literal)),
    )


def _ctx_eq(field: str, literal) -> QGuardCompare:
    return QGuardCompare(
        op="eq",
        left=VariableRef(path=["ctx", field]),
        right=ValueRef(type="number", value=float(literal)),
    )


class TestGuardEvaluator:
    def test_true_and_false(self):
        assert evaluate_guard(QGuardTrue(), {}, {}) is True
        assert evaluate_guard(QGuardFalse(), {}, {}) is False

    def test_none_expr_is_true(self):
        assert evaluate_guard(None, {}, {}) is True

    def test_ctx_field_compare(self):
        ctx = {"iteration": 5}
        assert evaluate_guard(_ctx_lt("iteration", 10), ctx, {}) is True
        assert evaluate_guard(_ctx_lt("iteration", 5), ctx, {}) is False
        assert evaluate_guard(_ctx_eq("iteration", 5), ctx, {}) is True

    def test_bare_field_reference_resolves_like_ctx_prefixed(self):
        """`max_iter` on the RHS of a compare is parsed as a string
        ValueRef; the evaluator should look it up in ctx."""
        ctx = {"iteration": 3, "max_iter": 10}
        expr = QGuardCompare(
            op="lt",
            left=VariableRef(path=["ctx", "iteration"]),
            right=ValueRef(type="string", value="max_iter"),
        )
        assert evaluate_guard(expr, ctx, {}) is True

    def test_list_element_reference(self):
        ctx = {"theta": [0.0, 0.25, 0.5]}
        expr = QGuardCompare(
            op="ge",
            left=VariableRef(path=["ctx", "theta", "1"]),
            right=ValueRef(type="number", value=0.2),
        )
        assert evaluate_guard(expr, ctx, {}) is True

    def test_boolean_combos(self):
        ctx = {"a": 1, "b": 2}
        a_eq_1 = _ctx_eq("a", 1)
        b_eq_2 = _ctx_eq("b", 2)
        b_eq_5 = _ctx_eq("b", 5)

        assert evaluate_guard(QGuardAnd(left=a_eq_1, right=b_eq_2), ctx, {}) is True
        assert evaluate_guard(QGuardAnd(left=a_eq_1, right=b_eq_5), ctx, {}) is False
        assert evaluate_guard(QGuardOr(left=a_eq_1, right=b_eq_5), ctx, {}) is True
        assert evaluate_guard(QGuardNot(expr=a_eq_1), ctx, {}) is False
        assert evaluate_guard(QGuardNot(expr=b_eq_5), ctx, {}) is True

    def test_nested_boolean(self):
        ctx = {"x": 1, "y": 2, "z": 3}
        expr = QGuardAnd(
            left=QGuardOr(left=_ctx_eq("x", 1), right=_ctx_eq("y", 99)),
            right=QGuardNot(expr=_ctx_eq("z", 99)),
        )
        assert evaluate_guard(expr, ctx, {}) is True

    def test_missing_field_raises(self):
        expr = _ctx_eq("missing", 1)
        with pytest.raises(QIterativeRuntimeError, match="unknown context field"):
            evaluate_guard(expr, {"other": 1}, {})

    def test_approx_op(self):
        ctx = {"angle": 0.30000000000001}
        expr = QGuardCompare(
            op="approx",
            left=VariableRef(path=["ctx", "angle"]),
            right=ValueRef(type="number", value=0.3),
        )
        assert evaluate_guard(expr, ctx, {}) is True

    def test_probability_guard_reads_last_bit(self):
        expr = QGuardProbability(
            outcome=CollapseOutcome(bitstring="1", probability=0.5)
        )
        # Only bit 0 measured so far.
        assert evaluate_guard(expr, {}, {0: 1}) is True
        assert evaluate_guard(expr, {}, {0: 0}) is False

    def test_probability_guard_without_bits_raises(self):
        expr = QGuardProbability(
            outcome=CollapseOutcome(bitstring="0", probability=0.5)
        )
        with pytest.raises(QIterativeRuntimeError, match="before any measurement"):
            evaluate_guard(expr, {}, {})

    def test_probability_guard_multibit_rejected(self):
        expr = QGuardProbability(
            outcome=CollapseOutcome(bitstring="11", probability=0.5)
        )
        with pytest.raises(QIterativeRuntimeError, match="multi-bit outcomes"):
            evaluate_guard(expr, {}, {0: 1})

    def test_fidelity_guard_rejected(self):
        expr = QGuardFidelity(state_a="|0>", state_b="|0>", op="eq", value=1.0)
        with pytest.raises(QIterativeRuntimeError, match="fidelity guards"):
            evaluate_guard(expr, {}, {})


# ============================================================
# Section 3: context-mutation interpreter
# ============================================================


def _scalar(field: str, op: str, literal: float) -> QContextMutation:
    return QContextMutation(
        target_field=field,
        target_idx=None,
        op=op,
        rhs_literal=literal,
    )


def _list_elem(field: str, idx: int, op: str, literal: float) -> QContextMutation:
    return QContextMutation(
        target_field=field,
        target_idx=idx,
        op=op,
        rhs_literal=literal,
    )


def _field_rhs(field: str, op: str, rhs_field: str) -> QContextMutation:
    return QContextMutation(
        target_field=field,
        target_idx=None,
        op=op,
        rhs_field=rhs_field,
    )


class TestContextMutationInterpreter:
    def test_unconditional_scalar_increment(self):
        effect = QEffectContextUpdate(
            then_mutations=[_scalar("iteration", "+=", 1)],
        )
        out = apply(effect, {"iteration": 3}, {})
        assert out == {"iteration": 4}

    def test_list_element_plus_equal(self):
        effect = QEffectContextUpdate(
            then_mutations=[_list_elem("theta", 1, "+=", 0.05)],
        )
        out = apply(effect, {"theta": [0.1, 0.2, 0.3]}, {})
        assert out == {"theta": [0.1, 0.25, 0.3]}

    def test_list_element_minus_equal(self):
        effect = QEffectContextUpdate(
            then_mutations=[_list_elem("theta", 0, "-=", 0.1)],
        )
        out = apply(effect, {"theta": [0.5, 0.5]}, {})
        assert out == {"theta": [pytest.approx(0.4), 0.5]}

    def test_list_element_assign(self):
        effect = QEffectContextUpdate(
            then_mutations=[_list_elem("theta", 2, "=", 9.0)],
        )
        out = apply(effect, {"theta": [0.0, 0.0, 0.0]}, {})
        assert out == {"theta": [0.0, 0.0, 9.0]}

    def test_rhs_context_field_reference(self):
        effect = QEffectContextUpdate(
            then_mutations=[_field_rhs("iteration", "+=", "step")],
        )
        out = apply(effect, {"iteration": 5, "step": 2}, {})
        assert out["iteration"] == 7

    def test_then_only_conditional(self):
        effect = QEffectContextUpdate(
            bit_idx=0,
            bit_value=1,
            then_mutations=[_scalar("counter", "+=", 1)],
        )
        # Bit matches → then branch applies.
        assert apply(effect, {"counter": 0}, {0: 1}) == {"counter": 1}
        # Bit mismatches → empty else branch → no change.
        assert apply(effect, {"counter": 0}, {0: 0}) == {"counter": 0}

    def test_then_plus_else_conditional(self):
        effect = QEffectContextUpdate(
            bit_idx=0,
            bit_value=1,
            then_mutations=[_list_elem("theta", 0, "-=", 0.01)],
            else_mutations=[_list_elem("theta", 0, "+=", 0.01)],
        )
        agree = apply(effect, {"theta": [0.5]}, {0: 1})
        disagree = apply(effect, {"theta": [0.5]}, {0: 0})
        assert agree["theta"][0] == pytest.approx(0.49)
        assert disagree["theta"][0] == pytest.approx(0.51)

    def test_snapshot_immutability(self):
        original = {"theta": [0.1, 0.2]}
        effect = QEffectContextUpdate(
            then_mutations=[_list_elem("theta", 0, "=", 9.9)],
        )
        out = apply(effect, original, {})
        assert original == {"theta": [0.1, 0.2]}
        assert out == {"theta": [9.9, 0.2]}
        assert out["theta"] is not original["theta"]

    def test_missing_field_raises(self):
        effect = QEffectContextUpdate(
            then_mutations=[_scalar("ghost", "+=", 1)],
        )
        with pytest.raises(QIterativeRuntimeError, match="unknown field"):
            apply(effect, {"real": 0}, {})

    def test_missing_bit_raises_when_conditional(self):
        effect = QEffectContextUpdate(
            bit_idx=0,
            bit_value=1,
            then_mutations=[_scalar("x", "+=", 1)],
        )
        with pytest.raises(QIterativeRuntimeError, match="no measurement"):
            apply(effect, {"x": 0}, {})

    def test_type_mismatch_on_arithmetic(self):
        effect = QEffectContextUpdate(
            then_mutations=[_scalar("label", "+=", 1.0)],
        )
        with pytest.raises(QIterativeRuntimeError, match="numeric target"):
            apply(effect, {"label": "hello"}, {})

    def test_list_oob_raises(self):
        effect = QEffectContextUpdate(
            then_mutations=[_list_elem("theta", 5, "=", 0.0)],
        )
        with pytest.raises(QIterativeRuntimeError, match="beyond length"):
            apply(effect, {"theta": [0.0, 0.0]}, {})


# ============================================================
# Section 4: iterative walker
# ============================================================


def _parse_machine(source: str):
    result = parse_q_orca_markdown(source)
    assert result.errors == [], f"parse errors: {result.errors}"
    return result.file.machines[0]


_QPC_MINIMAL = """\
# machine QPCMinimal

## context
| Field   | Type        | Default      |
|---------|-------------|--------------|
| qubits  | list<qubit> | [q0, q1, q2] |
| bits    | list<bit>   | [b0]         |
| theta_0 | float       | 0.5          |
| theta_1 | float       | 0.3          |
| theta_2 | float       | 0.7          |

## events
- prepare_prior
- encode_data
- compute_error
- measure_error

## state |init> [initial]
> start
## state |prior_ready>
## state |joined>
## state |error_extracted>
## state |bit_read> [final]

## transitions
| Source             | Event          | Guard | Target             | Action              |
|--------------------|----------------|-------|--------------------|---------------------|
| |init>             | prepare_prior  |       | |prior_ready>      | apply_ansatz        |
| |prior_ready>      | encode_data    |       | |joined>           | encode_datum        |
| |joined>           | compute_error  |       | |error_extracted>  | parity_to_ancilla   |
| |error_extracted>  | measure_error  |       | |bit_read>         | measure_ancilla     |

## actions
| Name              | Signature  | Effect                                              |
|-------------------|------------|-----------------------------------------------------|
| apply_ansatz      | (qs) -> qs | Ry(qs[0], theta_0); Rz(qs[0], theta_1); Rx(qs[0], theta_2) |
| encode_datum      | (qs) -> qs | H(qs[1])                                            |
| parity_to_ancilla | (qs) -> qs | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[2])              |
| measure_ancilla   | (qs) -> qs | measure(qs[2]) -> bits[0]                           |
"""


_QPC_LEARNING = """\
# machine QPCLearning

## context
| Field     | Type        | Default      |
|-----------|-------------|--------------|
| qubits    | list<qubit> | [q0, q1, q2] |
| bits      | list<bit>   | [b0]         |
| theta_0   | float       | 0.5          |
| theta_1   | float       | 0.3          |
| theta_2   | float       | 0.7          |
| eta       | float       | 0.05         |
| iteration | int         | 0            |
| max_iter  | int         | 3            |

## events
- prepare_prior
- encode_data
- compute_error
- measure_error
- gradient_step
- loop_back
- finalize

## state |init> [initial]
## state |prior_ready>
## state |joined>
## state |error_extracted>
## state |measured>
## state |model_updated>
## state |converged> [final]

## guards
| Name     | Expression                |
|----------|---------------------------|
| continue | ctx.iteration < max_iter  |
| done     | ctx.iteration >= max_iter |

## transitions
| Source             | Event          | Guard    | Target             | Action             |
|--------------------|----------------|----------|--------------------|--------------------|
| |init>             | prepare_prior  |          | |prior_ready>      | apply_ansatz       |
| |prior_ready>      | encode_data    |          | |joined>           | encode_datum       |
| |joined>           | compute_error  |          | |error_extracted>  | parity_to_ancilla  |
| |error_extracted>  | measure_error  |          | |measured>         | measure_ancilla    |
| |measured>         | gradient_step  |          | |model_updated>    | gradient_step      |
| |model_updated>    | loop_back      | continue | |prior_ready>      | tick               |
| |model_updated>    | finalize       | done     | |converged>        |                    |

## actions
| Name              | Signature   | Effect                                              |
|-------------------|-------------|-----------------------------------------------------|
| apply_ansatz      | (qs) -> qs  | Ry(qs[0], theta_0); Rz(qs[0], theta_1); Rx(qs[0], theta_2) |
| encode_datum      | (qs) -> qs  | H(qs[1])                                            |
| parity_to_ancilla | (qs) -> qs  | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[2])              |
| measure_ancilla   | (qs) -> qs  | measure(qs[2]) -> bits[0]                           |
| gradient_step     | (ctx) -> ctx | if bits[0] == 1: theta_0 -= eta else: theta_0 += eta |
| tick              | (ctx) -> ctx | iteration += 1                                     |
"""


class TestIterativeWalker:
    def test_qpc_minimal_runs_to_final(self):
        machine = _parse_machine(_QPC_MINIMAL)
        opts = QIterativeSimulationOptions(shots=1, inner_shots=1, seed_simulator=42)
        result = simulate_iterative(machine, opts)
        assert result.success
        assert result.final_state == "|bit_read>"
        assert len(result.trace) == 4
        assert all(tr.measurement_bits for tr in result.trace)
        # Iteration indices should be 0..3 (one per transition).
        assert [tr.iteration for tr in result.trace] == [0, 1, 2, 3]

    def test_initial_context_from_defaults(self):
        machine = _parse_machine(_QPC_MINIMAL)
        opts = QIterativeSimulationOptions(shots=1, inner_shots=1, seed_simulator=1)
        result = simulate_iterative(machine, opts)
        # Non-mutating machine: final ctx matches initial defaults.
        assert result.final_context == {"theta_0": 0.5, "theta_1": 0.3, "theta_2": 0.7}

    def test_qpc_learning_loop_converges(self):
        machine = _parse_machine(_QPC_LEARNING)
        opts = QIterativeSimulationOptions(shots=1, inner_shots=1, seed_simulator=7)
        result = simulate_iterative(machine, opts)
        assert result.success
        assert result.final_state == "|converged>"
        # Iteration counter should have advanced max_iter times.
        assert result.final_context["iteration"] == 3
        # theta_0 should have drifted away from its default at least once
        # during the loop (the final value may coincidentally land back on
        # 0.5 for seeds where +/- updates cancel).
        theta_history = [
            tr.context_snapshot.get("theta_0") for tr in result.trace
        ]
        assert any(t != pytest.approx(0.5) for t in theta_history)

    def test_iteration_ceiling_trips(self):
        machine = _parse_machine(_QPC_LEARNING)
        opts = QIterativeSimulationOptions(
            shots=1, inner_shots=1, seed_simulator=7, iteration_ceiling=3
        )
        with pytest.raises(QIterativeRuntimeError, match="iteration ceiling"):
            simulate_iterative(machine, opts)

    def test_seeded_reproducibility(self):
        machine = _parse_machine(_QPC_LEARNING)
        opts = QIterativeSimulationOptions(shots=1, inner_shots=1, seed_simulator=123)
        a = simulate_iterative(machine, opts)
        b = simulate_iterative(machine, opts)
        assert a.aggregate_counts == b.aggregate_counts
        assert a.final_context == b.final_context

    def test_record_trace_off(self):
        machine = _parse_machine(_QPC_MINIMAL)
        opts = QIterativeSimulationOptions(
            shots=1, inner_shots=1, seed_simulator=42, record_trace=False
        )
        result = simulate_iterative(machine, opts)
        assert result.trace == []
