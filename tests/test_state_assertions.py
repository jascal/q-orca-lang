"""Tests for the Stage-4b state-category assertion checker.

Covers `add-runtime-state-assertions` tasks §5.2-5.3 (partial trace) and
§12.1-12.7 (assertion checker: one passing case per category, failure
severities, inconclusive-at-low-shots, backend-missing, real-device skip,
mid-circuit measurement, and unreachable-state skip).
"""

import numpy as np
import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import dynamic as dyn
from q_orca.verifier._partial_trace import purity, reduced_density_matrix
from q_orca.verifier.assertions import check_state_assertions

INV2 = 1.0 / np.sqrt(2.0)


def _machine(source: str):
    result = parse_q_orca_markdown(source)
    assert not result.errors, result.errors
    assert result.file.machines, "no machine parsed"
    return result.file.machines[0]


def _codes(machine, **kwargs):
    return [(d.code, d.severity) for d in check_state_assertions(machine, **kwargs)]


# A two-qubit Bell machine with one assertion slot per state. Callers fill the
# `{a_*}` placeholders with `[assert: …]` annotations (or leave them blank).
BELL_TMPL = """# machine Bell
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0, q1] |
## state |00> [initial] {a00}
## state |plus> {aplus}
## state |bell> {abell}
## transitions
| Source | Event | Guard | Target | Action |
| |00> | h | | |plus> | apply_H |
| |plus> | e | | |bell> | apply_CNOT |
## actions
| Name | Signature | Effect |
| apply_H | (qs) -> qs | Hadamard(qs[0]) |
| apply_CNOT | (qs) -> qs | CNOT(qs[0], qs[1]) |
{policy}
"""


def _bell(a00="", aplus="", abell="", policy=""):
    return _machine(BELL_TMPL.format(
        a00=a00, aplus=aplus, abell=abell,
        policy=("## assertion policy\n| Setting | Value |\n" + policy) if policy else "",
    ))


# ---------------------------------------------------------------------------
# §5.2-5.3 partial trace (no backend needed)
# ---------------------------------------------------------------------------

class TestPartialTrace:
    def test_bell_single_qubit_marginal_is_maximally_mixed(self):
        bell = np.array([INV2, 0, 0, INV2])
        for q in (0, 1):
            rho = reduced_density_matrix(bell, 2, [q])
            assert np.allclose(rho, np.eye(2) / 2)
            assert abs(purity(rho) - 0.5) < 1e-9

    def test_bell_joint_pair_is_pure(self):
        bell = np.array([INV2, 0, 0, INV2])
        assert abs(purity(reduced_density_matrix(bell, 2, [0, 1])) - 1.0) < 1e-9

    def test_product_state_single_qubit_marginals_are_pure(self):
        prod = np.kron(np.array([INV2, INV2]), np.array([1.0, 0.0]))  # |+>|0>
        for q in (0, 1):
            assert abs(purity(reduced_density_matrix(prod, 2, [q])) - 1.0) < 1e-9

    def test_ghz_pairwise_reduction_is_mixed(self):
        ghz = np.zeros(8)
        ghz[0] = INV2
        ghz[7] = INV2
        assert abs(purity(reduced_density_matrix(ghz, 3, [1])) - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# §12.1 one passing test per category
# ---------------------------------------------------------------------------

class TestPassingAssertions:
    def test_classical_at_ground_state(self):
        pytest.importorskip("qutip")
        m = _bell(a00="[assert: classical(qs[0])]")
        assert _codes(m) == [("ASSERTION_PASSED", "info")]

    def test_superposition_after_hadamard(self):
        pytest.importorskip("qutip")
        m = _bell(aplus="[assert: superposition(qs[0])]")
        assert _codes(m) == [("ASSERTION_PASSED", "info")]

    def test_entangled_on_bell_pair(self):
        pytest.importorskip("qutip")
        m = _bell(abell="[assert: entangled(qs[0], qs[1])]")
        assert _codes(m) == [("ASSERTION_PASSED", "info")]

    def test_separable_on_product_state(self):
        pytest.importorskip("qutip")
        m = _bell(aplus="[assert: separable(qs[0], qs[1])]")
        assert _codes(m) == [("ASSERTION_PASSED", "info")]


# ---------------------------------------------------------------------------
# §12.2 failure severities
# ---------------------------------------------------------------------------

class TestFailingAssertion:
    def test_failed_is_error_by_default(self):
        pytest.importorskip("qutip")
        # entangled asserted on the product state |+0> (no CNOT yet) -> fails
        m = _bell(aplus="[assert: entangled(qs[0], qs[1])]")
        assert _codes(m) == [("ASSERTION_FAILED", "error")]

    def test_failed_is_warning_when_on_failure_warn(self):
        pytest.importorskip("qutip")
        m = _bell(aplus="[assert: entangled(qs[0], qs[1])]", policy="| on_failure | warn |")
        assert _codes(m) == [("ASSERTION_FAILED", "warning")]


# ---------------------------------------------------------------------------
# §12.3 inconclusive at small shot counts
# ---------------------------------------------------------------------------

class TestInconclusiveAssertion:
    def test_inconclusive_at_16_shots(self):
        pytest.importorskip("qutip")
        # Ry(qs[0], 0.5) gives p(|0>) ≈ 0.94 — borderline against the 0.90
        # definiteness threshold at only 16 shots.
        source = """# machine Inc
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0] |
## state |0> [initial]
## state |rot> [assert: classical(qs[0])]
## transitions
| Source | Event | Guard | Target | Action |
| |0> | r | | |rot> | rot |
## actions
| Name | Signature | Effect |
| rot | (qs) -> qs | Ry(qs[0], 0.5) |
## assertion policy
| Setting | Value |
| shots_per_assert | 16 |
"""
        assert _codes(_machine(source)) == [("ASSERTION_INCONCLUSIVE", "warning")]


# ---------------------------------------------------------------------------
# §12.4 backend missing
# ---------------------------------------------------------------------------

class TestBackendMissing:
    def test_single_backend_missing_warning(self, monkeypatch):
        monkeypatch.setattr(dyn, "QUTIP_AVAILABLE", False)
        m = _bell(abell="[assert: entangled(qs[0], qs[1])]")
        codes = _codes(m)
        assert codes == [("ASSERTION_BACKEND_MISSING", "warning")]


# ---------------------------------------------------------------------------
# §12.5 real-device target
# ---------------------------------------------------------------------------

class TestRealDeviceSkip:
    def test_real_device_emits_single_info(self):
        m = _bell(abell="[assert: entangled(qs[0], qs[1])]", policy="| backend | hardware |")
        assert _codes(m) == [("ASSERTIONS_SKIPPED_NO_SIMULATOR", "info")]


# ---------------------------------------------------------------------------
# §12.6 mid-circuit measurement
# ---------------------------------------------------------------------------

class TestMidCircuitMeasurement:
    SRC = """# machine MCM
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0] |
## state |0> [initial]
## state |super>
## state |measured> {a}
## transitions
| Source | Event | Guard | Target | Action |
| |0> | h | | |super> | apply_H |
| |super> | m | | |measured> | meas_q0 |
## actions
| Name | Signature | Effect |
| apply_H | (qs) -> qs | Hadamard(qs[0]) |
| meas_q0 | (qs) -> qs | measure(qs[0]) -> bits[0] |
"""

    def test_classical_holds_after_measurement_collapse(self):
        pytest.importorskip("qutip")
        m = _machine(self.SRC.format(a="[assert: classical(qs[0])]"))
        assert _codes(m) == [("ASSERTION_PASSED", "info")]

    def test_superposition_fails_after_collapse(self):
        pytest.importorskip("qutip")
        m = _machine(self.SRC.format(a="[assert: superposition(qs[0])]"))
        assert _codes(m) == [("ASSERTION_FAILED", "error")]


# ---------------------------------------------------------------------------
# §12.7 unreachable state
# ---------------------------------------------------------------------------

class TestUnreachableState:
    def test_no_diagnostic_for_unreachable_state(self):
        pytest.importorskip("qutip")
        source = """# machine Island
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0, q1] |
## state |0> [initial]
## state |done> [final]
## state |island> [assert: entangled(qs[0], qs[1])]
## transitions
| Source | Event | Guard | Target | Action |
| |0> | go | | |done> | apply_H |
| |island> | x | | |island> | apply_H |
## actions
| Name | Signature | Effect |
| apply_H | (qs) -> qs | Hadamard(qs[0]) |
"""
        # |island> is unreachable from |0>; its assertion must not be evaluated.
        assert _codes(_machine(source)) == []
