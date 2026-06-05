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


class TestDecoderUnavailable:
    def test_missing_pymatching_raises_structured_error(self, monkeypatch):
        import q_orca.evaluation.qec as qec
        monkeypatch.setattr(qec, "PYMATCHING_AVAILABLE", False)
        with pytest.raises(qec.DecoderUnavailableError, match="q-orca\\[stabilizer\\]"):
            qec.decode_logical_error_rate(object(), shots=10)
