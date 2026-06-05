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


class TestCompileToStim:
    """compile_to_stim gate / measurement / feedforward mapping + diagnostics."""

    def setup_method(self):
        pytest.importorskip("stim")

    def test_gate_mapping(self):
        from q_orca.compiler.stabilizer import compile_to_stim
        circ = str(compile_to_stim(_machine("examples/bell-entangler.q.orca.md")))
        assert circ == "H 0\nCX 0 1"

    def test_measurement_emits_M(self):
        from q_orca.compiler.stabilizer import compile_to_stim
        circ = str(compile_to_stim(_machine("examples/active-teleportation.q.orca.md")))
        assert "M 0 1" in circ

    def test_feedforward_record_indexing(self):
        # b1 (measured second) → rec[-1]; b0 (measured first) → rec[-2].
        from q_orca.compiler.stabilizer import compile_to_stim
        circ = str(compile_to_stim(_machine("examples/active-teleportation.q.orca.md")))
        assert "CX rec[-1] 2" in circ   # if b1 == 1: X(q2)
        assert "CZ rec[-2] 2" in circ   # if b0 == 1: Z(q2)

    def test_feedforward_on_earliest_of_three_bits(self):
        # 3 measurements then a correction on the *first* bit → rec[-3], not -1.
        from q_orca.compiler.stabilizer import compile_to_stim
        src = (
            "# machine M\n\n## context\n| Field | Type | Default |\n|---|---|---|\n"
            "| qubits | list<qubit> | [q0, q1, q2, q3] |\n| bits | list<bit> | [b0, b1, b2] |\n\n"
            "## states\n## state |s0> [initial]\n## state |s1>\n## state |s2>\n"
            "## state |s3>\n## state |done> [final]\n\n"
            "## events\n- m0e\n- m1e\n- m2e\n- corre\n\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n|---|---|---|---|---|\n"
            "| |s0> | m0e | | |s1> | meas0 |\n| |s1> | m1e | | |s2> | meas1 |\n"
            "| |s2> | m2e | | |s3> | meas2 |\n| |s3> | corre | | |done> | corr0 |\n\n"
            "## actions\n| Name | Signature | Effect |\n|---|---|---|\n"
            "| meas0 | (qs) -> qs | measure(qs[0]) -> bits[0] |\n"
            "| meas1 | (qs) -> qs | measure(qs[1]) -> bits[1] |\n"
            "| meas2 | (qs) -> qs | measure(qs[2]) -> bits[2] |\n"
            "| corr0 | (qs) -> qs | if bits[0] == 1: X(qs[3]) |\n"
        )
        circ = str(compile_to_stim(parse_q_orca_markdown(src).file.machines[0]))
        assert "CX rec[-3] 3" in circ, circ  # b0 is 3 records back at emit time

    def test_non_clifford_machine_refused(self):
        from q_orca.compiler.stabilizer import compile_to_stim, StabilizerCompileError
        with pytest.raises(StabilizerCompileError, match="not Clifford"):
            compile_to_stim(_machine_with_effect("T(qs[0])"))

    def test_non_pauli_feedforward_refused(self):
        from q_orca.compiler.stabilizer import compile_to_stim, StabilizerCompileError
        src = (
            "# machine M\n\n## context\n| Field | Type | Default |\n|---|---|---|\n"
            "| qubits | list<qubit> | [q0, q1] |\n| bits | list<bit> | [b0] |\n\n"
            "## states\n## state |s0> [initial]\n## state |s1>\n## state |done> [final]\n\n"
            "## events\n- meas\n- corr\n\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n|---|---|---|---|---|\n"
            "| |s0> | meas | | |s1> | m0 |\n| |s1> | corr | | |done> | badcorr |\n\n"
            "## actions\n| Name | Signature | Effect |\n|---|---|---|\n"
            "| m0 | (qs) -> qs | measure(qs[0]) -> bits[0] |\n"
            "| badcorr | (qs) -> qs | if bits[0] == 1: H(qs[1]) |\n"
        )
        machine = parse_q_orca_markdown(src).file.machines[0]
        cg = next((a.conditional_gate for a in machine.actions if a.conditional_gate), None)
        if cg is None:
            pytest.skip("parser did not produce a conditional_gate for non-Pauli correction")
        with pytest.raises(StabilizerCompileError, match="Pauli"):
            compile_to_stim(machine)

    def test_multiclause_syndrome_feedforward_refused(self):
        # Real QEC syndrome decoding (e.g. bit-flip-syndrome) uses multi-clause
        # AND feedforward, which Stim's single-record rec-controls cannot express
        # in-circuit — it is a decoder concern (the deferred detector/PyMatching
        # follow-on). compile_to_stim must refuse it clearly, not miscompile it.
        from q_orca.compiler.stabilizer import compile_to_stim, StabilizerCompileError
        machine = _machine("examples/bit-flip-syndrome.q.orca.md")
        with pytest.raises(StabilizerCompileError, match="single-clause"):
            compile_to_stim(machine)


class TestStabilizerSamplingParity:
    """Sampled distributions match the expected (state-vector) distribution."""

    def setup_method(self):
        pytest.importorskip("stim")

    @pytest.mark.parametrize("name,n", [("bell-entangler", 2), ("ghz-state", 3)])
    def test_terminal_distribution(self, name, n):
        from q_orca.compiler.stabilizer import compile_to_stim, sample_stim_circuit
        circ = compile_to_stim(_machine(f"examples/{name}.q.orca.md"))
        circ.append("M", list(range(n)))  # terminal measurement of all qubits
        counts = sample_stim_circuit(circ, shots=10000, seed=20260605)
        # A cat state collapses to all-0 or all-1, ~50/50; nothing else appears.
        allowed = {"0" * n, "1" * n}
        assert set(counts) <= allowed, f"unexpected outcomes: {set(counts) - allowed}"
        for key in allowed:
            assert abs(counts.get(key, 0) / 10000 - 0.5) < 0.03  # Wilson ~±0.01

    def test_feedforward_recovers_teleported_state(self):
        # active-teleportation teleports |0>; after correct X/Z feedforward, q2
        # must be |0> on every shot. A mis-indexed X correction (wrong rec[-N])
        # would flip q2 on ~half the shots, so this gates the feedforward path.
        from q_orca.compiler.stabilizer import compile_to_stim, sample_stim_circuit
        circ = compile_to_stim(_machine("examples/active-teleportation.q.orca.md"))
        circ.append("M", [2])  # measure the teleported qubit last
        counts = sample_stim_circuit(circ, shots=10000, seed=20260605)
        # records: b0, b1, then q2 → q2 is the last char of each 3-bit outcome.
        q2_ones = sum(c for k, c in counts.items() if k[-1] == "1")
        assert q2_ones == 0, f"teleported |0> recovered as 1 on {q2_ones} shots"


class TestAerStabilizerTarget:
    """The secondary Aer-stabilizer compilation target produces the same results."""

    def setup_method(self):
        pytest.importorskip("qiskit_aer")

    def test_bell_distribution_under_aer(self):
        from qiskit import ClassicalRegister
        from qiskit_aer import AerSimulator
        from q_orca.compiler.stabilizer import compile_to_qiskit_stabilizer
        qc = compile_to_qiskit_stabilizer(_machine("examples/bell-entangler.q.orca.md"))
        creg = ClassicalRegister(2, "out")
        qc.add_register(creg)
        qc.measure([0, 1], creg)
        counts = AerSimulator(method="stabilizer").run(qc, shots=10000, seed_simulator=7).result().get_counts()
        # Multi-register key "out orig"; the `out` register is the first field.
        norm: dict[str, int] = {}
        for k, v in counts.items():
            norm[k.split(" ")[0]] = norm.get(k.split(" ")[0], 0) + v
        assert set(norm) <= {"00", "11"}, f"unexpected: {set(norm)}"
        for key in ("00", "11"):
            assert abs(norm.get(key, 0) / 10000 - 0.5) < 0.03

    def test_teleportation_feedforward_under_aer(self):
        from qiskit import ClassicalRegister
        from qiskit_aer import AerSimulator
        from q_orca.compiler.stabilizer import compile_to_qiskit_stabilizer
        qc = compile_to_qiskit_stabilizer(_machine("examples/active-teleportation.q.orca.md"))
        out = ClassicalRegister(1, "q2out")
        qc.add_register(out)
        qc.measure(2, out[0])
        counts = AerSimulator(method="stabilizer").run(qc, shots=8000, seed_simulator=7).result().get_counts()
        # q2out is the leftmost (most-significant) register in qiskit's key.
        q2_ones = sum(v for k, v in counts.items() if k.split(" ")[0] == "1")
        assert q2_ones == 0  # teleported |0> recovered exactly


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
