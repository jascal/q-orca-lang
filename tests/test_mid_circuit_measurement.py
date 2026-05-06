"""Tests for mid-circuit measurement and classical feedforward (mid-circuit-measurement change)."""


from q_orca.ast import QEffectMeasure, QEffectConditional, QTypeList
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions, _infer_bit_count
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.verifier.quantum import (
    check_mid_circuit_coherence,
    check_feedforward_completeness,
)


def _compound_machine_source(effect: str) -> str:
    return f"""\
# machine CompoundMCM

## context

| Field  | Type        | Default          |
|--------|-------------|------------------|
| qubits | list<qubit> | [q0, q1, q2, q3, q4] |
| bits   | list<bit>   | [b0, b1]         |

## events

- prepare
- measure_s0
- measure_s1
- correct

## state |ready> [initial]
## state |s0>
## state |s1>
## state |done> [final]

## transitions

| Source     | Event       | Guard | Target | Action      |
|------------|-------------|-------|--------|-------------|
| |ready>    | prepare     |       | |ready>| apply_h     |
| |ready>    | measure_s0  |       | |s0>   | meas_b0     |
| |s0>       | measure_s1  |       | |s1>   | meas_b1     |
| |s1>       | correct     |       | |done> | corr        |

## actions

| Name    | Signature  | Effect                      |
|---------|------------|-----------------------------|
| apply_h | (qs) -> qs | Hadamard(qs[0])             |
| meas_b0 | (qs) -> qs | measure(qs[3]) -> bits[0]   |
| meas_b1 | (qs) -> qs | measure(qs[4]) -> bits[1]   |
| corr    | (qs) -> qs | {effect}                    |
"""


# ---------------------------------------------------------------------------
# Minimal machine fixture used across multiple tests
# ---------------------------------------------------------------------------

MINIMAL_MCM_MACHINE = """\
# machine MinimalMCM

## context

| Field  | Type       | Default      |
|--------|------------|--------------|
| qubits | list<qubit> | [q0, q1]    |
| bits   | list<bit>  | [b0]         |

## events

- prepare
- measure_mid
- correct
- done

## state |ready> [initial]

## state |measured>

## state |done> [final]

## transitions

| Source     | Event       | Guard | Target      | Action      |
|------------|-------------|-------|-------------|-------------|
| |ready>    | prepare     |       | |ready>     | apply_h     |
| |ready>    | measure_mid |       | |measured>  | meas_q0     |
| |measured> | correct     |       | |done>      | corr_q1     |

## actions

| Name    | Signature  | Effect                      |
|---------|------------|-----------------------------|
| apply_h | (qs) -> qs | Hadamard(qs[0])             |
| meas_q0 | (qs) -> qs | measure(qs[0]) -> bits[0]   |
| corr_q1 | (qs) -> qs | if bits[0] == 1: X(qs[1])  |

## verification rules

- mid_circuit_coherence: q0 is not reused after measurement
- feedforward_completeness: bit 0 drives an X correction on q1
"""


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParser:
    def _parse(self, source: str):
        result = parse_q_orca_markdown(source)
        assert not result.errors, f"Parse errors: {result.errors}"
        return result.file.machines[0]

    def test_list_bit_type_parsed(self):
        machine = self._parse(MINIMAL_MCM_MACHINE)
        bit_field = next((f for f in machine.context if f.name == "bits"), None)
        assert bit_field is not None
        assert isinstance(bit_field.type, QTypeList)
        assert bit_field.type.element_type == "bit"

    def test_mid_circuit_measure_parsed(self):
        machine = self._parse(MINIMAL_MCM_MACHINE)
        action = next((a for a in machine.actions if a.name == "meas_q0"), None)
        assert action is not None
        assert action.mid_circuit_measure is not None
        mcm = action.mid_circuit_measure
        assert isinstance(mcm, QEffectMeasure)
        assert mcm.qubit_idx == 0
        assert mcm.bit_idx == 0

    def test_mid_circuit_measure_does_not_also_set_terminal_measurement(self):
        """measure(qs[N]) -> bits[M] should not create a terminal Measurement node."""
        machine = self._parse(MINIMAL_MCM_MACHINE)
        action = next((a for a in machine.actions if a.name == "meas_q0"), None)
        assert action is not None
        assert action.measurement is None

    def test_conditional_gate_parsed(self):
        machine = self._parse(MINIMAL_MCM_MACHINE)
        action = next((a for a in machine.actions if a.name == "corr_q1"), None)
        assert action is not None
        assert action.conditional_gate is not None
        cg = action.conditional_gate
        assert isinstance(cg, QEffectConditional)
        assert cg.bit_idx == 0
        assert cg.value == 1
        assert cg.gate.kind == "X"
        assert cg.gate.targets == [1]

    def test_regular_actions_unaffected(self):
        machine = self._parse(MINIMAL_MCM_MACHINE)
        action = next((a for a in machine.actions if a.name == "apply_h"), None)
        assert action is not None
        assert action.mid_circuit_measure is None
        assert action.conditional_gate is None
        assert action.gate is not None
        assert action.gate.kind == "H"

    def test_active_teleportation_example_parses(self):
        with open("examples/active-teleportation.q.orca.md") as f:
            src = f.read()
        result = parse_q_orca_markdown(src)
        assert not result.errors, f"Parse errors: {result.errors}"
        machine = result.file.machines[0]
        # Should have two mid-circuit measurements and two conditional gates
        mcm_actions = [a for a in machine.actions if a.mid_circuit_measure is not None]
        cg_actions = [a for a in machine.actions if a.conditional_gate is not None]
        assert len(mcm_actions) == 2
        assert len(cg_actions) == 2

    def test_bit_flip_syndrome_example_parses(self):
        with open("examples/bit-flip-syndrome.q.orca.md") as f:
            src = f.read()
        result = parse_q_orca_markdown(src)
        assert not result.errors, f"Parse errors: {result.errors}"
        machine = result.file.machines[0]
        mcm_actions = [a for a in machine.actions if a.mid_circuit_measure is not None]
        cg_actions = [a for a in machine.actions if a.conditional_gate is not None]
        assert len(mcm_actions) == 2
        # All four syndrome patterns map to distinct corrections; the
        # example ships three compound-condition correction actions
        # (correct_q0 / correct_q1 / correct_q2) and an implicit "no
        # correction" path for syndrome (0, 0).
        assert len(cg_actions) == 3
        for a in cg_actions:
            assert len(a.conditional_gate.conditions) == 2


# ---------------------------------------------------------------------------
# Qiskit compiler tests
# ---------------------------------------------------------------------------

class TestQiskitCompiler:
    def _machine(self):
        result = parse_q_orca_markdown(MINIMAL_MCM_MACHINE)
        return result.file.machines[0]

    def test_infer_bit_count(self):
        machine = self._machine()
        assert _infer_bit_count(machine) == 1

    def test_circuit_has_classical_register(self):
        machine = self._machine()
        code = compile_to_qiskit(machine, QSimulationOptions(analytic=True, skip_qutip=True))
        assert "QuantumCircuit(2, 1)" in code

    def test_mid_circuit_measure_emitted(self):
        machine = self._machine()
        code = compile_to_qiskit(machine, QSimulationOptions(analytic=True, skip_qutip=True))
        assert "qc.measure(0, 0)" in code

    def test_if_test_emitted(self):
        machine = self._machine()
        code = compile_to_qiskit(machine, QSimulationOptions(analytic=True, skip_qutip=True))
        assert "qc.if_test(" in code
        assert "qc.clbits[0]" in code

    def test_no_classical_register_without_bits(self):
        source = """\
# machine NoBits

## state |0> [initial]
## state |1> [final]

## transitions

| Source | Event   | Guard | Target | Action |
|--------|---------|-------|--------|--------|
| |0>    | prepare |       | |1>    | apply_h |

## actions

| Name    | Signature  | Effect          |
|---------|------------|-----------------|
| apply_h | (qs) -> qs | Hadamard(qs[0]) |
"""
        result = parse_q_orca_markdown(source)
        machine = result.file.machines[0]
        code = compile_to_qiskit(machine, QSimulationOptions(analytic=True, skip_qutip=True))
        # Should be QuantumCircuit(N) not QuantumCircuit(N, M)
        assert "QuantumCircuit(1, " not in code


# ---------------------------------------------------------------------------
# QASM compiler tests
# ---------------------------------------------------------------------------

class TestQasmCompiler:
    def _machine(self):
        result = parse_q_orca_markdown(MINIMAL_MCM_MACHINE)
        return result.file.machines[0]

    def test_bit_register_declared(self):
        machine = self._machine()
        code = compile_to_qasm(machine)
        assert "bit[1] c;" in code

    def test_mid_circuit_measure_emitted(self):
        machine = self._machine()
        code = compile_to_qasm(machine)
        assert "c[0] = measure q[0];" in code

    def test_conditional_gate_emitted(self):
        machine = self._machine()
        code = compile_to_qasm(machine)
        # OpenQASM 3.0 per-bit conditional: bare bit for value==1
        assert "if (c[0])" in code
        assert "x q[1]" in code

    def test_active_teleportation_qasm(self):
        with open("examples/active-teleportation.q.orca.md") as f:
            src = f.read()
        result = parse_q_orca_markdown(src)
        machine = result.file.machines[0]
        code = compile_to_qasm(machine)
        # Two mid-circuit measurements
        assert "c[0] = measure q[0];" in code
        assert "c[1] = measure q[1];" in code
        # Two conditional corrections using per-bit OpenQASM 3.0 bare-bit syntax
        assert "if (c[0])" in code
        assert "if (c[1])" in code


# ---------------------------------------------------------------------------
# Verifier tests
# ---------------------------------------------------------------------------

class TestVerifier:
    def _machine(self):
        result = parse_q_orca_markdown(MINIMAL_MCM_MACHINE)
        return result.file.machines[0]

    def test_coherence_passes_valid_machine(self):
        machine = self._machine()
        result = check_mid_circuit_coherence(machine)
        assert result.valid
        assert not any(e.severity == "error" for e in result.errors)

    def test_feedforward_completeness_passes_valid_machine(self):
        machine = self._machine()
        result = check_feedforward_completeness(machine)
        assert result.valid

    def test_coherence_inactive_without_rule(self):
        """Without the mid_circuit_coherence rule, the check is skipped."""
        source = """\
# machine NoCohRule

## state |0> [initial]
## state |1> [final]

## transitions

| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    | meas   |

## actions

| Name | Signature  | Effect                     |
|------|------------|----------------------------|
| meas | (qs) -> qs | measure(qs[0]) -> bits[0]  |
"""
        result = parse_q_orca_markdown(source)
        machine = result.file.machines[0]
        vr = check_mid_circuit_coherence(machine)
        assert vr.valid  # rule not declared → skipped

    def test_feedforward_completeness_warns_on_unused_bit(self):
        source = """\
# machine UnusedBit

## context

| Field | Type      | Default |
|-------|-----------|---------|
| bits  | list<bit> | [b0]    |

## state |0> [initial]
## state |1> [final]

## transitions

| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    | meas   |

## actions

| Name | Signature  | Effect                     |
|------|------------|----------------------------|
| meas | (qs) -> qs | measure(qs[0]) -> bits[0]  |

## verification rules

- feedforward_completeness: bit 0 should be used
"""
        result = parse_q_orca_markdown(source)
        machine = result.file.machines[0]
        vr = check_feedforward_completeness(machine)
        # Should warn (warning, not error)
        assert any(e.code == "FEEDFORWARD_UNUSED" for e in vr.errors)
        assert all(e.severity == "warning" for e in vr.errors)
        assert vr.valid  # warnings don't fail validation

    def test_coherence_errors_on_reuse_after_measurement(self):
        source = """\
# machine ReusedQubit

## state |0> [initial]
## state |1>
## state |2> [final]

## transitions

| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | step1 |       | |1>    | meas   |
| |1>    | step2 |       | |2>    | reuse  |

## actions

| Name  | Signature  | Effect                     |
|-------|------------|----------------------------|
| meas  | (qs) -> qs | measure(qs[0]) -> bits[0]  |
| reuse | (qs) -> qs | Hadamard(qs[0])            |

## verification rules

- mid_circuit_coherence: q0 reused after measurement
"""
        result = parse_q_orca_markdown(source)
        machine = result.file.machines[0]
        vr = check_mid_circuit_coherence(machine)
        assert not vr.valid
        assert any(e.code == "MID_CIRCUIT_COHERENCE_VIOLATION" for e in vr.errors)


# ---------------------------------------------------------------------------
# Compound conditional gates (extend-conditional-gate-compound-bits)
# ---------------------------------------------------------------------------

class TestCompoundConditional:
    def _conditional(self, effect: str):
        result = parse_q_orca_markdown(_compound_machine_source(effect))
        assert not result.errors, f"Parse errors: {result.errors}"
        machine = result.file.machines[0]
        action = next(a for a in machine.actions if a.name == "corr")
        return machine, action.conditional_gate

    def test_single_condition_parses_to_length_one_list(self):
        _, cg = self._conditional("if bits[0] == 1: X(qs[1])")
        assert cg.conditions == [(0, 1)]
        assert cg.bit_idx == 0
        assert cg.value == 1

    def test_two_bit_and_conjunction(self):
        _, cg = self._conditional("if bits[0] == 1 and bits[1] == 1: X(qs[1])")
        assert cg.conditions == [(0, 1), (1, 1)]
        assert cg.gate.kind == "X"
        assert cg.gate.targets == [1]

    def test_mixed_value_conjunction(self):
        _, cg = self._conditional("if bits[0] == 1 and bits[1] == 0: X(qs[0])")
        assert cg.conditions == [(0, 1), (1, 0)]

    def test_three_bit_conjunction(self):
        # Bump the bits register to 3 so bits[2] is in range; reuse the
        # 5-qubit machine and add a third measurement.
        source = """\
# machine ThreeBit
## context
| Field  | Type        | Default                |
|--------|-------------|------------------------|
| qubits | list<qubit> | [q0, q1, q2, q3, q4]  |
| bits   | list<bit>   | [b0, b1, b2]          |

## events
- m0
- m1
- m2
- corr

## state |s> [initial]
## state |a>
## state |b>
## state |c>
## state |done> [final]

## transitions
| Source | Event | Guard | Target | Action  |
|--------|-------|-------|--------|---------|
| |s>    | m0    |       | |a>    | meas_b0 |
| |a>    | m1    |       | |b>    | meas_b1 |
| |b>    | m2    |       | |c>    | meas_b2 |
| |c>    | corr  |       | |done> | corr    |

## actions
| Name    | Signature  | Effect                                                       |
|---------|------------|--------------------------------------------------------------|
| meas_b0 | (qs) -> qs | measure(qs[2]) -> bits[0]                                    |
| meas_b1 | (qs) -> qs | measure(qs[3]) -> bits[1]                                    |
| meas_b2 | (qs) -> qs | measure(qs[4]) -> bits[2]                                    |
| corr    | (qs) -> qs | if bits[0] == 1 and bits[1] == 0 and bits[2] == 1: X(qs[3])  |
"""
        result = parse_q_orca_markdown(source)
        assert not result.errors, f"Parse errors: {result.errors}"
        machine = result.file.machines[0]
        cg = next(a.conditional_gate for a in machine.actions if a.name == "corr")
        assert cg.conditions == [(0, 1), (1, 0), (2, 1)]

    def test_conflicting_clauses_rejected(self):
        result = parse_q_orca_markdown(
            _compound_machine_source("if bits[0] == 1 and bits[0] == 0: X(qs[0])")
        )
        assert any(
            "conflicting clauses for bits[0]" in e for e in result.errors
        ), f"Expected conflict error, got {result.errors}"

    def test_whitespace_flexibility(self):
        _, cg = self._conditional("if bits[0]==1  and  bits[1] == 1: X(qs[1])")
        assert cg.conditions == [(0, 1), (1, 1)]

    def test_qasm_emits_compound_with_and(self):
        machine, _ = self._conditional("if bits[0] == 1 and bits[1] == 0: X(qs[0])")
        code = compile_to_qasm(machine)
        assert "if (c[0] && !c[1]) { x q[0]; }" in code

    def test_qasm_single_condition_emit_unchanged(self):
        machine, _ = self._conditional("if bits[0] == 1: X(qs[1])")
        code = compile_to_qasm(machine)
        # The bare-bit / negated-bit shape is preserved for length-1 lists
        assert "if (c[0]) { x q[1]; }" in code

    def test_qiskit_emits_nested_if_test(self):
        machine, _ = self._conditional("if bits[0] == 1 and bits[1] == 1: X(qs[1])")
        code = compile_to_qiskit(
            machine, QSimulationOptions(analytic=True, skip_qutip=True)
        )
        assert "with qc.if_test((qc.clbits[0], 1)):" in code
        assert "with qc.if_test((qc.clbits[1], 1)):" in code
        # Nested: the inner block is indented one level past the outer one.
        lines = code.splitlines()
        outer_idx = next(i for i, line in enumerate(lines)
                         if line.startswith("with qc.if_test((qc.clbits[0], 1)):"))
        inner = lines[outer_idx + 1]
        assert inner.startswith("    with qc.if_test((qc.clbits[1], 1)):"), inner

    def test_qiskit_classical_register_sized_for_max_bit(self):
        machine, _ = self._conditional("if bits[0] == 1 and bits[1] == 1: X(qs[1])")
        # _infer_bit_count walks every clause, so bits[1] keeps the register
        # sized correctly even if no measurement writes bits[1] in the
        # action-table head condition.
        assert _infer_bit_count(machine) == 2

    def test_verifier_feedforward_registers_every_bit(self):
        machine, _ = self._conditional("if bits[0] == 1 and bits[1] == 1: X(qs[1])")
        # Both bits are measured and both are referenced by the conditional;
        # feedforward_completeness should pass.
        result = check_feedforward_completeness(machine)
        assert result.valid, f"Expected valid feedforward, got {result.errors}"
