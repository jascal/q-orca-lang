"""Tests for the QEC decoder + logical-error-rate benchmark.

The decoder (`decode_logical_error_rate`) is engine-agnostic — it works on any
detector-annotated `stim.Circuit` — so it is validated here against Stim's own
generated repetition-code circuits, independently of the q-orca→Stim translation
(`compile_to_stim_with_detectors`, which is tested separately). This pins the
correctness of the DEM → PyMatching → logical-error-rate pipeline and the trend
behaviour (logical error rate falls with distance, rises with physical noise).
"""

import pytest


def _rep_code(distance: int, p: float, rounds: int = 1):
    import stim
    return stim.Circuit.generated(
        "repetition_code:memory",
        rounds=rounds,
        distance=distance,
        before_round_data_depolarization=p,
    )


class TestDecoderMachinery:
    def setup_method(self):
        pytest.importorskip("stim")
        pytest.importorskip("pymatching")

    def test_reproducible_under_fixed_seed(self):
        from q_orca.evaluation.qec import decode_logical_error_rate
        c = _rep_code(distance=5, p=0.05)
        r1 = decode_logical_error_rate(c, shots=4000, seed=20260605)
        r2 = decode_logical_error_rate(c, shots=4000, seed=20260605)
        assert r1 == r2

    def test_logical_error_rate_falls_with_distance(self):
        # At a fixed sub-threshold physical error rate, a larger code corrects more.
        from q_orca.evaluation.qec import decode_logical_error_rate
        p = 0.05
        ler_d3 = decode_logical_error_rate(_rep_code(3, p), shots=20000, seed=1)
        ler_d7 = decode_logical_error_rate(_rep_code(7, p), shots=20000, seed=1)
        assert ler_d7 < ler_d3, f"expected d7 ({ler_d7}) < d3 ({ler_d3})"

    def test_logical_error_rate_rises_with_noise(self):
        from q_orca.evaluation.qec import decode_logical_error_rate
        d = 5
        ler_lo = decode_logical_error_rate(_rep_code(d, 0.02), shots=20000, seed=2)
        ler_hi = decode_logical_error_rate(_rep_code(d, 0.10), shots=20000, seed=2)
        assert ler_hi > ler_lo, f"expected hi-noise ({ler_hi}) > lo-noise ({ler_lo})"


def _machine(path: str):
    from q_orca.parser.markdown_parser import parse_q_orca_markdown
    return parse_q_orca_markdown(open(path).read()).file.machines[0]


class TestCompileToStimWithDetectors:
    def setup_method(self):
        pytest.importorskip("stim")

    def test_emission_structure(self):
        from q_orca.compiler.stabilizer import compile_to_stim_with_detectors
        circ = str(compile_to_stim_with_detectors(_machine("examples/bit-flip-code.q.orca.md")))
        # noise on the data qubits
        assert "X_ERROR(0.05) 0 1 2" in circ
        # a per-ancilla round detector
        assert "DETECTOR rec[-1]" in circ
        # final detectors linking each stabilizer to its data support (a0=q0,q1; a1=q1,q2)
        assert "DETECTOR rec[-5] rec[-3] rec[-2]" in circ
        assert "DETECTOR rec[-4] rec[-2] rec[-1]" in circ
        # logical observable over one data qubit (Z_L)
        assert "OBSERVABLE_INCLUDE(0) rec[-3]" in circ

    def test_untagged_machine_refused(self):
        from q_orca.compiler.stabilizer import compile_to_stim_with_detectors, StabilizerCompileError
        # bell-entangler has no ancilla/syndrome roles
        with pytest.raises(StabilizerCompileError, match="ancilla/syndrome"):
            compile_to_stim_with_detectors(_machine("examples/bell-entangler.q.orca.md"))


class TestBitFlipCodeDecodes:
    def setup_method(self):
        pytest.importorskip("stim")
        pytest.importorskip("pymatching")

    def test_decoding_beats_raw_error_rate(self):
        # Distance-3 repetition code at p=0.05: a single data error is corrected,
        # so the logical error rate ~ 3p^2 ≈ 0.0075, far below the raw 0.05.
        from q_orca.evaluation.qec import logical_error_rate
        ler = logical_error_rate(_machine("examples/bit-flip-code.q.orca.md"), shots=20000, seed=7)
        assert ler < 0.02, f"logical error rate {ler} should be well below raw p=0.05"


class TestDecoderUnavailable:
    def test_missing_pymatching_raises_structured_error(self, monkeypatch):
        import q_orca.evaluation.qec as qec
        monkeypatch.setattr(qec, "PYMATCHING_AVAILABLE", False)
        with pytest.raises(qec.DecoderUnavailableError, match="q-orca\\[stabilizer\\]"):
            qec.decode_logical_error_rate(object(), shots=10)
