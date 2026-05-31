"""Evaluation harnesses — benchmark an existing q-orca machine through the
runtime and assert quantitative behavioral properties.

Currently houses the QPC convergence benchmark (`add-qpc-convergence-benchmark`):
runs the quantum predictive coder's learning loop, measures the per-iteration
error trajectory, compares it against an exact classical baseline, and certifies
convergence.
"""

from q_orca.evaluation.qpc import (
    QpcBenchmarkConfig,
    QpcBenchmarkResult,
    p_exact,
    run_benchmark,
    write_artifacts,
)

__all__ = [
    "QpcBenchmarkConfig",
    "QpcBenchmarkResult",
    "p_exact",
    "run_benchmark",
    "write_artifacts",
]
