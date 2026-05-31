# QPC convergence benchmark

Demonstrates that the quantum predictive coder's learning loop actually
**converges** — the single remaining concrete deliverable from
`docs/research/spec-quantum-predictive-coder.md` (Next-Step #6), shipped as
OpenSpec change `add-qpc-convergence-benchmark`.

## Run it

```bash
python demos/qpc_convergence/run.py            # defaults: max_iter=80, eta=0.15, seed=7
python demos/qpc_convergence/run.py --max-iter 120 --eta 0.1 --seed 7
```

Writes `out/results.csv`, `out/results.json`, and (if matplotlib is installed)
`out/convergence.png`.

## What it shows

The benchmark machine (`examples/predictive-coder-converging.q.orca.md`) prepares
a model qubit with `Ry(theta_0)`, holds the data qubit in `|0>`, and measures the
parity ancilla, so the forward measurement is

```
p(theta_0) = P(bits[0]=1) = sin^2(theta_0 / 2)
```

The binary update `theta_0 -= eta` (measured 1) / `+= eta` (measured 0) has zero
expected drift exactly where `p = 1/2`, i.e. at **`theta_0* = pi/2`** — the angle
that makes the model qubit a fair coin. The harness:

1. runs the loop on the real iterative runtime (the measured ancilla bit drives
   each update) to get the `theta_0` trajectory;
2. re-measures the forward pass at each `theta_0` to get the error
   `|P(1) - 1/2|`;
3. compares against the **exact classical baseline** (gradient descent on the
   analytic `p(theta_0)`), reporting the shot-noise gap;
4. certifies convergence with a **band criterion**: the running-mean error
   enters an `O(eta)` band and the second half improves on the first.

## Honest caveats

- **No quantum advantage.** For this single-parameter toy the classical baseline
  is at least as good; it is shown alongside precisely so the comparison is
  honest. The point is that the loop is *correct and measurable*.
- **Band, not point.** A constant step `eta` dithers within an `O(eta)` band
  around `theta_0*` rather than converging to a point. A decreasing
  (Robbins–Monro) schedule for true point-convergence, and a principled
  scalar-innovation (Kalman) update, are noted follow-ups — not in this change.
- **No-signal guard.** Point the harness at the old `predictive-coder-learning`
  example (data `|+>`) and it refuses to certify: the forward error is constant
  in `theta_0`, so there is nothing to learn.
