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


def _machine_with_effect(effect: str, n: int = 3):
    """A minimal 1-action machine whose single action runs `effect`."""
    qubits = ", ".join(f"q{i}" for i in range(n))
    src = (
        "# machine M\n\n## context\n| Field | Type | Default |\n|---|---|---|\n"
        f"| qubits | list<qubit> | [{qubits}] |\n\n"
        "## states\n## state |0> [initial]\n## state |done> [final]\n\n"
        "## events\n- go\n\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n|---|---|---|---|---|\n"
        "| |0> | go | | |done> | act |\n\n"
        "## actions\n| Name | Signature | Effect |\n|---|---|---|\n"
        f"| act | (qs) -> qs | {effect} |\n"
    )
    return parse_q_orca_markdown(src).file.machines[0]


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

    def test_large_multiple_recognized(self):
        # pi/2 + 2*pi == 5*(pi/2) — a Clifford multiple beyond [0, 2pi).
        assert is_clifford_angle(math.pi / 2 + 2 * math.pi)
        assert is_clifford_angle(-3 * math.pi / 2)


class TestCliffordClassifierGates:
    """Per-gate classification on minimal constructed machines."""

    @pytest.mark.parametrize("effect", [
        "H(qs[0]); CNOT(qs[0], qs[1])",
        "S(qs[0]); CZ(qs[0], qs[1]); SWAP(qs[1], qs[2])",
        "Rz(qs[0], pi/2); Rx(qs[1], pi)",          # pi/2 multiples
    ])
    def test_clifford_effects(self, effect):
        ok, offenders = is_clifford(_machine_with_effect(effect))
        assert ok, offenders

    @pytest.mark.parametrize("effect,kind", [
        ("T(qs[0])", "T"),
        ("CCNOT(qs[0], qs[1], qs[2])", "CCNOT"),
        ("Rz(qs[0], pi/4)", "Rz"),                 # non-pi/2 multiple
    ])
    def test_non_clifford_effects(self, effect, kind):
        ok, offenders = is_clifford(_machine_with_effect(effect))
        assert not ok
        assert kind in {o["kind"] for o in offenders}


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


class TestBackendResolution:
    """Auto-routing + force/refuse in the Stage-4b dispatcher."""

    def _resolve(self, machine, requested):
        from q_orca.verifier import _resolve_dynamic_backend
        errors = []
        resolved = _resolve_dynamic_backend(machine, requested, errors)
        return resolved, errors

    def test_auto_routes_clifford_to_stim(self):
        pytest.importorskip("stim")
        resolved, errors = self._resolve(_machine("examples/bell-entangler.q.orca.md"), "auto")
        assert resolved == "stim"
        assert errors == []

    def test_auto_routes_non_clifford_to_qutip(self):
        resolved, errors = self._resolve(_machine("examples/qaoa-maxcut.q.orca.md"), "auto")
        assert resolved == "qutip"
        assert errors == []

    def test_state_vector_alias_maps_to_qutip(self):
        resolved, _ = self._resolve(_machine("examples/bell-entangler.q.orca.md"), "state-vector")
        assert resolved == "qutip"

    def test_force_stabilizer_on_non_clifford_is_fatal(self):
        machine = _machine("examples/qaoa-maxcut.q.orca.md")
        resolved, errors = self._resolve(machine, "stabilizer")
        assert resolved is None  # fatal — simulation skipped
        codes = [(e.code, e.severity) for e in errors]
        assert ("NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND", "error") in codes

    def test_force_stabilizer_with_fallback_warns_and_uses_qutip(self):
        machine = _machine("examples/qaoa-maxcut.q.orca.md")
        machine.assertion_policy.stabilizer_fallback = "state-vector"
        resolved, errors = self._resolve(machine, "stabilizer")
        assert resolved == "qutip"
        codes = [(e.code, e.severity) for e in errors]
        assert ("NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND", "warning") in codes

    def test_explicit_qutip_unchanged(self):
        resolved, errors = self._resolve(_machine("examples/bell-entangler.q.orca.md"), "qutip")
        assert resolved == "qutip"
        assert errors == []

    def test_end_to_end_force_error(self):
        from q_orca.verifier import verify, VerifyOptions
        machine = _machine("examples/qaoa-maxcut.q.orca.md")
        result = verify(machine, VerifyOptions(backend="stabilizer"))
        assert not result.valid
        assert any(e.code == "NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND" for e in result.errors)

    def test_force_error_names_gate_and_location(self):
        machine = _machine_with_effect("T(qs[0])")
        _, errors = self._resolve(machine, "stim")
        err = next(e for e in errors if e.code == "NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND")
        assert "T" in err.message
        assert "act" in err.message  # the offending action is named in the message
        assert err.location  # structured location is populated too

    def test_qec_example_routes_to_stim(self):
        # The doc claims bit-flip-syndrome (a 5-qubit QEC machine) routes to the
        # fast path under auto — confirm it resolves to stim and verifies clean.
        pytest.importorskip("stim")
        from q_orca.verifier import verify, VerifyOptions
        machine = _machine("examples/bit-flip-syndrome.q.orca.md")
        resolved, _ = self._resolve(machine, "auto")
        assert resolved == "stim"
        result = verify(machine, VerifyOptions(backend="stim"))
        assert result.valid


class TestAssertionPolicyStabilizerFallback:
    """Parser support for the `stabilizer_fallback` assertion-policy key."""

    def _parse_policy(self, value):
        from q_orca.parser.markdown_parser import parse_q_orca_markdown
        src = (
            "# machine M\n\n## context\n| Field | Type | Default |\n"
            "|---|---|---|\n| qubits | list<qubit> | [q0] |\n\n"
            "## states\n## state |0> [initial]\n\n## events\n- e\n\n"
            "## assertion policy\n| Setting | Value |\n|---|---|\n"
            f"| stabilizer_fallback | {value} |\n"
        )
        return parse_q_orca_markdown(src)

    def test_valid_state_vector(self):
        res = self._parse_policy("state-vector")
        assert res.file.machines[0].assertion_policy.stabilizer_fallback == "state-vector"

    def test_default_is_error(self):
        from q_orca.ast import AssertionPolicy
        assert AssertionPolicy().stabilizer_fallback == "error"

    def test_invalid_value_errors(self):
        res = self._parse_policy("qutip")
        assert any("stabilizer_fallback" in e and "qutip" in e for e in res.errors)


class TestSchmidtRankInvariantOnStabilizer:
    def test_bell_schmidt_rank_invariant_on_stim(self):
        pytest.importorskip("stim")
        from q_orca.verifier import verify, VerifyOptions
        machine = _machine("examples/bell-entangler.q.orca.md")
        result = verify(machine, VerifyOptions(backend="stim"))
        # No DYNAMIC_NO_ENTANGLEMENT — the Bell state's entanglement is confirmed
        # on the tableau, same verdict as the state-vector path.
        assert not any(e.code == "DYNAMIC_NO_ENTANGLEMENT" for e in result.errors)


class TestAutoFallbackWhenStimAbsent:
    def test_auto_clifford_falls_back_to_qutip_without_stim(self, monkeypatch):
        # With stim unavailable, `auto` must not pick stim — it routes a Clifford
        # machine to the state-vector backend instead (no error, no warning).
        import q_orca.backends.stim_backend as sb
        monkeypatch.setattr(sb, "AVAILABLE", False)
        from q_orca.verifier import _resolve_dynamic_backend
        errors = []
        resolved = _resolve_dynamic_backend(_machine("examples/bell-entangler.q.orca.md"), "auto", errors)
        assert resolved == "qutip"
        assert errors == []


class TestLargeCliffordIntractableForStatevector:
    """The headline win: a Clifford machine well past the state-vector wall
    verifies on the stabilizer tableau in well under a second."""

    def _ghz_machine(self, n: int):
        qubits = ", ".join(f"q{i}" for i in range(n))
        cnots = "; ".join(f"CNOT(qs[{i}], qs[{i + 1}])" for i in range(n - 1))
        src = (
            "# machine GHZWide\n\n## context\n| Field | Type | Default |\n|---|---|---|\n"
            f"| qubits | list<qubit> | [{qubits}] |\n\n"
            "## states\n## state |0> [initial]\n## state |ghz> [final]\n> GHZ entangled state\n\n"
            "## events\n- prepare\n\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n|---|---|---|---|---|\n"
            "| |0> | prepare | | |ghz> | build |\n\n"
            "## actions\n| Name | Signature | Effect |\n|---|---|---|\n"
            f"| build | (qs) -> qs | H(qs[0]); {cnots} |\n\n"
            "## verification rules\n- entanglement\n"
        )
        return parse_q_orca_markdown(src).file.machines[0]

    def test_30_qubit_ghz_verifies_on_stim(self):
        pytest.importorskip("stim")
        from q_orca.compiler.stabilizer import is_clifford
        from q_orca.verifier.dynamic import dynamic_verify_stabilizer

        machine = self._ghz_machine(30)  # 2**30 statevector — far past the wall
        ok, offenders = is_clifford(machine)
        assert ok, offenders
        result = dynamic_verify_stabilizer(machine)
        # Entanglement confirmed (GHZ q0 is entangled with the rest), no failure.
        assert not any(e.code == "DYNAMIC_NO_ENTANGLEMENT" for e in result.errors)
        assert result.valid
