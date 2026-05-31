## ADDED Requirements

### Requirement: QPC convergence benchmark harness

The harness SHALL run the QPC learning machine through the iterative runtime and produce a per-iteration error trajectory recording, for each iteration, the model parameter `theta_0` in effect and the measured error metric at that parameter.

The harness reads the parameter trajectory from the public `simulate_iterative` result trace and obtains the per-iteration error by shot-batching the forward pass at each recorded `theta_0`. It accepts a configuration of `(seed, inner_shots, eta, theta_0_initial, max_iter)` and returns a structured result containing the trajectory, the classical baseline, the computed metrics, and a convergence verdict.

#### Scenario: produces a full trajectory
- **WHEN** the harness runs the converging QPC machine with `max_iter = N`
- **THEN** the result contains an error-trajectory of length `N` (one entry per learning iteration), each entry carrying the iteration index, the `theta_0` in effect, and the measured error metric

#### Scenario: trajectory is sourced from the runtime, not re-derived
- **WHEN** the harness records `theta_0` per iteration
- **THEN** the values are taken from the `simulate_iterative` result's recorded trace, so the benchmarked parameters are exactly those the runtime executed

### Requirement: Non-trivial learning signal

The benchmark task SHALL be defined so the measured error depends on the model parameter `theta_0`, so that a fixed point and convergence toward it are well-defined.

The benchmark uses a data-register encoding for which the parity-ancilla outcome probability is a non-constant function of `theta_0` (the shipped `H|0>` data encoding, which yields `P(bits[0]=1) = 0.5` independent of `theta_0`, MUST NOT be used). The fixed point `theta_0*` is the parameter at which the measured error metric is minimized and is known analytically for the chosen task.

#### Scenario: error varies with the model parameter
- **WHEN** the harness evaluates the error metric at two materially different `theta_0` values away from the fixed point
- **THEN** the two measured error values differ by more than shot noise (the signal is present)

#### Scenario: the no-signal encoding is rejected
- **WHEN** a benchmark task is configured whose error metric is constant in `theta_0` (e.g. the `|+>` data encoding)
- **THEN** the harness refuses to certify convergence and reports that the task carries no learning signal

### Requirement: Exact classical baseline comparison

The harness SHALL compute an exact classical reference trajectory on the identical scalar objective and report the gap between the quantum and classical trajectories.

The classical baseline runs the same update dynamics (same `eta`, same `theta_0_initial`, same step count) against the closed-form or statevector-exact objective `p(theta_0)`, with no shot noise. The harness reports the mean and maximum absolute difference between the quantum and classical error trajectories.

#### Scenario: quantum tracks classical within shot noise
- **WHEN** the harness runs with `inner_shots = S`
- **THEN** the maximum absolute gap between the quantum and classical error trajectories is within an `O(1/sqrt(S))` tolerance, and both trajectories are included in the result

#### Scenario: no advantage is claimed
- **WHEN** the harness emits its report
- **THEN** the report states that the classical baseline is at least as good and that the benchmark demonstrates correctness and measurability, not quantum advantage

### Requirement: Convergence verdict under a constant step size

The harness SHALL decide convergence using a band criterion rather than point-convergence, because a constant step size dithers within a bounded band around the fixed point.

Convergence is certified when the running-mean error over the final window of iterations falls below `c * eta` (default `c = 1`) AND the mean error over the first half of the run strictly exceeds the mean error over the second half (the loop demonstrably moved toward the fixed point). The verdict, the band width used, and both half-run means are included in the result. The harness MUST NOT assert strict per-iteration monotonic decrease.

#### Scenario: converging run is certified
- **WHEN** the loop starts away from the fixed point and the final-window running-mean error falls below `c * eta` with second-half mean error below first-half
- **THEN** the verdict is "converged" and the band width and half-run means are reported

#### Scenario: non-converging run is not certified
- **WHEN** the final-window running-mean error stays above the band (e.g. a no-signal task or a step size too large)
- **THEN** the verdict is "not converged" and the report identifies which condition failed

### Requirement: Reproducibility under a fixed seed

The harness SHALL produce an identical trajectory across runs for a fixed configuration including the simulator seed.

The simulator seed is threaded into the iterative runtime options so that a given `(seed, inner_shots, eta, theta_0_initial, max_iter)` yields the same measured trajectory on repeated invocation.

#### Scenario: two runs with the same seed match
- **WHEN** the harness is invoked twice with identical configuration and seed
- **THEN** the two error trajectories are equal element-for-element

### Requirement: Benchmark artifact emission

The harness SHALL emit a machine-readable results table, and SHALL emit an error-vs-iteration plot only when a plotting backend is available.

Results are written as both CSV and JSON containing the per-iteration quantum and classical error values and the summary metrics. A plot comparing the quantum and classical error-vs-iteration curves is written only if the optional plotting dependency imports successfully; otherwise the harness records that plotting was skipped and emits the data files alone.

#### Scenario: data files always emitted
- **WHEN** the harness completes a run with an output directory configured
- **THEN** `results.csv` and `results.json` are written regardless of whether a plotting backend is present

#### Scenario: plot is optional
- **WHEN** the plotting dependency is not installed
- **THEN** the harness completes successfully, skips the plot, and notes the skip in its result without raising
