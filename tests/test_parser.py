"""Tests for Q-Orca markdown parser."""

import math

import pytest

from q_orca.angle import evaluate_angle
from q_orca.parser.markdown_parser import (
    parse_q_orca_markdown,
    parse_markdown_structure,
    ket_to_identifier,
    MdHeading,
    MdTable,
    MdBulletList,
    MdBlockquote,
)


class TestMarkdownStructure:
    def test_parse_heading(self):
        elements = parse_markdown_structure("# machine Foo")
        assert len(elements) == 1
        assert isinstance(elements[0], MdHeading)
        assert elements[0].level == 1
        assert elements[0].text == "machine Foo"

    def test_parse_table(self):
        source = """\
| Name | Value |
|------|-------|
| a    | 1     |
| b    | 2     |
"""
        elements = parse_markdown_structure(source)
        assert len(elements) == 1
        assert isinstance(elements[0], MdTable)
        assert elements[0].headers == ["Name", "Value"]
        assert len(elements[0].rows) == 2
        assert elements[0].rows[0] == ["a", "1"]

    def test_parse_bullet_list(self):
        source = "- alpha\n- beta\n- gamma"
        elements = parse_markdown_structure(source)
        assert len(elements) == 1
        assert isinstance(elements[0], MdBulletList)
        assert elements[0].items == ["alpha", "beta", "gamma"]

    def test_parse_blockquote(self):
        elements = parse_markdown_structure("> some description")
        assert len(elements) == 1
        assert isinstance(elements[0], MdBlockquote)
        assert elements[0].text == "some description"

    def test_skips_code_fences(self):
        source = "# heading\n```\ncode\n```\n## heading2"
        elements = parse_markdown_structure(source)
        assert len(elements) == 2
        assert all(isinstance(e, MdHeading) for e in elements)

    def test_skips_horizontal_rules(self):
        source = "# heading\n---\n## heading2"
        elements = parse_markdown_structure(source)
        assert len(elements) == 2

    def test_table_with_ket_notation(self):
        """Pipes inside ket notation (|00>) should not split table cells."""
        source = """\
| Source | Event | Target |
|--------|-------|--------|
| |00>   | go    | |11>   |
"""
        elements = parse_markdown_structure(source)
        table = elements[0]
        assert table.rows[0][0] == "|00>"
        assert table.rows[0][2] == "|11>"


class TestSemanticParsing:
    def test_parse_machine_name(self, bell_source):
        result = parse_q_orca_markdown(bell_source)
        assert len(result.file.machines) == 1
        assert result.file.machines[0].name == "BellEntangler"

    def test_parse_states(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        state_names = [s.name for s in machine.states]
        assert "|00>" in state_names
        assert "|ψ>" in state_names

    def test_parse_initial_final(self, minimal_source):
        machine = parse_q_orca_markdown(minimal_source).file.machines[0]
        initial = [s for s in machine.states if s.is_initial]
        final = [s for s in machine.states if s.is_final]
        assert len(initial) == 1
        assert initial[0].name == "|0>"
        assert len(final) == 1
        assert final[0].name == "|1>"

    def test_parse_state_expression(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        psi = next(s for s in machine.states if s.name == "|ψ>")
        assert psi.state_expression is not None
        assert "00" in psi.state_expression
        assert "11" in psi.state_expression

    def test_parse_events(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        event_names = [e.name for e in machine.events]
        assert "prepare_H" in event_names
        assert "entangle" in event_names
        assert "measure_done" in event_names

    def test_parse_transitions(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        assert len(machine.transitions) == 4
        t0 = machine.transitions[0]
        assert t0.source == "|00>"
        assert t0.event == "prepare_H"
        assert t0.target == "|+0>"

    def test_parse_guarded_transitions(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        guarded = [t for t in machine.transitions if t.guard]
        assert len(guarded) == 2
        assert all(t.event == "measure_done" for t in guarded)

    def test_parse_actions(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        action_names = [a.name for a in machine.actions]
        assert "apply_H_on_q0" in action_names
        assert "apply_CNOT_q0_to_q1" in action_names

    def test_parse_gate_from_effect(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        h_action = next(a for a in machine.actions if a.name == "apply_H_on_q0")
        assert h_action.gate is not None
        assert h_action.gate.kind == "H"
        assert h_action.gate.targets == [0]

        cnot_action = next(a for a in machine.actions if a.name == "apply_CNOT_q0_to_q1")
        assert cnot_action.gate is not None
        assert cnot_action.gate.kind == "CNOT"
        assert cnot_action.gate.controls == [0]
        assert cnot_action.gate.targets == [1]

    def test_parse_guards(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        assert len(machine.guards) == 2
        guard_names = [g.name for g in machine.guards]
        assert "prob_collapse('00')" in guard_names

    def test_parse_verification_rules(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        rule_kinds = [r.kind for r in machine.verification_rules]
        assert "unitarity" in rule_kinds
        assert "entanglement" in rule_kinds
        assert "completeness" in rule_kinds
        assert "no_cloning" in rule_kinds

    def test_parse_context(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        assert len(machine.context) >= 1
        field_names = [f.name for f in machine.context]
        assert "qubits" in field_names

    def test_parse_effects(self, bell_source):
        machine = parse_q_orca_markdown(bell_source).file.machines[0]
        assert len(machine.effects) >= 1

    def test_no_machine_returns_empty(self):
        result = parse_q_orca_markdown("# not a machine\njust text")
        assert len(result.file.machines) == 0

    def test_first_state_becomes_initial_if_none_marked(self):
        source = """\
# machine Auto

## events
- go

## state |a>
> First state

## state |b>
> Second state

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |a>    | go    |       | |b>    |        |
"""
        machine = parse_q_orca_markdown(source).file.machines[0]
        assert machine.states[0].is_initial is True


class TestKetToIdentifier:
    def test_simple_ket(self):
        assert ket_to_identifier("|00>") == "ket_00"

    def test_greek_ket(self):
        assert ket_to_identifier("|ψ>") == "ket_psi"

    def test_complex_ket(self):
        result = ket_to_identifier("|00_collapsed>")
        assert result.startswith("ket_")
        assert "00" in result


class TestEvaluateAngle:
    """Unit tests for the symbolic angle evaluator."""

    @pytest.mark.parametrize("text,expected", [
        ("1.5708", 1.5708),
        ("-0.5", -0.5),
        ("3.14159", 3.14159),
        ("0", 0.0),
        ("pi", math.pi),
        ("-pi", -math.pi),
        ("pi/2", math.pi / 2),
        ("pi/4", math.pi / 4),
        ("pi/8", math.pi / 8),
        ("-pi/4", -math.pi / 4),
        ("2*pi", 2 * math.pi),
        ("2pi", 2 * math.pi),
        ("-2*pi", -2 * math.pi),
        ("3*pi/4", 3 * math.pi / 4),
        ("-3*pi/4", -3 * math.pi / 4),
    ])
    def test_valid_angle_forms(self, text, expected):
        assert evaluate_angle(text) == pytest.approx(expected, rel=1e-9)

    def test_bare_identifier_raises(self):
        with pytest.raises(ValueError, match="Unrecognized angle expression"):
            evaluate_angle("theta_custom")

    def test_context_ref_raises(self):
        with pytest.raises(ValueError):
            evaluate_angle("ctx.angle")

    @pytest.mark.parametrize("text,expected", [
        ("gamma", 0.5),
        ("-gamma", -0.5),
        ("2*gamma", 1.0),
        ("2gamma", 1.0),
        ("gamma/2", 0.25),
        ("gamma*pi", 0.5 * math.pi),
        ("pi*gamma", 0.5 * math.pi),
        ("-gamma*pi", -0.5 * math.pi),
    ])
    def test_context_reference_forms(self, text, expected):
        ctx = {"gamma": 0.5, "beta": 0.25, "theta": 0.7}
        assert evaluate_angle(text, ctx) == pytest.approx(expected, rel=1e-9)

    def test_pi_literal_shadowing_disabled(self):
        # A field named `pi` must NOT shadow the literal `pi`.
        assert evaluate_angle("pi", {"pi": 99.0}) == math.pi

    def test_unknown_identifier_with_context_lists_available(self):
        with pytest.raises(ValueError) as exc:
            evaluate_angle("zzz", {"gamma": 0.5})
        assert "zzz" in str(exc.value)
        assert "gamma" in str(exc.value)

    def test_no_context_still_rejects_identifier(self):
        with pytest.raises(ValueError):
            evaluate_angle("gamma")


_ROTATION_MACHINE = """\
# machine RotationTest

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]    |

## events
- rotate

## state |0> [initial]
> Ground state

## state |θ> [final]
> Rotated state

## transitions
| Source | Event  | Guard | Target | Action    |
|--------|--------|-------|--------|-----------|
| |0>    | rotate |       | |θ>    | rotate_q0 |

## actions
| Name      | Signature         | Effect            |
|-----------|-------------------|-------------------|
| rotate_q0 | (qs) -> qs        | {effect}          |
"""


class TestRotationGateParsing:
    """Tests for rotation gate parsing in the actions table."""

    def _machine(self, effect: str):
        source = _ROTATION_MACHINE.format(effect=effect)
        return parse_q_orca_markdown(source)

    def test_rx_decimal_angle(self):
        result = self._machine("Rx(qs[0], 1.5708)")
        machine = result.file.machines[0]
        action = machine.actions[0]
        assert action.gate is not None
        assert action.gate.kind == "Rx"
        assert action.gate.targets == [0]
        assert action.gate.parameter == pytest.approx(1.5708)
        assert result.errors == []

    def test_ry_symbolic_pi_over_4(self):
        result = self._machine("Ry(qs[0], pi/4)")
        action = result.file.machines[0].actions[0]
        assert action.gate is not None
        assert action.gate.kind == "Ry"
        assert action.gate.parameter == pytest.approx(math.pi / 4)
        assert result.errors == []

    def test_rz_compound_symbolic(self):
        result = self._machine("Rz(qs[0], 3*pi/4)")
        action = result.file.machines[0].actions[0]
        assert action.gate is not None
        assert action.gate.kind == "Rz"
        assert action.gate.parameter == pytest.approx(3 * math.pi / 4)
        assert result.errors == []

    def test_rx_negative_angle(self):
        result = self._machine("Rx(qs[0], -pi/2)")
        action = result.file.machines[0].actions[0]
        assert action.gate is not None
        assert action.gate.parameter == pytest.approx(-math.pi / 2)
        assert result.errors == []

    def test_wrong_argument_order_produces_error(self):
        result = self._machine("Rx(1.5708, qs[0])")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any("angle-first" in e for e in result.errors)

    def test_unrecognized_symbolic_angle_produces_error(self):
        result = self._machine("Rx(qs[0], theta_custom)")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any("theta_custom" in e for e in result.errors)


_CTX_ANGLE_MACHINE = """\
# machine CtxAngleTest

## context
| Field  | Type        | Default            |
|--------|-------------|--------------------|
| qubits | list<qubit> | [q0, q1]           |
| theta  | float       | 0.7                |
| gamma  | float       | 0.5                |
| beta   | float       | 0.25               |
| frac   | float       | 0.5                |
| n      | int         | 2                  |

## events
- rotate

## state |00> [initial]
> Ground state

## state |out> [final]
> After rotation

## transitions
| Source | Event  | Guard | Target | Action    |
|--------|--------|-------|--------|-----------|
| |00>   | rotate |       | |out>  | apply_gate |

## actions
| Name       | Signature  | Effect          |
|------------|------------|-----------------|
| apply_gate | (qs) -> qs | {effect}        |
"""


class TestContextAngleReferences:
    """Tests for context-field references inside rotation gate angles."""

    def _machine(self, effect: str):
        source = _CTX_ANGLE_MACHINE.format(effect=effect)
        return parse_q_orca_markdown(source)

    def test_bare_identifier(self):
        result = self._machine("Rx(qs[0], theta)")
        action = result.file.machines[0].actions[0]
        assert result.errors == []
        assert action.gate is not None
        assert action.gate.parameter == pytest.approx(0.7)

    def test_negated_identifier(self):
        result = self._machine("Ry(qs[0], -theta)")
        action = result.file.machines[0].actions[0]
        assert result.errors == []
        assert action.gate.parameter == pytest.approx(-0.7)

    def test_integer_scaling(self):
        result = self._machine("Rz(qs[0], 2*beta)")
        action = result.file.machines[0].actions[0]
        assert result.errors == []
        assert action.gate.parameter == pytest.approx(0.5)

    def test_division_by_integer(self):
        result = self._machine("Rx(qs[0], theta/2)")
        action = result.file.machines[0].actions[0]
        assert result.errors == []
        assert action.gate.parameter == pytest.approx(0.35)

    def test_pi_scaling(self):
        result = self._machine("Rz(qs[0], frac*pi)")
        action = result.file.machines[0].actions[0]
        assert result.errors == []
        assert action.gate.parameter == pytest.approx(math.pi / 2)

    def test_two_qubit_gate_with_context_reference(self):
        result = self._machine("RZZ(qs[0], qs[1], gamma)")
        action = result.file.machines[0].actions[0]
        assert result.errors == []
        assert action.gate is not None
        assert action.gate.kind == "RZZ"
        assert action.gate.targets == [0, 1]
        assert action.gate.parameter == pytest.approx(0.5)

    def test_int_field_resolves(self):
        result = self._machine("Rx(qs[0], n)")
        action = result.file.machines[0].actions[0]
        assert result.errors == []
        assert action.gate.parameter == pytest.approx(2.0)

    def test_unknown_identifier_produces_error(self):
        result = self._machine("Rx(qs[0], unknown_field)")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any("unknown_field" in e for e in result.errors)

    def test_non_numeric_field_produces_error(self):
        # `qubits` is list<qubit>, not numeric — must be rejected.
        result = self._machine("Rx(qs[0], qubits)")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any("qubits" in e for e in result.errors)


_GATE_EFFECT_MACHINE = """\
# machine GateEffect

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2, q3] |

## events
- run

## state |s0> [initial]
> start

## state |s1> [final]
> end

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | run   |       | |s1>   | apply  |

## actions
| Name  | Signature  | Effect   |
|-------|------------|----------|
| apply | (qs) -> qs | {effect} |
"""


class TestMCXMCZArityValidation:
    """Regression: `MCX(qs[0], qs[1])` with only two args used to silently
    no-match the parser regex, leaving the transition with no gate and
    surfacing only as a late ValueError from the Qiskit emitter. Task 2.7
    promotes this to a structured parse-time error naming the action and
    required minimum arity.
    """

    def _parse(self, effect: str):
        source = _GATE_EFFECT_MACHINE.format(effect=effect)
        return parse_q_orca_markdown(source)

    def test_mcx_with_two_args_produces_arity_error(self):
        result = self._parse("MCX(qs[0], qs[1])")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any("MCX" in e and "at least 3" in e for e in result.errors), result.errors
        # Error names the action so the user can locate it.
        assert any("apply" in e for e in result.errors)

    def test_mcz_with_two_args_produces_arity_error(self):
        result = self._parse("MCZ(qs[0], qs[1])")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any("MCZ" in e and "at least 3" in e for e in result.errors), result.errors

    def test_mcx_with_three_args_still_parses(self):
        result = self._parse("MCX(qs[0], qs[1], qs[2])")
        action = result.file.machines[0].actions[0]
        assert action.gate is not None
        assert action.gate.kind == "MCX"
        assert action.gate.controls == [0, 1]
        assert action.gate.targets == [2]

    def test_mcz_with_four_args_still_parses(self):
        result = self._parse("MCZ(qs[0], qs[1], qs[2], qs[3])")
        action = result.file.machines[0].actions[0]
        assert action.gate is not None
        assert action.gate.kind == "MCZ"
        assert action.gate.controls == [0, 1, 2]
        assert action.gate.targets == [3]

    def test_mcx_arity_error_does_not_double_fire_unknown_gate_warning(self):
        # The wrong-arity MCX effect also matches `_looks_like_gate_call`,
        # so without a guard the unrecognized-gate warning would fire in
        # addition to the specific arity error. Only the more specific
        # diagnostic should surface.
        result = self._parse("MCX(qs[0], qs[1])")
        assert any("MCX" in e and "at least 3" in e for e in result.errors)
        assert not any("does not match any known gate" in e for e in result.errors), (
            f"unrecognized-gate warning double-fired alongside MCX arity error: {result.errors}"
        )

    def test_mcz_arity_error_does_not_double_fire_unknown_gate_warning(self):
        result = self._parse("MCZ(qs[0], qs[1])")
        assert any("MCZ" in e and "at least 3" in e for e in result.errors)
        assert not any("does not match any known gate" in e for e in result.errors), (
            f"unrecognized-gate warning double-fired alongside MCZ arity error: {result.errors}"
        )


class TestUnrecognizedGateEffectWarning:
    """Regression: a typo like `MCXY(...)` used to silently produce
    `action.gate == None` and the verifier skipped the transition
    entirely. Task 2.8 emits a structured warning so typos surface early
    instead of becoming silent test gaps.
    """

    def _parse(self, effect: str):
        source = _GATE_EFFECT_MACHINE.format(effect=effect)
        return parse_q_orca_markdown(source)

    def test_typo_in_gate_name_produces_warning(self):
        result = self._parse("MCXY(qs[0], qs[1], qs[2])")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any(
            "MCXY" in e and "does not match any known gate" in e
            for e in result.errors
        ), result.errors

    def test_unknown_multi_qubit_gate_name_produces_warning(self):
        # Multi-arg typos have no fallback — the generic single-qubit regex
        # requires exactly one argument, so e.g. `Flip(qs[0], qs[1])` returns
        # None across all gate patterns and must warn.
        result = self._parse("Flip(qs[0], qs[1])")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any("does not match any known gate" in e for e in result.errors), result.errors

    def test_known_gate_does_not_trigger_warning(self):
        result = self._parse("H(qs[0])")
        action = result.file.machines[0].actions[0]
        assert action.gate is not None
        assert not any("does not match any known gate" in e for e in result.errors)

    def test_measurement_effect_does_not_trigger_warning(self):
        result = self._parse("measure(qs[0])")
        # Measurements go through a different parser; the unknown-gate
        # warning must not false-positive on them.
        assert not any("does not match any known gate" in e for e in result.errors)

    def test_empty_effect_does_not_trigger_warning(self):
        result = self._parse("")
        assert not any("does not match any known gate" in e for e in result.errors)
