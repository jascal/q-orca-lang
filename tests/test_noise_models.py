"""Tests for the legacy `noise:` context field: parsing + compile integration.

The flat single-channel emission was replaced by the declarative `## noise_model`
section (`add-noise-model-section`); the legacy field is now a deprecated alias
that routes through the section emitter. These tests assert the alias still
parses and still produces the expected Aer calls in the compiled output. The
section itself is covered by `tests/test_noise_model_section.py`.
"""

import pytest

from q_orca.compiler.qiskit import (
    _parse_noise_model_string,
    compile_to_qiskit,
    QSimulationOptions,
)
from q_orca.parser.markdown_parser import parse_q_orca_markdown


# ── Legacy string parsing (still used by the deprecated-field alias) ──────────

class TestNoiseModelParsing:
    def test_depolarizing(self):
        nm = _parse_noise_model_string("depolarizing(0.01)")
        assert nm is not None and nm.kind == "depolarizing"
        assert nm.parameter == pytest.approx(0.01)

    def test_depolarizing_case_insensitive(self):
        assert _parse_noise_model_string("Depolarizing(0.05)").kind == "depolarizing"

    def test_amplitude_damping(self):
        nm = _parse_noise_model_string("amplitude_damping(0.05)")
        assert nm.kind == "amplitude_damping" and nm.parameter == pytest.approx(0.05)

    def test_amplitude_damping_camel(self):
        assert _parse_noise_model_string("amplitudeDamping(0.1)").kind == "amplitude_damping"

    def test_phase_damping(self):
        nm = _parse_noise_model_string("phase_damping(0.02)")
        assert nm.kind == "phase_damping" and nm.parameter == pytest.approx(0.02)

    def test_thermal_two_params(self):
        nm = _parse_noise_model_string("thermal(50000, 70000)")
        assert nm.kind == "thermal"
        assert nm.parameter == pytest.approx(50000.0)
        assert nm.parameter2 == pytest.approx(70000.0)

    def test_unrecognized_kind_returns_none(self):
        assert _parse_noise_model_string("custom_noise(0.1)") is None

    def test_empty_string_returns_none(self):
        assert _parse_noise_model_string("") is None

    def test_none_input_returns_none(self):
        assert _parse_noise_model_string(None) is None


# ── Compile integration (deprecated field → section emitter) ──────────────────

_NOISE_MACHINE_TEMPLATE = """\
# machine NoiseSmoke
## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]    |
| noise  | noise_model | {noise} |
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


def _compile(noise_str: str) -> str:
    machine = parse_q_orca_markdown(_NOISE_MACHINE_TEMPLATE.format(noise=noise_str)).file.machines[0]
    return compile_to_qiskit(machine, QSimulationOptions(skip_noise=False, skip_qutip=True))


class TestLegacyFieldCompiles:
    def test_depolarizing_in_output(self):
        code = _compile("depolarizing(0.01)")
        assert "depolarizing_error(0.01, 1)" in code
        assert "add_all_qubit_quantum_error" in code
        assert "'cnot'" in code  # all_gates target includes two-qubit gates

    def test_amplitude_damping_in_output(self):
        assert "amplitude_damping_error(0.05)" in _compile("amplitude_damping(0.05)")

    def test_phase_damping_in_output(self):
        assert "phase_damping_error(0.02)" in _compile("phase_damping(0.02)")

    def test_thermal_in_output_single_qubit_only(self):
        code = _compile("thermal(50000, 70000)")
        assert "thermal_relaxation_error(50000.0, 70000.0," in code
        # thermal is a single-qubit channel — not installed on two-qubit gates
        assert "'cnot'" not in code.split("thermal_relaxation_error", 1)[1]

    def test_thermal_single_param_defaults_t2(self):
        code = _compile("thermal(50000)")
        assert "thermal_relaxation_error(50000.0, 50000.0," in code
