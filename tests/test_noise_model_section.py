"""Tests for the declarative `## noise_model` section (add-noise-model-section).

Covers parsing (channels/targets/units), the four verifier rules + the
deprecation alias, Qiskit Aer emission (asymmetric channels, readout, thermal),
QASM comment emission, and a live Aer round-trip (skipped if qiskit-aer absent).
"""

import pytest

from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.noise import resolve_noise_section
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier.noise_model import check_noise_model

_BASE = """# machine M
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0, q1, q2] |
{extra}## noise_model
| Channel | Target | Parameters |
|--|--|--|
{rows}
## state |s0> [initial]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go |  | |s1> | mk |
## actions
| Name | Signature | Effect |
| mk | (qs) -> qs | H(qs[0]); CNOT(qs[0], qs[1]); measure(qs[0]) -> bits[0] |
"""


def _machine(rows: str, extra: str = ""):
    return parse_q_orca_markdown(_BASE.format(rows=rows, extra=extra)).file.machines[0]


def _codes(rows, extra="", target=None):
    return [(e.code, e.severity) for e in check_noise_model(_machine(rows, extra), target=target).errors]


# ── Parsing ───────────────────────────────────────────────────────────────────

class TestParsing:
    def test_channels_in_order(self):
        sec = _machine("| depolarizing | single_qubit_gates | p=0.001 |\n"
                       "| depolarizing | two_qubit_gates | p=0.012 |").noise_model
        assert [c.kind for c in sec.channels] == ["depolarizing", "depolarizing"]
        assert [c.target.kind for c in sec.channels] == ["single_qubit_gates", "two_qubit_gates"]

    def test_time_unit_to_ns(self):
        sec = _machine("| thermal | all_qubits | T1=100us, T2=80us |").noise_model
        assert sec.channels[0].parameters == {"T1": 100_000.0, "T2": 80_000.0}

    def test_selectors(self):
        sec = _machine("| thermal | qs[role:ancilla] | T1=1us, T2=1us |\n"
                       "| depolarizing | qs[1] | p=0.01 |\n"
                       "| depolarizing | gates[H,CNOT] | p=0.01 |").noise_model
        t = sec.channels
        assert t[0].target.kind == "qubit_role" and t[0].target.role == "ancilla"
        assert t[1].target.kind == "qubit_index" and t[1].target.index == 1
        assert t[2].target.kind == "gate_list" and t[2].target.gates == ["H", "CNOT"]

    def test_pauli_probabilities_list(self):
        sec = _machine("| pauli | qs[0] | probabilities=[0.97,0.01,0.01,0.01] |").noise_model
        assert sec.channels[0].parameters["probabilities"] == [0.97, 0.01, 0.01, 0.01]


# ── Verifier rules ──────────────────────────────────────────────────────────────

class TestVerifier:
    def test_well_formed_passes(self):
        assert _codes("| depolarizing | single_qubit_gates | p=0.001 |\n"
                      "| readout_error | all_measurements | p0given1=0.02, p1given0=0.04 |") == []

    def test_out_of_range_p(self):
        assert ("NOISE_CHANNEL_INVALID", "error") in _codes("| depolarizing | all_gates | p=1.4 |")

    def test_mixed_params_ambiguous(self):
        assert ("NOISE_PARAMETER_AMBIGUOUS", "error") in _codes(
            "| amplitude_damping | all_qubits | gamma=0.05, T1=100us |")

    def test_role_target_unresolved(self):
        assert ("NOISE_TARGET_NO_MATCH", "warning") in _codes(
            "| thermal | qs[role:ancilla] | T1=1us, T2=1us |")

    def test_qubit_index_out_of_range(self):
        assert ("NOISE_TARGET_NO_MATCH", "warning") in _codes("| depolarizing | qs[9] | p=0.01 |")

    def test_coherence_budget(self):
        codes = _codes("| thermal | all_qubits | T1=10ns, T2=8ns |",
                       extra="| gate_duration_ns | float | 10 |\n")
        assert ("COHERENCE_BUDGET_EXCEEDED", "warning") in codes

    def test_stabilizer_rejects_non_pauli(self):
        assert ("STABILIZER_BACKEND_NOISE_INCOMPATIBLE", "error") in _codes(
            "| amplitude_damping | all_qubits | gamma=0.05 |", target="stabilizer")

    def test_stabilizer_accepts_pauli(self):
        assert _codes("| depolarizing | all_gates | p=0.01 |", target="stabilizer") == []

    def test_qasm_drops_with_warning(self):
        assert ("NOISE_DROPPED_FOR_BACKEND", "warning") in _codes(
            "| depolarizing | all_gates | p=0.01 |", target="qasm3")


# ── Deprecation alias ───────────────────────────────────────────────────────────

_LEGACY = """# machine L
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0] |
| noise | noise_model | depolarizing(0.01) |
## state |s0> [initial]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go |  | |s1> |  |
"""

_SECTION_EQUIV = """# machine S
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0] |
## noise_model
| Channel | Target | Parameters |
| depolarizing | all_gates | p=0.01 |
## state |s0> [initial]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go |  | |s1> |  |
"""


def _noise_block(src):
    code = compile_to_qiskit(parse_q_orca_markdown(src).file.machines[0],
                             QSimulationOptions(skip_qutip=True)).splitlines()
    s = next(i for i, l in enumerate(code) if "Noise model" in l)
    e = next(i for i, l in enumerate(code[s:], s) if l.strip() == "" and i > s + 8)
    return "\n".join(code[s:e])


class TestDeprecationAlias:
    def test_emits_deprecation_warning(self):
        m = parse_q_orca_markdown(_LEGACY).file.machines[0]
        errs = check_noise_model(m).errors
        dep = [e for e in errs if e.code == "NOISE_CONTEXT_FIELD_DEPRECATED"]
        assert len(dep) == 1 and dep[0].severity == "warning"
        assert "## noise_model" in (dep[0].suggestion or "")

    def test_legacy_compiles_byte_identical_to_section(self):
        assert _noise_block(_LEGACY) == _noise_block(_SECTION_EQUIV)


# ── Qiskit emission ─────────────────────────────────────────────────────────────

class TestQiskitEmission:
    def test_asymmetric_depolarizing(self):
        code = compile_to_qiskit(_machine(
            "| depolarizing | single_qubit_gates | p=0.001 |\n"
            "| depolarizing | two_qubit_gates | p=0.012 |"), QSimulationOptions(skip_qutip=True))
        assert "depolarizing_error(0.001, 1)" in code
        assert "depolarizing_error(0.012, 2)" in code

    def test_readout_error(self):
        code = compile_to_qiskit(_machine(
            "| readout_error | all_measurements | p0given1=0.02, p1given0=0.04 |"),
            QSimulationOptions(skip_qutip=True))
        assert "ReadoutError(" in code and "add_all_qubit_readout_error" in code

    def test_thermal_single_qubit_only(self):
        code = compile_to_qiskit(_machine("| thermal | all_qubits | T1=100us, T2=80us |"),
                                 QSimulationOptions(skip_qutip=True))
        tail = code.split("thermal_relaxation_error", 1)[1]
        assert "'cnot'" not in tail and "'cx'" not in tail

    def test_noise_off_strips_model(self):
        code = compile_to_qiskit(_machine("| depolarizing | all_gates | p=0.01 |"),
                                 QSimulationOptions(skip_qutip=True, skip_noise=True))
        assert "depolarizing_error" not in code


# ── QASM emission ───────────────────────────────────────────────────────────────

class TestQasmEmission:
    def test_noise_comment_block(self):
        qasm = compile_to_qasm(_machine(
            "| depolarizing | single_qubit_gates | p=0.001 |\n"
            "| readout_error | all_measurements | p0given1=0.02, p1given0=0.04 |"))
        lines = [l for l in qasm.splitlines() if l.startswith("// noise: channel=")]
        assert len(lines) == 2
        assert "channel=depolarizing target=single_qubit_gates p=0.001" in lines[0]


# ── Live Aer round-trip (skipped if qiskit-aer absent) ──────────────────────────

class TestAerRoundTrip:
    def test_section_builds_valid_noise_model(self):
        pytest.importorskip("qiskit_aer")
        code = compile_to_qiskit(_machine(
            "| depolarizing | single_qubit_gates | p=0.001 |\n"
            "| depolarizing | two_qubit_gates | p=0.012 |\n"
            "| readout_error | all_measurements | p0given1=0.02, p1given0=0.04 |"),
            QSimulationOptions(skip_qutip=True)).splitlines()
        s = next(i for i, l in enumerate(code) if "Noise model" in l)
        e = next(i for i, l in enumerate(code[s:], s) if l.strip() == "" and i > s + 8)
        ns: dict = {}
        exec("\n".join(code[s:e]), ns)
        assert ns["HAS_AER"] is True
        nm = ns["noise_model"]
        assert nm is not None and nm.to_dict()["errors"]


# ── Example ─────────────────────────────────────────────────────────────────────

def test_noisy_example_resolves():
    m = parse_q_orca_markdown(open("examples/vqe-heisenberg-noisy.q.orca.md").read()).file.machines[0]
    sec = resolve_noise_section(m)
    assert sec is not None and len(sec.channels) == 3
    assert check_noise_model(m).valid  # no errors (warnings ok)
