"""Tests for Q-Orca markdown parser."""

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
