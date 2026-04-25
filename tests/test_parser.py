"""Tests for Q-Orca markdown parser."""

import math

import pytest

from q_orca.angle import evaluate_angle
from q_orca.parser.markdown_parser import (
    parse_q_orca_markdown,
    parse_markdown_structure,
    ket_to_identifier,
    _split_top_level_commas,
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


class TestInlineTableHeading:
    """Section headings with inline table-header rows must still be recognized.

    Users occasionally type `## context | Field | Type | Default |` (the header
    row glued onto the heading). Before the fix this was silently ignored,
    producing 0 parsed fields; now the parser recovers and emits a warning.
    """

    CLEAN = """\
# machine T
## context
| Field | Type | Default |
|-------|------|---------|
| x | int | 0 |
| y | float | 1.5 |

## state |0> [initial]
"""

    INLINE = """\
# machine T
## context | Field | Type | Default |
|-------|------|---------|
| x | int | 0 |
| y | float | 1.5 |

## state |0> [initial]
"""

    def test_clean_and_inline_produce_equal_context(self):
        clean = parse_q_orca_markdown(self.CLEAN).file.machines[0]
        inline = parse_q_orca_markdown(self.INLINE).file.machines[0]
        assert [(f.name, f.default_value) for f in clean.context] == \
               [(f.name, f.default_value) for f in inline.context]
        assert len(clean.context) == 2

    def test_clean_form_emits_no_warning(self):
        result = parse_q_orca_markdown(self.CLEAN)
        assert result.errors == []

    def test_inline_form_emits_warning(self):
        result = parse_q_orca_markdown(self.INLINE)
        assert any("inline table content" in e for e in result.errors)

    def test_inline_form_recognized_for_all_known_sections(self):
        """All 7 pipe-table section keywords recover from inline-header gluing."""
        source = """\
# machine T
## context | Field | Type | Default |
|-------|------|---------|
| x | int | 0 |

## state |0> [initial]

## transitions | Source | Event | Guard | Target | Action |
|---|---|---|---|---|
| |0> | go | | |0> | noop |

## guards | Name | Expression |
|---|---|
| always | ctx.x == 0 |

## actions | Name | Signature | Effect |
|---|---|---|
| noop | (qs) -> qs | |

## effects | Name | Input | Output |
|---|---|---|
| myfx | a | b |
"""
        result = parse_q_orca_markdown(source)
        m = result.file.machines[0]
        assert len(m.context) == 1
        assert len(m.transitions) == 1
        assert len(m.guards) == 1
        assert len(m.actions) == 1
        assert len(m.effects) == 1
        # One warning per affected section heading.
        assert sum("inline table content" in e for e in result.errors) == 5

    def test_state_heading_with_ket_is_not_stripped(self):
        """`## state |00>` must NOT be treated as inline-header misuse."""
        source = "# machine T\n## state |00> [initial]\n## state |11> [final]\n"
        result = parse_q_orca_markdown(source)
        assert result.errors == []
        names = [s.name for s in result.file.machines[0].states]
        assert names == ["|00>", "|11>"]


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

    def test_underscore_typo_in_gate_name_triggers_warning(self):
        # `U_3(...)` (underscore typo for `U3`) should still surface as a
        # typo warning rather than passing through as an unflagged effect.
        # The `_looks_like_gate_call` regex must accept `_` in the leading
        # identifier for this to fire.
        result = self._parse("U_3(qs[0], qs[1])")
        assert any("does not match any known gate" in e for e in result.errors), result.errors

    def test_warning_lists_known_gates_from_canonical_set(self):
        # The known-gate list in the warning is built from
        # `KNOWN_UNITARY_GATES` at module load, so the recently-added
        # `CCZ`, `MCX`, and `MCZ` (and `H`, `CNOT`, etc.) all appear.
        result = self._parse("Flip(qs[0], qs[1])")
        warning = next(
            (e for e in result.errors if "does not match any known gate" in e),
            None,
        )
        assert warning is not None, result.errors
        for name in ("H", "CNOT", "CCZ", "MCX", "MCZ", "RXX"):
            assert name in warning, (name, warning)


class TestCSWAPArityValidation:
    """Regression: `CSWAP(qs[0], qs[1])` with only two args used to fall
    through to the generic looks-like-gate warning, while the same arity
    bug for `MCX`/`MCZ` got a structured error. Task 1.3 in the
    tech-debt-backlog change adds a CSWAP-specific arity branch so all
    multi-controlled gates surface arity errors symmetrically.
    """

    def _parse(self, effect: str):
        source = _GATE_EFFECT_MACHINE.format(effect=effect)
        return parse_q_orca_markdown(source)

    def test_cswap_with_two_args_produces_arity_error(self):
        result = self._parse("CSWAP(qs[0], qs[1])")
        action = result.file.machines[0].actions[0]
        assert action.gate is None
        assert any("CSWAP" in e and "at least 3" in e for e in result.errors), result.errors
        # Error names the action so the user can locate it.
        assert any("apply" in e for e in result.errors)

    def test_cswap_with_three_args_still_parses(self):
        result = self._parse("CSWAP(qs[0], qs[1], qs[2])")
        action = result.file.machines[0].actions[0]
        assert action.gate is not None
        assert action.gate.kind == "CSWAP"
        assert action.gate.controls == [0]
        assert action.gate.targets == [1, 2]

    def test_cswap_arity_error_does_not_double_fire_unknown_gate_warning(self):
        result = self._parse("CSWAP(qs[0], qs[1])")
        assert any("CSWAP" in e and "at least 3" in e for e in result.errors)
        assert not any("does not match any known gate" in e for e in result.errors), (
            f"unrecognized-gate warning double-fired alongside CSWAP arity error: {result.errors}"
        )


_PARAMETRIC_MACHINE = """\
# machine Parametric

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2] |

## events
- go

## state |s0> [initial]
> start

## state |s1> [final]
> end

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | go    |       | |s1>   | {action} |

## actions
| Name            | Signature                       | Effect           |
|-----------------|---------------------------------|------------------|
| apply_h         | (qs) -> qs                      | Hadamard(qs[0])  |
| query_concept   | (qs, c: int) -> qs              | Hadamard(qs[c])  |
| rotate          | (qs, theta: angle) -> qs        | Rx(qs[0], theta) |
| mix             | (qs, c: int, theta: angle) -> qs | Rx(qs[c], theta) |
"""


class TestParametricActionSignature:
    """Signature-side grammar: typed parameters on the actions table."""

    def _parse_signature(self, sig: str):
        source = (
            "# machine S\n\n"
            "## state |s0> [initial]\n\n"
            "## actions\n"
            "| Name | Signature | Effect |\n"
            "|------|-----------|--------|\n"
            f"| act  | {sig}     |        |\n"
        )
        return parse_q_orca_markdown(source)

    def test_zero_parameter_signature_parses_unchanged(self):
        result = self._parse_signature("(qs) -> qs")
        action = result.file.machines[0].actions[0]
        assert action.parameters == []
        assert action.return_type == "qs"

    def test_ctx_signature_remains_valid(self):
        # Classical context-update actions use `(ctx) -> ctx`; they are not
        # parametric and must continue to parse as zero-parameter.
        result = self._parse_signature("(ctx) -> ctx")
        assert result.errors == []
        action = result.file.machines[0].actions[0]
        assert action.parameters == []
        assert action.return_type == "ctx"

    def test_single_int_parameter(self):
        result = self._parse_signature("(qs, c: int) -> qs")
        action = result.file.machines[0].actions[0]
        assert len(action.parameters) == 1
        assert action.parameters[0].name == "c"
        assert action.parameters[0].type == "int"

    def test_single_angle_parameter(self):
        result = self._parse_signature("(qs, theta: angle) -> qs")
        action = result.file.machines[0].actions[0]
        assert len(action.parameters) == 1
        assert action.parameters[0].name == "theta"
        assert action.parameters[0].type == "angle"

    def test_mixed_int_and_angle_parameters_in_order(self):
        result = self._parse_signature("(qs, c: int, theta: angle) -> qs")
        action = result.file.machines[0].actions[0]
        assert [(p.name, p.type) for p in action.parameters] == [
            ("c", "int"),
            ("theta", "angle"),
        ]

    def test_whitespace_around_colon_and_comma_is_insignificant(self):
        result = self._parse_signature("(qs ,  c  :  int  ,  theta  :  angle) -> qs")
        action = result.file.machines[0].actions[0]
        assert [(p.name, p.type) for p in action.parameters] == [
            ("c", "int"),
            ("theta", "angle"),
        ]

    def test_duplicate_parameter_name_is_error(self):
        result = self._parse_signature("(qs, c: int, c: int) -> qs")
        assert any("duplicate parameter" in e and "'c'" in e for e in result.errors), (
            result.errors
        )

    def test_unknown_parameter_type_is_error(self):
        result = self._parse_signature("(qs, c: float) -> qs")
        assert any(
            "unsupported parameter type" in e and "'float'" in e
            for e in result.errors
        ), result.errors

    def test_parametric_signature_without_leading_qs_is_error(self):
        result = self._parse_signature("(ctx, c: int) -> qs")
        assert any(
            "parametric signature must begin with `qs`" in e for e in result.errors
        ), result.errors


class TestParametricTransitionCall:
    """Transition-side grammar: bare name vs call form; arity and type
    checks; forward-reference resolution."""

    def _parse_with_action_cell(self, action_cell: str):
        return parse_q_orca_markdown(
            _PARAMETRIC_MACHINE.format(action=action_cell)
        )

    def test_bare_name_to_non_parametric_action(self):
        result = self._parse_with_action_cell("apply_h")
        t = result.file.machines[0].transitions[0]
        assert t.action == "apply_h"
        assert t.bound_arguments is None
        assert t.action_label is None

    def test_call_form_with_int_literal(self):
        result = self._parse_with_action_cell("query_concept(3)")
        t = result.file.machines[0].transitions[0]
        assert t.action == "query_concept"
        assert t.action_label == "query_concept(3)"
        assert t.bound_arguments == [
            t.bound_arguments[0].__class__(name="c", value=3)
        ]

    def test_call_form_with_angle_expression(self):
        result = self._parse_with_action_cell("rotate(pi/4)")
        t = result.file.machines[0].transitions[0]
        assert t.action == "rotate"
        assert t.action_label == "rotate(pi/4)"
        assert len(t.bound_arguments) == 1
        assert t.bound_arguments[0].name == "theta"
        assert math.isclose(t.bound_arguments[0].value, math.pi / 4)

    def test_call_form_with_mixed_arguments(self):
        result = self._parse_with_action_cell("mix(1, 2*pi/3)")
        t = result.file.machines[0].transitions[0]
        assert t.action == "mix"
        assert len(t.bound_arguments) == 2
        assert t.bound_arguments[0].name == "c"
        assert t.bound_arguments[0].value == 1
        assert t.bound_arguments[1].name == "theta"
        assert math.isclose(t.bound_arguments[1].value, 2 * math.pi / 3)

    def test_bare_name_reference_to_parametric_action_is_error(self):
        result = self._parse_with_action_cell("query_concept")
        assert any(
            "is parametric and requires arguments" in e
            for e in result.errors
        ), result.errors

    def test_call_form_to_non_parametric_action_is_error(self):
        result = self._parse_with_action_cell("apply_h(0)")
        assert any(
            "is not parametric" in e for e in result.errors
        ), result.errors

    def test_call_form_arity_mismatch_is_error(self):
        result = self._parse_with_action_cell("query_concept(0, 1)")
        assert any(
            "expects 1 argument" in e and "got 2" in e for e in result.errors
        ), result.errors

    def test_call_form_int_type_mismatch_is_error(self):
        result = self._parse_with_action_cell("query_concept(pi/4)")
        assert any(
            "expects an int literal" in e for e in result.errors
        ), result.errors

    def test_call_form_unknown_action_is_error(self):
        result = self._parse_with_action_cell("unknown_action(0)")
        assert any(
            "call-form action" in e and "is not declared" in e
            for e in result.errors
        ), result.errors


class TestParametricActionForwardReference:
    """Forward references: a transition SHALL be able to invoke an action
    that is declared later in the markdown (actions table after
    transitions table)."""

    def test_transition_calls_action_declared_later(self):
        source = """\
# machine Forward

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2] |

## events
- go

## state |s0> [initial]
## state |s1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | go    |       | |s1>   | query_concept(2) |

## actions
| Name          | Signature          | Effect          |
|---------------|--------------------|-----------------|
| query_concept | (qs, c: int) -> qs | Hadamard(qs[c]) |
"""
        result = parse_q_orca_markdown(source)
        assert not any(
            "is not declared" in e for e in result.errors
        ), result.errors
        t = result.file.machines[0].transitions[0]
        assert t.action == "query_concept"
        assert t.bound_arguments[0].value == 2


class TestParametricTemplateBinding:
    """Template-level identifier resolution (Section 4). Subscripts and
    angle slots inside a parametric action's effect SHALL resolve against
    the signature's typed parameters; unbound names SHALL fire structured
    ``unbound identifier`` errors."""

    def _parse_action(self, sig: str, effect: str):
        source = (
            "# machine S\n\n"
            "## state |s0> [initial]\n\n"
            "## actions\n"
            "| Name | Signature | Effect |\n"
            "|------|-----------|--------|\n"
            f"| act  | {sig}     | {effect} |\n"
        )
        return parse_q_orca_markdown(source)

    def test_identifier_subscript_bound_to_int_parameter_parses_clean(self):
        result = self._parse_action("(qs, c: int) -> qs", "Hadamard(qs[c])")
        assert not any("unbound identifier" in e for e in result.errors), result.errors

    def test_identifier_subscript_unbound_is_error(self):
        result = self._parse_action("(qs, d: int) -> qs", "Hadamard(qs[c])")
        assert any(
            "unbound identifier" in e and "'c'" in e and "subscript" in e
            for e in result.errors
        ), result.errors

    def test_zero_parameter_action_with_identifier_subscript_unaffected(self):
        # Non-parametric actions keep their historical behavior: no
        # unbound-identifier error, but the gate-effect parser returns
        # None and the looks-like-gate warning fires.
        result = self._parse_action("(qs) -> qs", "Hadamard(qs[c])")
        assert not any("unbound identifier" in e for e in result.errors), result.errors

    def test_angle_identifier_bound_to_angle_parameter_parses_clean(self):
        result = self._parse_action("(qs, theta: angle) -> qs", "Rx(qs[0], theta)")
        assert not any("unbound identifier" in e for e in result.errors), result.errors

    def test_angle_identifier_unbound_is_error(self):
        # `phi` is not declared even though `theta` is.
        result = self._parse_action("(qs, theta: angle) -> qs", "Rx(qs[0], phi)")
        assert any(
            "unbound identifier" in e and "'phi'" in e and "angle slot" in e
            for e in result.errors
        ), result.errors

    def test_mixed_int_subscript_and_angle_slot(self):
        result = self._parse_action(
            "(qs, c: int, theta: angle) -> qs", "Rx(qs[c], theta)"
        )
        assert not any("unbound identifier" in e for e in result.errors), result.errors

    def test_literal_subscript_in_parametric_action_still_valid(self):
        # Parametric actions MAY mix literal and identifier subscripts
        # freely; literals are never misread as unbound identifiers.
        result = self._parse_action("(qs, c: int) -> qs", "CNOT(qs[0], qs[c])")
        assert not any("unbound identifier" in e for e in result.errors), result.errors

    def test_arithmetic_in_subscript_is_rejected(self):
        # Design decision 5 — subscripts accept literals or bare identifiers
        # only; `qs[c+1]` SHALL fail structurally.
        result = self._parse_action("(qs, c: int) -> qs", "Hadamard(qs[c+1])")
        assert any(
            "invalid subscript" in e for e in result.errors
        ), result.errors


class TestParametricActionIdentifierSubscriptWarning:
    """The `looks like a gate but not known` warning must not fire for a
    parametric action that legitimately uses an identifier subscript in
    its effect (per-call-site expansion — Section 4 — resolves those)."""

    def test_parametric_action_does_not_emit_unknown_gate_warning(self):
        source = """\
# machine PAS

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2] |

## events
- go

## state |s0> [initial]
## state |s1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | go    |       | |s1>   | query_concept(0) |

## actions
| Name          | Signature          | Effect          |
|---------------|--------------------|-----------------|
| query_concept | (qs, c: int) -> qs | Hadamard(qs[c]) |
"""
        result = parse_q_orca_markdown(source)
        assert not any(
            "does not match any known gate" in e for e in result.errors
        ), result.errors


class TestSplitTopLevelCommas:
    """Unit tests for the paren-aware comma splitter used to chop call-site
    argument strings. The naive `s.split(",")` it replaced would
    mis-split nested-call arguments like `mix(atan2(a, b), 0)`.
    """

    def test_no_commas_returns_single_arg(self):
        assert _split_top_level_commas("foo") == ["foo"]

    def test_top_level_split(self):
        assert _split_top_level_commas("a, b, c") == ["a", "b", "c"]

    def test_nested_parens_keep_args_together(self):
        # `atan2(a, b)` is one argument, not two.
        assert _split_top_level_commas("atan2(a, b), 0") == ["atan2(a, b)", "0"]

    def test_nested_brackets_keep_args_together(self):
        # `qs[i, j]` is one argument.
        assert _split_top_level_commas("qs[i, j], theta") == ["qs[i, j]", "theta"]

    def test_deeply_nested_calls(self):
        assert _split_top_level_commas("f(g(a, b), h(c, d)), e") == [
            "f(g(a, b), h(c, d))",
            "e",
        ]

    def test_empty_string_returns_empty_list(self):
        assert _split_top_level_commas("") == []

    def test_whitespace_is_stripped_per_arg(self):
        assert _split_top_level_commas("  a  ,  b  ") == ["a", "b"]
