"""Tests for the QPC convergence benchmark (`add-qpc-convergence-benchmark`).

Covers the `evaluation` capability requirements: convergence under a fixed seed,
the non-trivial-signal guard, run-to-run reproducibility, the exact classical
baseline gap (shot-noise bounded), and artifact emission (data always, plot
optional).
"""

import math
import sys

import pytest

from q_orca.evaluation.qpc import (
    QpcBenchmarkConfig,
    p_exact,
    run_benchmark,
    write_artifacts,
)

# Modest sizes keep the suite fast while staying above the noise band.
_FAST = dict(max_iter=30, metric_shots=2048, loop_shots=256, seed=7)


def test_converges_under_seed():
    r = run_benchmark(QpcBenchmarkConfig(**_FAST))
    assert r.has_signal
    assert r.converged, r.verdict_reason
    # final theta lands within a couple of eta-steps of pi/2
    assert abs(r.final_theta - math.pi / 2) <= 3 * r.config["eta"]
    # error demonstrably decreased
    assert r.second_half_mean < r.first_half_mean
    assert r.final_window_mean < r.band_width


def test_reproducible_under_fixed_seed():
    cfg = QpcBenchmarkConfig(**_FAST)
    a = run_benchmark(cfg)
    b = run_benchmark(cfg)
    assert a.thetas == b.thetas
    assert a.quantum_prob == b.quantum_prob
    assert a.quantum_error == b.quantum_error


def test_no_signal_example_is_rejected():
    # The shipped learning example uses a |+> data register -> P(1)=1/2 for all
    # theta_0 (no learning signal). The harness must refuse to certify it.
    cfg = QpcBenchmarkConfig(
        max_iter=15, metric_shots=2048, loop_shots=256, seed=7,
        example_path="examples/predictive-coder-learning.q.orca.md",
    )
    r = run_benchmark(cfg)
    assert r.has_signal is False
    assert r.converged is False
    assert "no learning signal" in r.verdict_reason


def test_baseline_gap_within_shot_noise():
    cfg = QpcBenchmarkConfig(**_FAST)
    r = run_benchmark(cfg)
    # measured forward prob vs the exact objective at the same theta: pure shot
    # noise, so the max gap should sit within a few sigma of 1/sqrt(shots).
    sigma = 1.0 / math.sqrt(cfg.metric_shots)
    assert r.max_gap < 5 * sigma
    assert r.mean_gap < 2 * sigma


def test_forward_measurement_matches_analytic():
    # Cross-validate the real circuit forward measurement against the analytic
    # objective p(theta)=sin^2(theta/2) the classical baseline uses.
    from q_orca.evaluation.qpc import _forward_actions, _forward_prob_measured, _load_machine
    m = _load_machine(QpcBenchmarkConfig().example_path)
    fwd = _forward_actions(m)
    for theta in (0.3, 1.5708, 2.5):
        measured = _forward_prob_measured(m, fwd, "theta_0", theta, shots=4000, seed=7)
        assert abs(measured - p_exact(theta)) < 0.05


def test_artifacts_data_always_emitted(tmp_path):
    r = run_benchmark(QpcBenchmarkConfig(**_FAST))
    written = write_artifacts(r, tmp_path)
    assert (tmp_path / "results.csv").exists()
    assert (tmp_path / "results.json").exists()
    assert "csv" in written and "json" in written


def test_plot_is_optional(tmp_path, monkeypatch):
    # Simulate matplotlib being unavailable: write_artifacts must still emit the
    # data files, skip the plot, and not raise.
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    r = run_benchmark(QpcBenchmarkConfig(**_FAST))
    written = write_artifacts(r, tmp_path)
    assert (tmp_path / "results.csv").exists()
    assert (tmp_path / "results.json").exists()
    assert r.plot_written is False
    assert r.plot_skipped_reason is not None
    assert "plot" not in written
