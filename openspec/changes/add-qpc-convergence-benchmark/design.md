## Context

The QPC learning loop (`examples/predictive-coder-learning.q.orca.md`) is a 3-qubit hybrid machine: a model qubit `q0` prepared by `Ry(θ0)·Rz(θ1)·Rx(θ2)|0>`, a data qubit `q1`, and an error ancilla `q2`. Two parity CNOTs map `q0 ⊕ q1` onto `q2`; `q2` is measured into `bits[0]`; a classical `gradient_step` nudges `θ0` by ±`eta` on the measured bit; the loop repeats until `iteration >= max_iter`. The iterative runtime (`q_orca/runtime/iterative.py::simulate_iterative`) already executes this end to end and, with `record_trace=True`, returns a `QIterationTrace` per context-update carrying `measurement_bits` and a `context_snapshot` (so the full `θ0` trajectory is recoverable).

What does not yet exist is any *measurement of convergence*: no harness, no classical reference, no plot, no test that the error actually falls.

### The learning-signal problem (must be fixed first)

In the shipped example `q1` is prepared `H|0> = |+>`. The state before the parity CNOTs factorizes as `(a|0>+b|1>)_q0 ⊗ (|0>+|1>)/√2_q1 ⊗ |0>_q2`, so the Z-basis parity is
`P(bits[0]=1) = P(q0=0)·P(q1=1) + P(q0=1)·P(q1=0) = ½(|a|²+|b|²) = ½`,
**independent of θ0**. The error bit is a fair coin regardless of the model, the expected `gradient_step` drift is zero, and `θ0` performs an unbiased random walk. There is nothing to converge to. Any convergence benchmark must therefore define a task whose error depends on `θ0`.

## Goals / Non-Goals

**Goals:**
- A reproducible harness that runs the QPC loop and produces a per-iteration error trajectory.
- A learning task with a non-trivial, analytically-known fixed point so "did it converge?" is a decidable question.
- An exact classical baseline trajectory on the identical scalar objective, with a reported gap.
- A headless test asserting convergence + reproducibility; emitted CSV/JSON results and an optional plot.

**Non-Goals:**
- **No quantum-advantage claim.** For this single-parameter toy the classical baseline is at least as good; the benchmark demonstrates the loop is *correct and measurable*, not superior. The proposal and the emitted report say so explicitly.
- **Not the scalar-innovation (Kalman) update.** The research doc's principled `(bits[0] − expected)` update is a *separate* residual; this change benchmarks the shipped binary `θ0 ± eta` loop. The harness is written so a future scalar-innovation loop can be benchmarked unchanged.
- **No new language/compiler/verifier surface.** Pure runtime consumer.

## Decisions

### D1 — Learning task: fixed computational-basis data register
Prepare `q1 = |0>` (drop the `H`) for the benchmark example. Then `P(bits[0]=1) = P(q0=1) = |b(θ0)|²`. With the model `Ry(θ0)·Rz(θ1)·Rx(θ2)|0>`, the Z-basis excitation `|b|²` is a smooth function of the angles; for the benchmark we fix `θ1,θ2` at their defaults so the objective is the 1-D curve `p(θ0) = P(q0=1)`. The binary update `θ0 -= eta` on bit=1 / `+= eta` on bit=0 has zero drift exactly where `p(θ0*) = ½`, so the fixed point `θ0*` is the angle that makes the model qubit a fair coin. This is analytically known, giving a ground-truth target.
*Alternative considered:* a parameterized data register `Ry(q1, φ)` with a target `φ` — richer (model chases data) but introduces a second free parameter and a 2-D objective; deferred to keep the first benchmark legible.

### D2 — Convergence metric
Primary metric: `err(t) = |p̂_t − ½|`, where `p̂_t` is the measured `P(bits[0]=1)` at the θ0 in effect at iteration `t`. Secondary metric: `|θ0(t) − θ0*|`. `p̂_t` is obtained by shot-batching the forward pass at each recorded θ0 (the iterative runtime already supports `inner_shots`). Report both the raw trajectory and a running mean.

### D3 — Convergence criterion under constant η (honest about dithering)
A constant-η binary stochastic-approximation update does **not** converge to a point — it enters and then dithers within an `O(eta)` band around `θ0*`. The criterion is therefore: the running-mean error over the last `k` iterations falls below `c·eta` (with `c≈1`, default `k=⌈max_iter/3⌉`), and the *first-half* mean error strictly exceeds the *second-half* mean error (the loop demonstrably moved toward the fixed point). For asymptotic point-convergence the harness ALSO supports an optional decreasing schedule `eta_t = eta_0 / (1 + t)` (Robbins–Monro); whether the runtime can express per-iteration η is checked in Open Questions — if not, the schedule is applied by the harness re-invoking the loop in unit steps.

### D4 — Exact classical baseline
Compute `p(θ0)` in closed form (or by a 1-qubit statevector) and run deterministic gradient descent / exact binary-drift dynamics on it with the same `eta`, `θ0(0)`, and step count. The honest comparison: the noisy quantum trajectory tracks the exact classical trajectory within `±O(1/√shots)`. Report the max and mean absolute gap.

### D5 — Reproducibility
Thread a fixed simulator seed (`QIterativeSimulationOptions.seed_simulator`) so a given `(seed, shots, eta, θ0(0), max_iter)` yields a byte-identical trajectory. The test pins this.

### D6 — Artifacts and optional plotting
The harness returns a structured result (trajectory, baseline, metrics, verdict) and writes `results.csv` + `results.json`. A plot (`error-vs-iteration`, quantum vs classical) is emitted **only if matplotlib imports**; otherwise the harness logs that plotting was skipped and emits data only. No hard dependency on matplotlib.

### D7 — Code placement
New package `q_orca/evaluation/` with `qpc.py` (task setup, harness, classical baseline, metrics) and a thin `__init__`. A user-facing runner lives at `demos/qpc_convergence/run.py` (mirrors the existing `demos/larql_*` pattern). The corrected machine is `examples/predictive-coder-converging.q.orca.md`. Tests in `tests/test_qpc_convergence.py`.

## Risks / Trade-offs

- **Constant-η never truly converges** → D3 specifies a band criterion + monotone-improvement check, and offers the Robbins–Monro schedule for true convergence; the report states which was used.
- **Shot noise can violate a strict monotonic-decrease assertion** → assert on running-mean / windowed error and on first-half-vs-second-half, never per-iteration monotonicity; use enough shots in the test (seeded) to keep noise below the band.
- **Reader over-interprets as quantum advantage** → explicit non-goal in proposal, design, and the emitted report header; the classical baseline is shown alongside and is at least as good.
- **Coupling to runtime trace internals** (`QIterationTrace.context_snapshot`) → access via the public `simulate_iterative` result only; if the field set changes the harness breaks loudly in its own test, not silently.
- **The benchmark "fixes" the example by changing the data encoding** → ship it as a *new* example (`-converging`) and leave `predictive-coder-learning` untouched with a documented note, so no existing test or doc reference breaks.

## Migration Plan

Additive only. New package, new example, new demo, new tests. Nothing to roll back beyond deleting the added files; no public API changes.

## Open Questions

1. **Per-iteration η:** can `QIterativeSimulationOptions` / the context-update grammar express a decreasing `eta_t` within a single `simulate_iterative` run, or must the harness drive unit steps externally to realize Robbins–Monro? (Affects D3; default to external driving if unsupported.)
2. **Default angles `θ1,θ2`:** fix at the example defaults (0.3, 0.7) or set both to 0 so `p(θ0)=sin²(θ0/2)` is the cleanest textbook curve? (Leaning: 0 for legibility; document the choice.)
3. **Autoencoder baseline (2202.01230):** the research doc also mentions comparing against the autoencoder compression baseline on sequential data. That is a much larger, separate effort — explicitly deferred; this change ships only the classical-gradient-descent baseline.
