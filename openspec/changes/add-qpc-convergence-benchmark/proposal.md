## Why

The Quantum Predictive Coder (QPC) machinery is fully built and end-to-end runnable — `examples/predictive-coder-learning.q.orca.md` verifies and executes on the iterative runtime — but it has never been shown to *converge*. The QPC research doc (`docs/research/spec-quantum-predictive-coder.md`, §"Next concrete steps" #6) names a single remaining concrete deliverable (everything else in that doc is open research): a convergence benchmark that sweeps the learning loop and plots error-vs-iteration against a classical baseline. Until that exists, "QPC" is *expressible and runnable* but *scientifically undemonstrated*.

Writing this benchmark also forces a correctness fix: in the shipped example the data register is prepared as `H|0> = |+>`, which makes the parity-ancilla outcome `P(bits[0]=1) = 0.5` **independent of θ** — so the learning loop currently has no signal and `theta_0` random-walks. A convergence benchmark cannot exist without a learning task whose error actually depends on the model parameter.

## What Changes

- Add an **`evaluation`** capability: a reproducible convergence-benchmark harness that drives the QPC learning loop through the iterative runtime, extracts the per-iteration error trajectory from the run trace, and reports whether and how fast it converges.
- Define a concrete, analytically-known **learning task** for the benchmark where the parity-ancilla error depends on `theta_0` (e.g. a fixed computational-basis data register), so convergence to a fixed point is well-defined and measurable.
- Compare the quantum stochastic loop against an **exact classical baseline** — gradient descent on the same scalar objective `P(bits[0]=1 | theta_0)` computed in closed form / by statevector — and report the gap (the honest result is parity within shot noise, *not* a quantum advantage).
- Add a corrected learning example (`examples/predictive-coder-converging.q.orca.md`) with a non-trivial signal, a demo runner under `demos/qpc_convergence/`, and an emitted results table (CSV/JSON) plus an optional error-vs-iteration plot.
- Add tests that run the benchmark headless (small shots/iterations, no plotting) asserting the convergence property and run-to-run reproducibility under a fixed seed.
- **Relax the verifier's scalar context-mutation typing to accept `float` (not only `int`).** Implementing the loop surfaced that a learnable bare-scalar angle could not be both referenced by a rotation gate *and* mutated by a context update: the scalar form is required for the gate-angle reference (list-index angles do not resolve in the circuit builder), but the verifier rejected scalar-`float` `+=`/`-=` — even though the runtime (`context_ops`) already performs float arithmetic. This is a one-line bug fix aligning the verifier with the runtime; it benefits any variational machine (VQE/QAOA) with a trainable bare-scalar angle, not just the QPC.
- Fix the structural loop bug shared with the original example: re-route the loop through a `|ready>` state so the model-prep ansatz re-runs each iteration (the original applied it once and then measured a stale state).

## Capabilities

### New Capabilities
- `evaluation`: benchmarking and convergence-measurement harnesses that run an existing q-orca machine through the runtime and assert quantitative behavioral properties (convergence rate, error floor, agreement with a reference baseline) over a sweep of configurations.

### Modified Capabilities
- `verifier`: classical context-update static typing — a scalar (non-indexed) `+=`/`-=` target may now be a numeric scalar (`int` **or** `float`), not `int` only. The runtime already supported float; this aligns the verifier.

## Impact

- **New code**: `q_orca/evaluation/` (harness + classical baseline + trajectory extraction); `demos/qpc_convergence/` (runner); `examples/predictive-coder-converging.q.orca.md`; tests under `tests/`.
- **Changed code**: `q_orca/verifier/classical_context.py` (one-condition relaxation: scalar mutation target may be `int` or `float`). 189 existing verifier/context tests still pass.
- **Dependencies**: NumPy (already used). Plotting (matplotlib) is an *optional* dependency — the harness degrades to data-only (CSV/JSON) when it is absent, mirroring the repo's optional-backend pattern.
- **Docs**: marks Next-Step #6 of `docs/research/spec-quantum-predictive-coder.md` as delivered.
- **No breaking changes**; the shipped `predictive-coder-learning.q.orca.md` example is left in place (a note documents its no-signal property).
