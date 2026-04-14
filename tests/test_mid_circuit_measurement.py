"""Tests for mid-circuit measurement and classical feedforward (mid-circuit-measurement change)."""

import pytest

from q_orca.ast import QEffectMeasure, QEffectConditional, QTypeList
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions, _infer_bit_count
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.verifier.quantum import (
    check_mid_circuit_coherence,
    check_feedforward_completeness,
)


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
        assert len(cg_actions) == 2


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
        # OpenQASM 3.0 per-bit conditional syntax
        assert "if (c[0] == 1)" in code
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
        # Two conditional corrections using per-bit OpenQASM 3.0 syntax
        assert "if (c[0] == 1)" in code
        assert "if (c[1] == 1)" in code


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
