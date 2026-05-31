#!/usr/bin/env python3
"""QPC convergence benchmark — runnable demo.

Runs the quantum predictive coder's learning loop
(`examples/predictive-coder-converging.q.orca.md`) through the iterative runtime,
measures the per-iteration error trajectory, compares it against an exact
classical baseline, certifies convergence, and writes a results table (+ a plot
if matplotlib is available).

    python demos/qpc_convergence/run.py [--max-iter N] [--eta E] [--seed S] [--out DIR]

NOTE: this is a correctness/measurability demonstration, NOT a quantum advantage.
For this single-parameter toy the exact classical baseline is at least as good;
it is shown alongside precisely so the comparison is honest.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from q_orca.evaluation.qpc import QpcBenchmarkConfig, run_benchmark, write_artifacts


def main() -> int:
    p = argparse.ArgumentParser(description="QPC convergence benchmark")
    p.add_argument("--max-iter", type=int, default=80)
    p.add_argument("--eta", type=float, default=0.15)
    p.add_argument("--theta0", type=float, default=0.5)
    p.add_argument("--metric-shots", type=int, default=2048)
    p.add_argument("--loop-shots", type=int, default=256)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", type=str, default=str(Path(__file__).resolve().parent / "out"))
    args = p.parse_args()

    cfg = QpcBenchmarkConfig(
        theta_0_init=args.theta0, eta=args.eta, max_iter=args.max_iter,
        metric_shots=args.metric_shots, loop_shots=args.loop_shots, seed=args.seed,
    )
    result = run_benchmark(cfg)
    written = write_artifacts(result, args.out)

    bar = "─" * 72
    print(bar)
    print("QPC convergence benchmark — quantum vs exact classical baseline")
    print("  (correctness + measurability demonstration; NO quantum advantage claimed)")
    print(bar)
    print(f"  example      : {Path(cfg.example_path).name}")
    print(f"  config       : theta0={cfg.theta_0_init}  eta={cfg.eta}  max_iter={cfg.max_iter}"
          f"  loop_shots={cfg.loop_shots}  metric_shots={cfg.metric_shots}  seed={cfg.seed}")
    print(f"  learning sig : {'present' if result.has_signal else 'ABSENT'} "
          f"(p(0.3)={result.signal_lo:.3f}, p(2.8)={result.signal_hi:.3f})")
    print()
    print(f"  theta*        = {result.theta_star:.4f}   (target P(1) = {0.5})")
    print(f"  final theta   = {result.final_theta:.4f}")
    print(f"  error band    = {result.band_width:.3f}   (= eta)")
    print(f"  mean error    : first half {result.first_half_mean:.3f} -> "
          f"second half {result.second_half_mean:.3f}  (final window {result.final_window_mean:.3f})")
    print(f"  shot-noise gap: max {result.max_gap:.4f}  mean {result.mean_gap:.4f}  "
          f"(measured forward vs exact objective)")
    print()
    print(f"  VERDICT: {'CONVERGED' if result.converged else 'NOT CONVERGED'}")
    print(f"           {result.verdict_reason}")
    print()
    print("  artifacts:")
    for kind, path in written.items():
        print(f"    {kind:5} -> {path}")
    if not result.plot_written:
        print(f"    plot  -> skipped ({result.plot_skipped_reason})")
    print(bar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
