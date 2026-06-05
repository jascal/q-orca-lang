"""Tests for the stabilizer (Clifford) fast-path backend.

Covers the two foundational pieces: the Clifford classifier
(`q_orca.compiler.stabilizer`) and the stabilizer entanglement-entropy helper
(`q_orca.verifier.stabilizer_entanglement`). Backend-adapter and dispatch
tests follow once those land.
"""

import math

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.compiler.stabilizer import is_clifford, is_clifford_angle


def _machine(path: str):
    return parse_q_orca_markdown(open(path).read()).file.machines[0]


def _gd(name, targets, controls=None, theta=None):
    params = {"theta": theta} if theta is not None else {}
    return {"name": name, "targets": targets, "controls": controls or [], "params": params}


class TestCliffordAngle:
    @pytest.mark.parametrize("k", [0, 1, 2, 3, 4, -1, -2])
    def test_half_pi_multiples_are_clifford(self, k):
        assert is_clifford_angle(k * math.pi / 2)

    @pytest.mark.parametrize("theta", [math.pi / 4, math.pi / 3, 0.1, 3 * math.pi / 4])
    def test_non_multiples_are_not_clifford(self, theta):
        assert not is_clifford_angle(theta)

    def test_unfolded_sum_still_recognized(self):
        # pi/4 + pi/4 reaches us as the float sum (the parser pre-evaluates),
        # so a genuine pi/2 is still recognized.
        assert is_clifford_angle(math.pi / 4 + math.pi / 4)


class TestCliffordClassifier:
    # Standard Bell/GHZ/teleportation/syndrome circuits are Clifford. (Note:
    # deutsch-jozsa is *also* Clifford — its oracle uses only H/X/CNOT/CZ — and
    # vqe-heisenberg binds theta=0.0 at every call site, so neither is a stable
    # negative example; we assert only unambiguous cases here.)
    @pytest.mark.parametrize("name", [
        "bell-entangler", "ghz-state", "quantum-teleportation",
        "active-teleportation", "bit-flip-syndrome",
    ])
    def test_clifford_examples(self, name):
        ok, offenders = is_clifford(_machine(f"examples/{name}.q.orca.md"))
        assert ok, f"expected Clifford, got offenders {offenders}"

    @pytest.mark.parametrize("name,expected_kind", [
        ("qaoa-maxcut", "RZZ"),
        ("vqe-heisenberg-noisy", "Ry"),
        ("vqe-rotation", "Rx"),
    ])
    def test_non_clifford_examples(self, name, expected_kind):
        ok, offenders = is_clifford(_machine(f"examples/{name}.q.orca.md"))
        assert not ok
        kinds = {o["kind"] for o in offenders}
        assert expected_kind in kinds, f"{expected_kind} not in {kinds}"

    def test_offender_carries_location(self):
        ok, offenders = is_clifford(_machine("examples/vqe-rotation.q.orca.md"))
        assert not ok
        assert all("location" in o for o in offenders)


class TestStabilizerEntanglement:
    """Schmidt rank / entropy computed on the tableau must equal the QuTiP path."""

    def setup_method(self):
        pytest.importorskip("stim")
        pytest.importorskip("qutip")

    @pytest.mark.parametrize("label,n,gates,q1,exp_rank", [
        ("product", 2, [("H", [0], [], None)], 0, 1),
        ("bell", 2, [("H", [0], [], None), ("CNOT", [1], [0], None)], 0, 2),
        ("ghz3", 3, [("H", [0], [], None), ("CNOT", [1], [0], None), ("CNOT", [2], [1], None)], 0, 2),
    ])
    def test_schmidt_rank_matches_qutip(self, label, n, gates, q1, exp_rank):
        from qutip import basis
        from q_orca.verifier.stabilizer_entanglement import build_state_simulator, entropy_and_schmidt
        from q_orca.verifier.dynamic import _evolve_path, _schmidt_rank_across_bipartition

        gate_dicts = [_gd(*g) for g in gates]
        sim = build_state_simulator(gate_dicts, n)
        _, stab_rank = entropy_and_schmidt(sim, [q1])

        psi = _evolve_path(basis([2] * n, [0] * n), gate_dicts, n)
        q2 = next(q for q in range(n) if q != q1)
        qutip_rank = _schmidt_rank_across_bipartition(psi, [q1], [q2], n)

        assert stab_rank == exp_rank == qutip_rank

    def test_gf2_rank(self):
        from q_orca.verifier.stabilizer_entanglement import _gf2_rank
        assert _gf2_rank([[1, 0], [0, 1]]) == 2
        assert _gf2_rank([[1, 1], [1, 1]]) == 1   # rows identical over GF(2)
        assert _gf2_rank([[0, 0], [0, 0]]) == 0
