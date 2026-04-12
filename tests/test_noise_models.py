"""Tests for noise model parsing, emission, and compile integration."""

import pytest

from q_orca.ast import NoiseModel
from q_orca.compiler.qiskit import (
    _parse_noise_model_string,
    _emit_qiskit_noise_model_code,
    compile_to_qiskit,
    QSimulationOptions,
)
from q_orca.parser.markdown_parser import parse_q_orca_markdown


# ── Parsing ──────────────────────────────────────────────────────────────────

class TestNoiseModelParsing:
    def test_depolarizing(self):
        nm = _parse_noise_model_string("depolarizing(0.01)")
        assert nm is not None
        assert nm.kind == "depolarizing"
        assert nm.parameter == pytest.approx(0.01)

    def test_depolarizing_case_insensitive(self):
        nm = _parse_noise_model_string("Depolarizing(0.05)")
        assert nm is not None
        assert nm.kind == "depolarizing"

    def test_amplitude_damping(self):
        nm = _parse_noise_model_string("amplitude_damping(0.05)")
        assert nm is not None
        assert nm.kind == "amplitude_damping"
        assert nm.parameter == pytest.approx(0.05)

    def test_amplitude_damping_camel(self):
        nm = _parse_noise_model_string("amplitudeDamping(0.1)")
        assert nm is not None
        assert nm.kind == "amplitude_damping"

    def test_phase_damping(self):
        nm = _parse_noise_model_string("phase_damping(0.02)")
        assert nm is not None
        assert nm.kind == "phase_damping"
        assert nm.parameter == pytest.approx(0.02)

    def test_thermal_one_param(self):
        nm = _parse_noise_model_string("thermal(50000)")
        assert nm is not None
        assert nm.kind == "thermal"
        assert nm.parameter == pytest.approx(50000.0)
        assert nm.parameter2 == pytest.approx(0.0)  # sentinel: T2 defaults to T1

    def test_thermal_two_params(self):
        nm = _parse_noise_model_string("thermal(50000, 70000)")
        assert nm is not None
        assert nm.kind == "thermal"
        assert nm.parameter == pytest.approx(50000.0)
        assert nm.parameter2 == pytest.approx(70000.0)

    def test_unrecognized_kind_returns_none(self):
        nm = _parse_noise_model_string("custom_noise(0.1)")
        assert nm is None

    def test_empty_string_returns_none(self):
        assert _parse_noise_model_string("") is None

    def test_none_input_returns_none(self):
        assert _parse_noise_model_string(None) is None


# ── Emission ─────────────────────────────────────────────────────────────────

class TestNoiseModelEmission:
    def _lines(self, nm: NoiseModel) -> list[str]:
        return _emit_qiskit_noise_model_code(nm, qubit_count=1)

    def test_depolarizing_uses_depolarizing_error(self):
        lines = self._lines(NoiseModel(kind="depolarizing", parameter=0.01))
        combined = "\n".join(lines)
        assert "depolarizing_error(0.01, 1)" in combined
        assert "add_all_qubit_quantum_error" in combined
        assert "'cnot'" in combined  # two-qubit gates included

    def test_amplitude_damping_uses_amplitude_damping_error(self):
        lines = self._lines(NoiseModel(kind="amplitude_damping", parameter=0.05))
        combined = "\n".join(lines)
        assert "amplitude_damping_error(0.05)" in combined
        assert "add_all_qubit_quantum_error" in combined

    def test_phase_damping_uses_phase_damping_error(self):
        lines = self._lines(NoiseModel(kind="phase_damping", parameter=0.02))
        combined = "\n".join(lines)
        assert "phase_damping_error(0.02)" in combined
        assert "add_all_qubit_quantum_error" in combined

    def test_thermal_uses_thermal_relaxation_error(self):
        lines = self._lines(NoiseModel(kind="thermal", parameter=50000.0, parameter2=70000.0))
        combined = "\n".join(lines)
        assert "thermal_relaxation_error(50000.0, 70000.0, 50)" in combined
        assert "add_all_qubit_quantum_error" in combined

    def test_thermal_no_two_qubit_gates(self):
        lines = self._lines(NoiseModel(kind="thermal", parameter=50000.0, parameter2=70000.0))
        combined = "\n".join(lines)
        assert "'cnot'" not in combined
        assert "'cx'" not in combined
        assert "'swap'" not in combined

    def test_unknown_kind_emits_none(self):
        lines = self._lines(NoiseModel(kind="unknown"))
        combined = "\n".join(lines)
        assert "noise_model = None" in combined


# ── Thermal defaults ──────────────────────────────────────────────────────────

class TestThermalDefaults:
    def test_single_param_defaults_t2_to_t1(self):
        nm = _parse_noise_model_string("thermal(50000)")
        lines = _emit_qiskit_noise_model_code(nm, qubit_count=1)
        combined = "\n".join(lines)
        # T2 should equal T1 (50000) when parameter2 == 0.0
        assert "thermal_relaxation_error(50000.0, 50000.0, 50)" in combined

    def test_two_params_uses_distinct_t2(self):
        nm = _parse_noise_model_string("thermal(50000, 70000)")
        lines = _emit_qiskit_noise_model_code(nm, qubit_count=1)
        combined = "\n".join(lines)
        assert "thermal_relaxation_error(50000.0, 70000.0, 50)" in combined


# ── Compile smoke ─────────────────────────────────────────────────────────────

_NOISE_MACHINE_TEMPLATE = """\
# machine NoiseSmoke

## context
| Field  | Type        | Default   |
|--------|-------------|-----------|
| qubits | list<qubit> | [q0]      |
| noise  | noise_model | {noise}   |

## events
- go

## state |0> [initial]
## state |1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    | flip   |

## actions
| Name | Signature  | Effect   |
|------|------------|----------|
| flip | (qs) -> qs | X(qs[0]) |
"""


def _machine(noise_str: str):
    source = _NOISE_MACHINE_TEMPLATE.format(noise=noise_str)
    return parse_q_orca_markdown(source).file.machines[0]


class TestNoiseModelCompileSmoke:
    def _compile(self, noise_str: str) -> str:
        machine = _machine(noise_str)
        return compile_to_qiskit(machine, QSimulationOptions(skip_noise=False))

    def test_depolarizing_in_output(self):
        code = self._compile("depolarizing(0.01)")
        assert "depolarizing_error" in code

    def test_amplitude_damping_in_output(self):
        code = self._compile("amplitude_damping(0.05)")
        assert "amplitude_damping_error" in code

    def test_phase_damping_in_output(self):
        code = self._compile("phase_damping(0.02)")
        assert "phase_damping_error" in code

    def test_thermal_in_output(self):
        code = self._compile("thermal(50000, 70000)")
        assert "thermal_relaxation_error" in code
        assert "50000" in code
        assert "70000" in code

    def test_thermal_single_param_in_output(self):
        code = self._compile("thermal(50000)")
        assert "thermal_relaxation_error(50000.0, 50000.0, 50)" in code
