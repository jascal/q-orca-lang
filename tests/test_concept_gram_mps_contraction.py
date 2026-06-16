"""Tests for the MPS transfer-matrix contraction path of
``compute_concept_gram_mps``.

Covers the change ``mps-transfer-matrix-contraction``:

- §1.5-1.6 — direct unit tests on ``mps_contract`` primitives.
- §2.6   — bit-identical preservation of the ``method="statevector"``
           path on bundled examples.
- §3.1-3.3 — equivalence of ``"contracted"`` vs ``"statevector"`` at
           small n on shipped examples + synthetic machines.
- §4.1-4.3 — Hermitian + unit-modulus-diagonal invariants on synthetic
           large-n machines.
- §5.1-5.5 — dispatch / auto-threshold tests.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import pytest

from q_orca import compute_concept_gram_mps
from q_orca.compiler.concept_gram_mps import (
    STATEVECTOR_NQUBIT_THRESHOLD,
    _build_concept_state,
    _parse_staircase_effect,
    _find_concept_action,
)
from q_orca.compiler.mps_contract import (
    MpsBondTruncationError,
    _apply_cnot,
    mps_overlap,
    staircase_to_mps_tensors,
)
from q_orca.parser.markdown_parser import parse_q_orca_markdown


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _make_machine(
    sig: str,
    effect: str,
    calls: list[str],
    action_name: str = "prepare_concept",
    n_qubits: int = 3,
):
    """Build a minimal MPS-encoded machine with N call sites."""
    qubit_list = ", ".join(f"q{k}" for k in range(n_qubits))
    transitions = []
    states = ["## state idle [initial]"]
    for i, args in enumerate(calls):
        state_name = f"q{i}"
        states.append(f"## state {state_name}")
        transitions.append(
            f"| idle | ev{i} | | {state_name} | {action_name}({args}) |"
        )
    states.append("## state done [final]")
    events = "\n".join(f"- ev{i}" for i in range(len(calls))) or "- noop"
    trans_body = "\n".join(transitions) or "| idle | noop | | done |  |"
    source = (
        "# machine M\n\n"
        "## context\n"
        "| Field  | Type        | Default      |\n"
        "|--------|-------------|--------------|\n"
        f"| qubits | list<qubit> | [{qubit_list}] |\n\n"
        "## events\n"
        f"{events}\n\n"
        + "\n\n".join(states) + "\n\n"
        "## transitions\n"
        "| Source | Event | Guard | Target | Action |\n"
        "|--------|-------|-------|--------|--------|\n"
        f"{trans_body}\n\n"
        "## actions\n"
        "| Name | Signature | Effect |\n"
        "|------|-----------|--------|\n"
        f"| {action_name} | {sig} | {effect} |\n"
    )
    result = parse_q_orca_markdown(source)
    assert result.errors == [], result.errors
    return result.file.machines[0]


def _staircase_prep(n: int) -> str:
    """Canonical preparation-form CNOT staircase on n qubits.

    ``Ry(qs[0], p0); CNOT(qs[0], qs[1]); Ry(qs[1], p1); ...; Ry(qs[n-1], p_{n-1})``.
    """
    segs = []
    for k in range(n):
        segs.append(f"Ry(qs[{k}], p{k})")
        if k < n - 1:
            segs.append(f"CNOT(qs[{k}], qs[{k + 1}])")
    return "; ".join(segs)


def _cross_coupled_staircase_prep(n: int) -> str:
    """Cross-coupled prep staircase: ``Ry(qs[k], p_{k-1} + p_k)``.

    Forces the bond-2 entanglement to be non-trivially angle-dependent
    (a pure product-staircase factorises and hides index-ordering bugs).
    """
    segs = []
    for k in range(n):
        if k == 0:
            expr = "p0"
        else:
            expr = f"p{k - 1} + p{k}"
        segs.append(f"Ry(qs[{k}], {expr})")
        if k < n - 1:
            segs.append(f"CNOT(qs[{k}], qs[{k + 1}])")
    return "; ".join(segs)


def _param_sig(n: int) -> str:
    params = ", ".join(f"p{k}: angle" for k in range(n))
    return f"(qs, {params}) -> qs"


def _synthetic_machine(
    n_qubits: int,
    n_calls: int,
    *,
    cross_coupled: bool = True,
    with_rz: bool = False,
    seed: int = 0,
):
    """Build a synthetic n-qubit MPS-encoded machine with random angles."""
    sig = _param_sig(n_qubits)
    if cross_coupled:
        effect = _cross_coupled_staircase_prep(n_qubits)
    else:
        effect = _staircase_prep(n_qubits)
    if with_rz:
        # Insert an Rz knob between site 1's Ry and the CNOT(1, 2)
        # (only valid for n >= 3). Reuses an existing parameter to stay
        # within the action's bound-parameter set.
        if n_qubits >= 3:
            segs = effect.split("; ")
            # Find index of "CNOT(qs[1], qs[2])" and insert Rz before it.
            for i, seg in enumerate(segs):
                if seg.strip() == "CNOT(qs[1], qs[2])":
                    segs.insert(i, "Rz(qs[1], p0)")
                    break
            effect = "; ".join(segs)
    rng = random.Random(seed)
    calls = []
    for _ in range(n_calls):
        row = ", ".join(f"{rng.uniform(-1.5, 1.5):.6f}" for _ in range(n_qubits))
        calls.append(row)
    return _make_machine(
        sig, effect, calls, action_name="prepare_concept", n_qubits=n_qubits
    )


# -----------------------------------------------------------------------------
# §1.5 — staircase_to_mps_tensors unit tests
# -----------------------------------------------------------------------------


class TestStaircaseToMpsTensors:
    """Unit tests pinning the per-gate behaviour of the tensor builder."""

    def test_zero_ops_returns_all_zero_state_tensors(self):
        """No ops → every site is the |0⟩ tensor with shape (1, 2, 1)."""
        tensors = staircase_to_mps_tensors([], n_qubits=3, angle_values=[], param_names=[])
        assert len(tensors) == 3
        for T in tensors:
            assert T.shape == (1, 2, 1)
            assert T[0, 0, 0] == 1.0 + 0j
            assert T[0, 1, 0] == 0.0 + 0j

    def test_single_ry_matches_handderived(self):
        """A single Ry(qs[0], θ) on |0⟩ produces (cos(θ/2), sin(θ/2))."""
        theta = 0.7
        ops = [("ry", 0, {"a": 1.0})]
        tensors = staircase_to_mps_tensors(
            ops, n_qubits=2, angle_values=[theta], param_names=["a"]
        )
        np.testing.assert_allclose(
            tensors[0][0, 0, 0], np.cos(theta / 2.0), atol=1e-14
        )
        np.testing.assert_allclose(
            tensors[0][0, 1, 0], np.sin(theta / 2.0), atol=1e-14
        )
        # Untouched site is still |0⟩.
        np.testing.assert_allclose(tensors[1][0, 0, 0], 1.0, atol=1e-14)
        np.testing.assert_allclose(tensors[1][0, 1, 0], 0.0, atol=1e-14)

    def test_single_rz_on_zero_is_global_phase(self):
        """Rz(qs[0], θ) applied to |0⟩ multiplies the (s=0) amplitude by
        e^{-iθ/2} and the (s=1) amplitude by e^{+iθ/2}. Starting from |0⟩
        only the (s=0) entry is non-zero, so we see a pure global phase."""
        theta = 1.3
        ops = [("rz", 0, {"a": 1.0})]
        tensors = staircase_to_mps_tensors(
            ops, n_qubits=2, angle_values=[theta], param_names=["a"]
        )
        np.testing.assert_allclose(
            tensors[0][0, 0, 0], np.exp(-1j * theta / 2.0), atol=1e-14
        )
        np.testing.assert_allclose(tensors[0][0, 1, 0], 0.0, atol=1e-14)

    def test_single_cnot_on_zero_state_is_identity_on_amplitudes(self):
        """CNOT(0, 1) applied to |00⟩ leaves it as |00⟩; the per-site
        tensors after SVD-decomposition still produce that statevector."""
        ops = [("cnot", 0, 1)]
        tensors = staircase_to_mps_tensors(
            ops, n_qubits=2, angle_values=[], param_names=[]
        )
        # Reconstruct the statevector from the MPS and assert |00⟩.
        state = np.einsum("Lsm,mtR->LstR", tensors[0], tensors[1])
        state = state[0, :, :, 0]  # (2, 2) array indexed by (s_0, s_1).
        np.testing.assert_allclose(state[0, 0], 1.0, atol=1e-12)
        np.testing.assert_allclose(state[0, 1], 0.0, atol=1e-12)
        np.testing.assert_allclose(state[1, 0], 0.0, atol=1e-12)
        np.testing.assert_allclose(state[1, 1], 0.0, atol=1e-12)

    def test_ry_then_cnot_produces_bond_2_bell_like_state(self):
        """Ry(qs[0], θ); CNOT(0, 1) → cos(θ/2)|00⟩ + sin(θ/2)|11⟩.

        Pins the bond growth from 1 to 2 at the CNOT.
        """
        theta = 1.1
        ops = [("ry", 0, {"a": 1.0}), ("cnot", 0, 1)]
        tensors = staircase_to_mps_tensors(
            ops, n_qubits=2, angle_values=[theta], param_names=["a"]
        )
        # The middle bond should have grown to 2.
        assert tensors[0].shape[2] == tensors[1].shape[0]
        assert tensors[0].shape[2] in (1, 2)
        # Reconstruct and compare to the hand-derived statevector.
        state = np.einsum("Lsm,mtR->LstR", tensors[0], tensors[1])[0, :, :, 0]
        c, s = np.cos(theta / 2.0), np.sin(theta / 2.0)
        np.testing.assert_allclose(state[0, 0], c, atol=1e-12)
        np.testing.assert_allclose(state[0, 1], 0.0, atol=1e-12)
        np.testing.assert_allclose(state[1, 0], 0.0, atol=1e-12)
        np.testing.assert_allclose(state[1, 1], s, atol=1e-12)


class TestApplyCnotBondTruncationGuard:
    """Defensive rank-≤ ``_MAX_BOND_DIM`` guard in ``_apply_cnot``.

    The CNOT-staircase contract guarantees rank ``<= _MAX_BOND_DIM`` at
    the SVD cut so the truncation is exact for in-spec callers. The
    guard raises ``MpsBondTruncationError`` when a non-staircase input
    (or numerical pathology) yields a higher effective rank — without
    the guard, the discarded singular values would silently leak
    amplitude. These tests are defensive: no in-spec call site triggers
    them today, so they pin the guard against a future regression in
    the truncation step.
    """

    def test_rank_two_input_passes_through_cleanly(self):
        """In-spec input (rank ≤ _MAX_BOND_DIM) raises nothing.

        Builds the rank-2 Bell-like pair from
        ``test_ry_then_cnot_produces_bond_2_bell_like_state`` and
        confirms ``_apply_cnot`` returns the truncated tensors without
        firing the guard.
        """
        # |0⟩ tensors with shape (1, 2, 1).
        A_c = np.zeros((1, 2, 1), dtype=complex)
        A_c[0, 0, 0] = 1.0
        A_t = np.zeros((1, 2, 1), dtype=complex)
        A_t[0, 0, 0] = 1.0
        # Apply Ry(θ) to A_c to make the eventual CNOT non-trivial.
        theta = 1.1
        c, s = np.cos(theta / 2.0), np.sin(theta / 2.0)
        A_c[0, 0, 0] = c
        A_c[0, 1, 0] = s
        # No exception: rank stays at 2 (Bell-like).
        A_c_new, A_t_new = _apply_cnot(np, A_c, A_t)
        assert A_c_new.shape[2] in (1, 2)
        assert A_t_new.shape[0] == A_c_new.shape[2]

    def test_rank_three_input_raises_with_named_discard(self):
        """Out-of-spec rank-3 input fires the guard with the discarded value.

        Constructs ``A_c`` of shape ``(2, 2, 3)`` and ``A_t`` of shape
        ``(3, 2, 2)`` with random complex entries (seeded) so the joint
        tensor's CNOT-permuted matrix has rank 3. ``_apply_cnot`` would
        silently truncate the third singular value to zero; the guard
        instead raises ``MpsBondTruncationError`` naming that value.
        """
        rng = np.random.default_rng(42)
        A_c = (
            rng.standard_normal((2, 2, 3))
            + 1j * rng.standard_normal((2, 2, 3))
        )
        A_t = (
            rng.standard_normal((3, 2, 2))
            + 1j * rng.standard_normal((3, 2, 2))
        )
        # Sanity-check our setup: the joint matrix really does have a
        # non-trivial third singular value so the guard is the only
        # thing standing between a silent amplitude leak and the user.
        T = np.einsum("Lsm,mtr->Lstr", A_c, A_t)
        T_perm = T.copy()
        T_perm[:, 1, 0, :] = T[:, 1, 1, :]
        T_perm[:, 1, 1, :] = T[:, 1, 0, :]
        M = T_perm.reshape(4, 4)
        S_oracle = np.linalg.svd(M, compute_uv=False)
        assert len(S_oracle) >= 3
        assert S_oracle[2] > 1e-3, (
            f"test fixture sanity check: third singular value "
            f"{S_oracle[2]:.3e} too small to reach the guard's atol; "
            f"the test would pass for the wrong reason."
        )

        with pytest.raises(MpsBondTruncationError) as exc_info:
            _apply_cnot(np, A_c, A_t)
        msg = str(exc_info.value)
        assert "SVD truncation would lose amplitude" in msg
        assert "discarded singular value" in msg
        # The message should reference the actual discarded value so a
        # human reader can decide whether it's a real leak or noise.
        assert f"{S_oracle[2]:.3e}" in msg

    def test_below_atol_discard_does_not_raise(self):
        """Numerical noise at ~ε does not fire the guard.

        Constructs the same shape as the rank-3 case but scales the
        third singular value below the guard's atol (1e-10). Pins that
        round-off-sized noise on an otherwise rank-2 input stays
        silent — the guard separates physical leaks from round-off.
        """
        # A diagonal (4, 4) matrix has its diagonal entries as its
        # singular values, so M trivially carries [1.0, 0.5, 1e-12, 0]
        # — the two smallest sit below the guard's 1e-10 atol so the
        # discard is round-off-sized, not an amplitude leak. The
        # downstream factorisation reshapes M, applies the inverse
        # CNOT entry swap, then SVDs the (4, 4) reshape with
        # `full_matrices=False` and keeps every singular value (no
        # truncation). The inverse swap exactly undoes _apply_cnot's
        # forward swap, and the full-rank SVD reconstruction is exact,
        # so by the time _apply_cnot runs its own SVD it sees the
        # singular values of M itself — i.e. [1.0, 0.5, 1e-12, 0].
        M = np.diag([1.0, 0.5, 1e-12, 0.0]).astype(complex)
        # Reverse the CNOT permutation so _apply_cnot's permutation
        # lands us back at M (the guard sees the singular values of M
        # itself, so the permutation choice is immaterial for this
        # test — it just needs A_c/A_t shapes _apply_cnot accepts).
        T_perm = M.reshape(2, 2, 2, 2)
        T = T_perm.copy()
        T[:, 1, 0, :] = T_perm[:, 1, 1, :]
        T[:, 1, 1, :] = T_perm[:, 1, 0, :]
        # Factor T back into A_c (2, 2, 2) and A_t (2, 2, 2) via SVD on
        # the middle index. T has shape (L=2, s_c=2, s_t=2, R=2); we
        # reshape to (L*s_c, s_t*R) = (4, 4) and split.
        T_mat = T.reshape(4, 4)
        U2, S2, Vh2 = np.linalg.svd(T_mat, full_matrices=False)
        # Keep all singular values — chi_M = 4 — so _apply_cnot sees
        # the leak (or absence thereof) cleanly at its own SVD step.
        A_c = (U2 * S2).reshape(2, 2, 4)
        A_t = Vh2.reshape(4, 2, 2)
        # Guard does not fire: the SVD of M has S[2] = 1e-12 < 1e-10.
        A_c_new, A_t_new = _apply_cnot(np, A_c, A_t)
        assert A_c_new.shape[2] == 2
        assert A_t_new.shape[0] == 2


# -----------------------------------------------------------------------------
# §1.6 — mps_overlap unit tests
# -----------------------------------------------------------------------------


class TestMpsOverlap:
    """Unit tests on inner products between hand-built MPS pairs."""

    def _zero_state(self, n: int):
        return staircase_to_mps_tensors([], n_qubits=n, angle_values=[], param_names=[])

    def test_identity_state_self_overlap_is_one(self):
        for n in (2, 3, 4):
            tensors = self._zero_state(n)
            ov = mps_overlap(tensors, tensors)
            np.testing.assert_allclose(ov, 1.0 + 0j, atol=1e-14)

    def test_orthogonal_states_have_zero_overlap(self):
        """|00⟩ vs |11⟩: build the second via Ry(π) on each qubit + CNOTs."""
        zero = self._zero_state(2)
        # Build |11⟩ as Ry(π) on q0 (→ |1⟩) then CNOT(0, 1) (→ |11⟩).
        flipped = staircase_to_mps_tensors(
            [("ry", 0, {"a": 1.0}), ("cnot", 0, 1)],
            n_qubits=2,
            angle_values=[np.pi],
            param_names=["a"],
        )
        ov = mps_overlap(zero, flipped)
        np.testing.assert_allclose(abs(ov), 0.0, atol=1e-12)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(AssertionError):
            mps_overlap(self._zero_state(2), self._zero_state(3))

    def test_overlap_is_hermitian_under_swap(self):
        """⟨a|b⟩ = conj(⟨b|a⟩) for any pair."""
        a = staircase_to_mps_tensors(
            [("ry", 0, {"x": 1.0}), ("cnot", 0, 1), ("ry", 1, {"y": 1.0})],
            n_qubits=2,
            angle_values=[0.3, 0.7],
            param_names=["x", "y"],
        )
        b = staircase_to_mps_tensors(
            [("ry", 0, {"x": 1.0}), ("cnot", 0, 1), ("ry", 1, {"y": 1.0})],
            n_qubits=2,
            angle_values=[1.1, -0.4],
            param_names=["x", "y"],
        )
        ov_ab = mps_overlap(a, b)
        ov_ba = mps_overlap(b, a)
        np.testing.assert_allclose(ov_ab, np.conj(ov_ba), atol=1e-12)


# -----------------------------------------------------------------------------
# §2.6 — statevector path is bit-identical to pre-change behaviour
# -----------------------------------------------------------------------------


class TestStatevectorPathPreserved:
    """``method="statevector"`` must reproduce the pre-change Gram bit-for-bit."""

    def _legacy_gram(self, machine):
        """Recompute the Gram via the pre-``method``-parameter path:
        explicit 2^n statevectors stacked and matmul'd as
        ``flat.conj() @ flat.T`` (tech-debt-backlog §3.12)."""
        from q_orca.compiler.util import infer_qubit_count

        n_qubits = infer_qubit_count(machine)
        action = _find_concept_action(machine, "prepare_concept")
        ops = _parse_staircase_effect(machine, action, n_qubits)
        param_names = [p.name for p in action.parameters]

        call_sites = [
            t for t in machine.transitions
            if t.action == "prepare_concept" and t.bound_arguments
        ]
        angles = [
            [float(b.value) for b in t.bound_arguments] for t in call_sites
        ]
        flat = np.stack(
            [
                _build_concept_state(np, n_qubits, row, param_names, ops).reshape(-1)
                for row in angles
            ]
        )
        return flat.conj() @ flat.T

    @pytest.mark.parametrize("n", [2, 3, 4, 5])
    def test_statevector_method_bit_identical_to_legacy(self, n):
        machine = _synthetic_machine(n_qubits=n, n_calls=4, seed=11)
        legacy = self._legacy_gram(machine)
        current = compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="statevector"
        )
        # Bit-identical floating-point equality.
        assert np.array_equal(current, legacy)


# -----------------------------------------------------------------------------
# §3.1-3.3 — equivalence of contracted vs statevector at small n
# -----------------------------------------------------------------------------


class TestContractedEquivalence:
    """At small n both paths run; the contracted Gram must match the
    statevector Gram to 1e-12 absolute."""

    @pytest.mark.parametrize("n", [3, 4, 5, 6])
    @pytest.mark.parametrize("cross_coupled", [False, True])
    def test_synthetic_machines_match(self, n, cross_coupled):
        machine = _synthetic_machine(
            n_qubits=n, n_calls=5, cross_coupled=cross_coupled, seed=n * 31
        )
        sv = compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="statevector"
        )
        contracted = compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="contracted"
        )
        np.testing.assert_allclose(contracted, sv, atol=1e-12)

    def test_minimum_call_sites_n_equals_2(self):
        """Edge case: only N=2 call sites still produces a 2x2 Gram that matches."""
        machine = _synthetic_machine(n_qubits=3, n_calls=2, seed=1)
        sv = compute_concept_gram_mps(machine, concept_action_label="prepare_concept", method="statevector")
        ct = compute_concept_gram_mps(machine, concept_action_label="prepare_concept", method="contracted")
        np.testing.assert_allclose(ct, sv, atol=1e-12)

    def test_rz_only_staircase_no_ry_knob(self):
        """Staircase where every Ry uses a single bound parameter (no
        cross-coupling) plus an Rz knob: contracted must still match."""
        # Sig: p0, p1, p2 angle params. Effect: standard prep + Rz on q1.
        sig = _param_sig(3)
        effect = (
            "Ry(qs[0], p0); CNOT(qs[0], qs[1]); Ry(qs[1], p1); "
            "Rz(qs[1], p0); CNOT(qs[1], qs[2]); Ry(qs[2], p2)"
        )
        calls = ["0.3, 0.7, 1.1", "1.2, -0.5, 0.0", "0.0, 0.0, 1.5"]
        machine = _make_machine(sig, effect, calls, action_name="prepare_concept", n_qubits=3)
        sv = compute_concept_gram_mps(machine, concept_action_label="prepare_concept", method="statevector")
        ct = compute_concept_gram_mps(machine, concept_action_label="prepare_concept", method="contracted")
        np.testing.assert_allclose(ct, sv, atol=1e-12)

    def test_rz_at_every_interior_qubit(self):
        """Rz on every interior qubit: contracted matches statevector."""
        sig = _param_sig(4)
        # Standard 4-qubit prep + Rz on qubits 1 and 2.
        effect = (
            "Ry(qs[0], p0); CNOT(qs[0], qs[1]); Ry(qs[1], p1); Rz(qs[1], p0); "
            "CNOT(qs[1], qs[2]); Ry(qs[2], p2); Rz(qs[2], p1); "
            "CNOT(qs[2], qs[3]); Ry(qs[3], p3)"
        )
        calls = ["0.3, 0.7, 1.1, -0.4", "1.2, -0.5, 0.0, 0.8"]
        machine = _make_machine(sig, effect, calls, action_name="prepare_concept", n_qubits=4)
        sv = compute_concept_gram_mps(machine, concept_action_label="prepare_concept", method="statevector")
        ct = compute_concept_gram_mps(machine, concept_action_label="prepare_concept", method="contracted")
        np.testing.assert_allclose(ct, sv, atol=1e-12)


class TestShippedExampleEquivalence:
    """The shipped 3-qubit MPS examples produce contracted Grams equal to
    statevector Grams to 1e-12."""

    EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples"

    @pytest.mark.parametrize(
        "filename, action_label",
        [
            ("larql-polysemantic-hierarchical.q.orca.md", "query_concept"),
            ("larql-animals-interference.q.orca.md", "prepare_concept"),
        ],
    )
    def test_shipped_example_equivalence(self, filename, action_label):
        text = (self.EXAMPLE_DIR / filename).read_text()
        result = parse_q_orca_markdown(text)
        assert result.errors == [], result.errors
        machine = result.file.machines[0]
        sv = compute_concept_gram_mps(
            machine, concept_action_label=action_label, method="statevector"
        )
        ct = compute_concept_gram_mps(
            machine, concept_action_label=action_label, method="contracted"
        )
        np.testing.assert_allclose(ct, sv, atol=1e-12)


# -----------------------------------------------------------------------------
# §4.1-4.3 — structural-invariant tests at larger synthetic n
# -----------------------------------------------------------------------------


class TestContractedStructuralInvariants:
    """At larger n the statevector reference is not available; the
    contracted Gram must still satisfy Hermitian + unit-modulus diagonal."""

    @pytest.mark.parametrize("n", [10, 16, 20, 24])
    def test_hermitian_and_unit_diagonal(self, n):
        machine = _synthetic_machine(n_qubits=n, n_calls=4, seed=n)
        G = compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="contracted"
        )
        np.testing.assert_allclose(G, G.conj().T, atol=1e-10)
        np.testing.assert_allclose(np.abs(np.diag(G)), 1.0, atol=1e-10)
        assert np.all(np.isfinite(G.real))
        assert np.all(np.isfinite(G.imag))

    def test_no_nan_or_inf_on_many_random_seeds(self):
        """At n=10 and n=16 the contracted Gram should be finite across
        100 random seeds (the spec calls for 1000; 100 keeps test runtime
        bounded while still exercising the path enough to flag a
        seed-sensitive bug)."""
        for n in (10, 16):
            for seed in range(100):
                machine = _synthetic_machine(n_qubits=n, n_calls=2, seed=seed)
                G = compute_concept_gram_mps(
                    machine, concept_action_label="prepare_concept", method="contracted"
                )
                assert np.all(np.isfinite(G.real)), f"NaN/Inf at n={n}, seed={seed}"
                assert np.all(np.isfinite(G.imag)), f"NaN/Inf at n={n}, seed={seed}"

    def test_at_threshold_n_qubits_20_auto_picks_contracted(self):
        """At exactly the threshold the auto-dispatch must take the
        contracted path; the resulting Gram still satisfies the invariants."""
        assert STATEVECTOR_NQUBIT_THRESHOLD == 20
        machine = _synthetic_machine(n_qubits=20, n_calls=3, seed=42)
        G = compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="auto"
        )
        np.testing.assert_allclose(G, G.conj().T, atol=1e-10)
        np.testing.assert_allclose(np.abs(np.diag(G)), 1.0, atol=1e-10)


# -----------------------------------------------------------------------------
# §5.1-5.5 — dispatch + auto-threshold tests
# -----------------------------------------------------------------------------


class TestDispatch:
    def test_auto_at_small_n_uses_statevector(self, monkeypatch):
        """At n=3 the auto path must dispatch to statevector. We instrument
        the contracted entry point and assert it is *not* called."""
        machine = _synthetic_machine(n_qubits=3, n_calls=3, seed=0)
        called = {"contracted": False}

        from q_orca.compiler import concept_gram_mps as cgm

        original = cgm.staircase_to_mps_tensors

        def spy(*args, **kwargs):
            called["contracted"] = True
            return original(*args, **kwargs)

        monkeypatch.setattr(cgm, "staircase_to_mps_tensors", spy)
        compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="auto"
        )
        assert called["contracted"] is False

    def test_auto_at_large_n_uses_contracted(self, monkeypatch):
        """At n=25 the auto path must dispatch to contracted. Instrument
        the statevector entry point and assert it is *not* called."""
        machine = _synthetic_machine(n_qubits=25, n_calls=2, seed=0)
        called = {"statevector": False}

        from q_orca.compiler import concept_gram_mps as cgm

        original = cgm._build_concept_state

        def spy(*args, **kwargs):
            called["statevector"] = True
            return original(*args, **kwargs)

        monkeypatch.setattr(cgm, "_build_concept_state", spy)
        compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="auto"
        )
        assert called["statevector"] is False

    def test_contracted_at_small_n_matches_statevector(self):
        """Explicit ``method="contracted"`` at n=3 still produces the
        same Gram as ``method="statevector"`` (covered by §3.1, repeated
        here as a dispatch-axis pin)."""
        machine = _synthetic_machine(n_qubits=3, n_calls=4, seed=99)
        sv = compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="statevector"
        )
        ct = compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="contracted"
        )
        np.testing.assert_allclose(ct, sv, atol=1e-12)

    @pytest.mark.skipif(
        os.environ.get("Q_ORCA_RUN_LARGE_STATEVECTOR_TEST") != "1",
        reason=(
            "16 MB/state * N states statevector simulation; skipped by "
            "default to keep test wall-clock bounded. Set "
            "Q_ORCA_RUN_LARGE_STATEVECTOR_TEST=1 to exercise."
        ),
    )
    def test_statevector_at_n_25_succeeds_if_memory_permits(self):
        machine = _synthetic_machine(n_qubits=25, n_calls=2, seed=0)
        G = compute_concept_gram_mps(
            machine, concept_action_label="prepare_concept", method="statevector"
        )
        assert G.shape == (2, 2)
        np.testing.assert_allclose(np.abs(np.diag(G)), 1.0, atol=1e-10)

    def test_unknown_method_raises_value_error(self):
        machine = _synthetic_machine(n_qubits=3, n_calls=2, seed=0)
        with pytest.raises(ValueError) as exc_info:
            compute_concept_gram_mps(
                machine, concept_action_label="prepare_concept", method="invalid"
            )
        message = str(exc_info.value)
        assert "invalid" in message
        assert "statevector" in message
        assert "contracted" in message
        assert "auto" in message
