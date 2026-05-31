## 1. Learning task + corrected example

- [ ] 1.1 Add `examples/predictive-coder-converging.q.orca.md`: clone `predictive-coder-learning` but prepare the data register as `|0>` (drop the `H` in `encode_datum`) so the parity-ancilla error depends on `theta_0`; set `theta_1 = theta_2 = 0` (D1) so the objective is the clean `p(theta_0)=sin²(theta_0/2)` with fixed point `theta_0* = π/2`
- [ ] 1.2 Confirm the new example verifies (`q-orca verify`) and runs (`q-orca run`) on the iterative runtime
- [ ] 1.3 Add a header note to `examples/predictive-coder-learning.q.orca.md` documenting (for educational value) that its `|+>` data encoding yields no learning signal — `P(bits[0]=1)=½` independent of `theta_0`, so `theta_0` random-walks — and pointing to the converging variant

## 2. Evaluation harness (`q_orca/evaluation/`)

- [ ] 2.1 Create the `q_orca/evaluation/` package (`__init__.py` exporting the public harness entry point)
- [ ] 2.2 Implement task setup in `qpc.py`: load the converging machine, expose `(seed, inner_shots, eta, theta_0_initial, max_iter)` config
- [ ] 2.3 Implement trajectory extraction: run `simulate_iterative(..., record_trace=True)` and pull per-iteration `theta_0` from the result trace's `context_snapshot`
- [ ] 2.4 Implement the per-iteration error metric: shot-batch the forward pass at each recorded `theta_0` to estimate `p̂_t = P(bits[0]=1)`, error `= |p̂_t − ½|`; also record `|theta_0 − theta_0*|`
- [ ] 2.5 Implement the exact classical baseline using the analytic objective `p(theta_0)=sin²(theta_0/2)` (no simulator) and the same update dynamics with no shot noise; keep a 1-qubit statevector evaluation of `p(theta_0)` as the generic fallback hook; compute mean and max absolute gap to the quantum trajectory
- [ ] 2.6 Implement the convergence verdict (D3): final-window running-mean error below `c*eta` AND second-half mean < first-half mean; record band width and half-run means; no per-iteration monotonicity assertion
- [ ] 2.7 Implement the no-signal guard: detect a task whose error metric is constant in `theta_0` and refuse to certify convergence
- [ ] 2.8 Return a structured result (trajectory, baseline, metrics, verdict, skip flags)

## 3. Artifacts + demo runner

- [ ] 3.1 Emit `results.csv` and `results.json` (per-iteration quantum + classical error, summary metrics) to a configured output dir
- [ ] 3.2 Emit an error-vs-iteration plot ONLY if matplotlib imports; otherwise log the skip and continue (no hard dependency)
- [ ] 3.3 Add `demos/qpc_convergence/run.py` user-facing runner with sensible defaults and a printed summary (mirrors the `demos/larql_*` pattern); include the "no quantum advantage" note in the report header

## 4. Tests

- [ ] 4.1 `tests/test_qpc_convergence.py`: headless run (no plotting) asserts the verdict is "converged" on the converging example under a fixed seed, using recommended defaults (D8): `inner_shots≈1024` floor, `max_iter≈300`, `eta≈0.15` — enough to keep shot noise below the `c·eta` band
- [ ] 4.2 Reproducibility test: two seeded runs produce element-for-element equal trajectories
- [ ] 4.3 No-signal test: the `|+>` (learning) example is reported as "not converged / no signal", not certified
- [ ] 4.4 Baseline test: max quantum-vs-classical gap is within the `O(1/sqrt(shots))` tolerance for the configured shot count
- [ ] 4.5 Artifact test: `results.csv`/`results.json` are written; plotting absence does not raise

## 5. Docs

- [ ] 5.1 Mark Next-Step #6 of `docs/research/spec-quantum-predictive-coder.md` as delivered, linking the example, harness, and demo
- [ ] 5.2 Note in the demo README that the binary constant-η loop converges to an `O(eta)` band (not a point), and that the scalar-innovation Kalman update is a separate future residual
