"""Tests for classical context-update effects.

Covers the parser, verifier, and compiler facets of the
`add-classical-context-updates` change.
"""

import pytest

from q_orca.ast import QEffectContextUpdate
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import QSimulationOptions, compile_to_qiskit
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.verifier.classical_context import check_classical_context


def _parse(source: str):
    return parse_q_orca_markdown(source)


def _machine(source: str):
    return _parse(source).file.machines[0]


def _base_machine_with_update(effect: str, action_name: str = "gradient_step") -> str:
    """Minimal machine with a single context-update action."""
    return f"""\
# machine WithUpdate

## context
| Field | Type | Default |
|-------|------|---------|
| iteration | int | 0 |
| theta | list<float> | [0.0, 0.0] |
| eta | float | 0.1 |
| qubits | list<qubit> | [q0] |

## events
- measure_out
- {action_name}_ev

## state |ψ0> [initial]
> start

## state |ψ1>
> after measurement

## state |ψ2> [final]
> after update

## transitions
| Source | Event           | Guard | Target | Action        |
|--------|-----------------|-------|--------|---------------|
| |ψ0>   | measure_out     |       | |ψ1>   | measure_ancilla |
| |ψ1>   | {action_name}_ev |       | |ψ2>   | {action_name} |

## actions
| Name            | Signature              | Effect                           |
|-----------------|------------------------|----------------------------------|
| measure_ancilla | (qs, bits) -> (qs, bits) | measure(qs[0]) -> bits[0]      |
| {action_name}   | (ctx) -> ctx           | {effect}                         |
"""


# ============================================================
# Parser tests
# ============================================================

class TestContextUpdateParser:
    def test_scalar_increment(self):
        source = _base_machine_with_update("iteration += 1", action_name="tick")
        result = _parse(source)
        machine = result.file.machines[0]
        tick = next(a for a in machine.actions if a.name == "tick")
        assert tick.context_update is not None
        cu = tick.context_update
        assert cu.bit_idx is None
        assert cu.bit_value is None
        assert len(cu.then_mutations) == 1
        m = cu.then_mutations[0]
        assert m.target_field == "iteration"
        assert m.target_idx is None
        assert m.op == "+="
        assert m.rhs_literal == 1.0
        assert m.rhs_field is None

    def test_list_element_literal_rhs(self):
        source = _base_machine_with_update("theta[0] -= 0.1")
        machine = _parse(source).file.machines[0]
        action = next(a for a in machine.actions if a.name == "gradient_step")
        cu = action.context_update
        assert cu is not None
        assert cu.bit_idx is None
        assert len(cu.then_mutations) == 1
        m = cu.then_mutations[0]
        assert m.target_field == "theta"
        assert m.target_idx == 0
        assert m.op == "-="
        assert m.rhs_literal == 0.1

    def test_list_element_field_rhs(self):
        source = _base_machine_with_update("theta[1] += eta")
        machine = _parse(source).file.machines[0]
        action = next(a for a in machine.actions if a.name == "gradient_step")
        m = action.context_update.then_mutations[0]
        assert m.target_field == "theta"
        assert m.target_idx == 1
        assert m.op == "+="
        assert m.rhs_field == "eta"
        assert m.rhs_literal is None

    def test_conditional_with_then_and_else(self):
        effect = "if bits[0] == 1: theta[0] -= eta else: theta[0] += eta"
        source = _base_machine_with_update(effect)
        machine = _parse(source).file.machines[0]
        action = next(a for a in machine.actions if a.name == "gradient_step")
        cu = action.context_update
        assert cu is not None
        assert cu.bit_idx == 0
        assert cu.bit_value == 1
        assert len(cu.then_mutations) == 1
        assert len(cu.else_mutations) == 1
        assert cu.then_mutations[0].op == "-="
        assert cu.else_mutations[0].op == "+="

    def test_conditional_then_only(self):
        effect = "if bits[0] == 1: theta[0] -= eta"
        source = _base_machine_with_update(effect)
        machine = _parse(source).file.machines[0]
        action = next(a for a in machine.actions if a.name == "gradient_step")
        cu = action.context_update
        assert cu is not None
        assert cu.bit_idx == 0
        assert cu.bit_value == 1
        assert len(cu.then_mutations) == 1
        assert cu.else_mutations == []

    def test_unconditional_multi_mutation(self):
        effect = "theta[0] += eta; iteration += 1"
        source = _base_machine_with_update(effect, action_name="step")
        machine = _parse(source).file.machines[0]
        action = next(a for a in machine.actions if a.name == "step")
        cu = action.context_update
        assert cu is not None
        assert len(cu.then_mutations) == 2
        assert cu.then_mutations[0].target_field == "theta"
        assert cu.then_mutations[1].target_field == "iteration"

    def test_mixed_gate_and_context_update_rejected(self):
        effect = "H(qs[0]); iteration += 1"
        source = _base_machine_with_update(effect, action_name="bad")
        result = _parse(source)
        assert any("cannot be combined" in e for e in result.errors), result.errors
        machine = result.file.machines[0]
        action = next(a for a in machine.actions if a.name == "bad")
        assert action.context_update is None

    def test_nested_conditional_rejected(self):
        effect = "if bits[0] == 1: if bits[1] == 1: theta[0] -= eta"
        source = _base_machine_with_update(effect, action_name="bad")
        result = _parse(source)
        assert any("nested" in e.lower() for e in result.errors), result.errors

    def test_non_bit_condition_not_parsed_as_update(self):
        # `if iteration > 0: ...` isn't valid grammar; the parser should
        # return None (letting other parsers see a non-match) rather than
        # producing a context_update.
        effect = "if iteration > 0: theta[0] += eta"
        source = _base_machine_with_update(effect, action_name="bad")
        machine = _parse(source).file.machines[0]
        action = next(a for a in machine.actions if a.name == "bad")
        assert action.context_update is None

    def test_raw_effect_string_preserved(self):
        effect = "if bits[0] == 1: theta[0] -= eta else: theta[0] += eta"
        source = _base_machine_with_update(effect)
        machine = _parse(source).file.machines[0]
        action = next(a for a in machine.actions if a.name == "gradient_step")
        assert action.context_update.raw == effect


# ============================================================
# Verifier tests
# ============================================================

class TestContextUpdateVerifier:
    def test_happy_path_verifies_cleanly(self):
        effect = "if bits[0] == 1: theta[0] -= eta else: theta[0] += eta"
        source = _base_machine_with_update(effect)
        machine = _machine(source)
        res = check_classical_context(machine)
        assert res.valid, [e.code for e in res.errors]

    def test_undeclared_field_reports_error(self):
        source = _base_machine_with_update("nonexistent += 1", action_name="tick")
        machine = _machine(source)
        res = check_classical_context(machine)
        codes = [e.code for e in res.errors]
        assert "UNDECLARED_CONTEXT_FIELD" in codes

    def test_wrong_type_scalar_mutation(self):
        source = f"""\
# machine WrongType

## context
| Field | Type | Default |
|-------|------|---------|
| label | string | "foo" |
| qubits | list<qubit> | [q0] |

## events
- tick_ev

## state |ψ0> [initial]

## state |ψ1> [final]

## transitions
| Source | Event   | Guard | Target | Action |
|--------|---------|-------|--------|--------|
| |ψ0>   | tick_ev |       | |ψ1>   | tick   |

## actions
| Name | Signature     | Effect      |
|------|---------------|-------------|
| tick | (ctx) -> ctx  | label += 1  |
"""
        machine = _machine(source)
        res = check_classical_context(machine)
        codes = [e.code for e in res.errors]
        assert "CONTEXT_FIELD_TYPE_MISMATCH" in codes

    def test_index_out_of_range(self):
        source = _base_machine_with_update("theta[5] += 0.1", action_name="tick")
        machine = _machine(source)
        res = check_classical_context(machine)
        codes = [e.code for e in res.errors]
        assert "CONTEXT_INDEX_OUT_OF_RANGE" in codes

    def test_bit_read_before_write_no_measurement_anywhere(self):
        source = f"""\
# machine Unread

## context
| Field | Type | Default |
|-------|------|---------|
| theta | list<float> | [0.0] |
| eta | float | 0.1 |
| qubits | list<qubit> | [q0] |

## events
- go

## state |ψ0> [initial]

## state |ψ1> [final]

## transitions
| Source | Event | Guard | Target | Action        |
|--------|-------|-------|--------|---------------|
| |ψ0>   | go    |       | |ψ1>   | gradient_step |

## actions
| Name           | Signature    | Effect                                               |
|----------------|--------------|------------------------------------------------------|
| gradient_step  | (ctx) -> ctx | if bits[0] == 1: theta[0] -= eta else: theta[0] += eta |
"""
        machine = _machine(source)
        res = check_classical_context(machine)
        codes = [e.code for e in res.errors]
        assert "BIT_READ_BEFORE_WRITE" in codes

    def test_bit_written_on_every_path_is_ok(self):
        effect = "if bits[0] == 1: theta[0] -= eta"
        source = _base_machine_with_update(effect)
        machine = _machine(source)
        res = check_classical_context(machine)
        codes = [e.code for e in res.errors]
        assert "BIT_READ_BEFORE_WRITE" not in codes

    def test_skip_flag_disables_stage(self):
        source = _base_machine_with_update("nonexistent += 1", action_name="tick")
        machine = _machine(source)
        # Normally this would fail classical-context
        res_skip = verify(machine, VerifyOptions(skip_classical_context=True,
                                                  skip_dynamic=True,
                                                  skip_quantum=True))
        codes = [e.code for e in res_skip.errors]
        assert "UNDECLARED_CONTEXT_FIELD" not in codes

    def test_pipeline_integration(self):
        """Classical-context errors surface through the top-level verify()."""
        source = _base_machine_with_update("nonexistent += 1", action_name="tick")
        machine = _machine(source)
        res = verify(machine, VerifyOptions(skip_dynamic=True, skip_quantum=True))
        codes = [e.code for e in res.errors]
        assert "UNDECLARED_CONTEXT_FIELD" in codes
        assert not res.valid


# ============================================================
# Compiler tests
# ============================================================

class TestContextUpdateCompiler:
    def test_qasm_emits_annotation_and_banner(self):
        effect = "if bits[0] == 1: theta[0] -= eta else: theta[0] += eta"
        source = _base_machine_with_update(effect)
        machine = _machine(source)
        qasm = compile_to_qasm(machine)
        assert f"// context_update: {effect}" in qasm
        assert "context-update actions are annotations only" in qasm

    def test_qasm_no_banner_when_no_context_update(self):
        # Minimal machine with only a gate action.
        source = """\
# machine NoUpdate

## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0] |

## events
- go

## state |0> [initial]

## state |1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    | apply_x |

## actions
| Name   | Signature        | Effect    |
|--------|------------------|-----------|
| apply_x | (qs) -> qs      | X(qs[0])  |
"""
        machine = _machine(source)
        qasm = compile_to_qasm(machine)
        assert "context-update actions are annotations only" not in qasm
        assert "context_update" not in qasm

    def test_qiskit_emits_annotation_and_banner(self):
        effect = "iteration += 1"
        source = _base_machine_with_update(effect, action_name="tick")
        machine = _machine(source)
        qiskit_script = compile_to_qiskit(machine, QSimulationOptions(skip_qutip=True))
        assert f"# context_update: {effect}" in qiskit_script
        assert "executed by the iterative runtime" in qiskit_script

    def test_qiskit_no_banner_when_no_context_update(self):
        source = """\
# machine NoUpdate

## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0] |

## events
- go

## state |0> [initial]

## state |1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    | apply_x |

## actions
| Name   | Signature        | Effect    |
|--------|------------------|-----------|
| apply_x | (qs) -> qs      | X(qs[0])  |
"""
        machine = _machine(source)
        script = compile_to_qiskit(machine, QSimulationOptions(skip_qutip=True))
        assert "context-update actions are annotations only" not in script

    def test_mermaid_renders_transition_label_unchanged(self):
        """Mermaid uses the action name on the transition arrow as-is."""
        from q_orca.compiler.mermaid import compile_to_mermaid

        effect = "if bits[0] == 1: theta[0] -= eta"
        source = _base_machine_with_update(effect)
        machine = _machine(source)
        mermaid = compile_to_mermaid(machine)
        # The action label is "gradient_step" — the raw effect string
        # should NOT leak into the mermaid output.
        assert "gradient_step" in mermaid
        assert "theta[0]" not in mermaid


# ============================================================
# UNBOUNDED_CONTEXT_LOOP termination warning
# ============================================================

_BOUNDED_LEARNING_MACHINE = """\
# machine BoundedLearner

## context
| Field     | Type        | Default      |
|-----------|-------------|--------------|
| qubits    | list<qubit> | [q0]         |
| bits      | list<bit>   | [b0]         |
| iteration | int         | 0            |
| max_iter  | int         | 3            |

## events
- measure_e
- tick_e
- finalize

## state |s0> [initial]
## state |s1>
## state |s2>
## state |done> [final]

## guards
| Name     | Expression                |
|----------|---------------------------|
| continue | ctx.iteration < max_iter  |
| done     | ctx.iteration >= max_iter |

## transitions
| Source | Event      | Guard    | Target  | Action          |
|--------|------------|----------|---------|-----------------|
| |s0>   | measure_e  |          | |s1>    | measure_ancilla |
| |s1>   | tick_e     | continue | |s0>    | tick            |
| |s1>   | finalize   | done     | |done>  |                 |

## actions
| Name            | Signature                | Effect                     |
|-----------------|--------------------------|----------------------------|
| measure_ancilla | (qs, bits) -> (qs, bits) | measure(qs[0]) -> bits[0]  |
| tick            | (ctx) -> ctx             | iteration += 1             |
"""


_UNBOUNDED_FLOAT_ONLY_MACHINE = """\
# machine FloatOnlyLoop

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0]         |
| bits   | list<bit>   | [b0]         |
| theta  | list<float> | [0.0, 0.0]   |
| eta    | float       | 0.1          |

## events
- measure_e
- step_e
- finalize

## state |s0> [initial]
## state |s1>
## state |done> [final]

## guards
| Name | Expression     |
|------|----------------|
| hot  | theta[0] < eta |

## transitions
| Source | Event     | Guard | Target  | Action          |
|--------|-----------|-------|---------|-----------------|
| |s0>   | measure_e |       | |s1>    | measure_ancilla |
| |s1>   | step_e    | hot   | |s0>    | drift           |
| |s1>   | finalize  |       | |done>  |                 |

## actions
| Name            | Signature                | Effect                     |
|-----------------|--------------------------|----------------------------|
| measure_ancilla | (qs, bits) -> (qs, bits) | measure(qs[0]) -> bits[0]  |
| drift           | (ctx) -> ctx             | theta[0] += eta            |
"""


_NO_GUARDS_AT_ALL_MACHINE = """\
# machine UnguardedLoop

## context
| Field     | Type        | Default  |
|-----------|-------------|----------|
| qubits    | list<qubit> | [q0]     |
| bits      | list<bit>   | [b0]     |
| iteration | int         | 0        |

## events
- measure_e
- tick_e
- finalize

## state |s0> [initial]
## state |s1>
## state |done> [final]

## transitions
| Source | Event     | Guard | Target  | Action          |
|--------|-----------|-------|---------|-----------------|
| |s0>   | measure_e |       | |s1>    | measure_ancilla |
| |s1>   | tick_e    |       | |s0>    | tick            |
| |s1>   | finalize  |       | |done>  |                 |

## actions
| Name            | Signature                | Effect                     |
|-----------------|--------------------------|----------------------------|
| measure_ancilla | (qs, bits) -> (qs, bits) | measure(qs[0]) -> bits[0]  |
| tick            | (ctx) -> ctx             | iteration += 1             |
"""


class TestIterativeTerminationWarning:
    def test_bounded_int_guard_suppresses_warning(self):
        machine = _machine(_BOUNDED_LEARNING_MACHINE)
        result = check_classical_context(machine)
        codes = [e.code for e in result.errors]
        assert "UNBOUNDED_CONTEXT_LOOP" not in codes

    def test_float_only_guard_still_warns(self):
        machine = _machine(_UNBOUNDED_FLOAT_ONLY_MACHINE)
        result = check_classical_context(machine)
        warnings = [e for e in result.errors if e.code == "UNBOUNDED_CONTEXT_LOOP"]
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"

    def test_no_guards_emits_warning(self):
        machine = _machine(_NO_GUARDS_AT_ALL_MACHINE)
        result = check_classical_context(machine)
        warnings = [e for e in result.errors if e.code == "UNBOUNDED_CONTEXT_LOOP"]
        assert len(warnings) == 1

    def test_machine_without_context_updates_is_silent(self):
        source = """\
# machine Plain

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]    |

## events
- go

## state |0> [initial]
## state |1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    | apply_h |

## actions
| Name    | Signature  | Effect  |
|---------|------------|---------|
| apply_h | (qs) -> qs | H(qs[0]) |
"""
        machine = _machine(source)
        result = check_classical_context(machine)
        codes = [e.code for e in result.errors]
        assert "UNBOUNDED_CONTEXT_LOOP" not in codes

    def test_skip_flag_suppresses_warning(self):
        machine = _machine(_NO_GUARDS_AT_ALL_MACHINE)
        result = verify(
            machine, VerifyOptions(skip_classical_context=True, skip_dynamic=True)
        )
        codes = [e.code for e in result.errors]
        assert "UNBOUNDED_CONTEXT_LOOP" not in codes
