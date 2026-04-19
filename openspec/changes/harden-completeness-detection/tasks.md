## 1. Code change

- [x] 1.1 Add a helper in `q_orca/verifier/completeness.py` that,
  given a `QMachineDef` and an `QEvent`, returns True iff some
  transition on that event has an action in `machine.actions` with a
  non-None `measurement` or `mid_circuit_measure` field.
- [x] 1.2 Rewrite `has_quantum_preparation_path` so the
  measurement-event check is the union of the existing
  name-substring match and the new action-effect helper from 1.1.
- [x] 1.3 Keep the >50% single-outgoing threshold logic unchanged.

## 2. Regression tests

- [x] 2.1 Add a unit test that a machine with event `read_error` and
  a `mid_circuit_measure` action (e.g.,
  `measure(qs[2]) -> bits[0]`) is classified as a preparation path
  by `has_quantum_preparation_path`.
- [x] 2.2 Add a unit test that a machine with both a measurement
  name match (e.g., `measure_alice_x`) AND a measurement-bearing
  action is still classified as a preparation path (no regression).
- [x] 2.3 Add a unit test that a machine with no measurement-name
  events and no measurement actions is NOT classified as a
  preparation path (negative case unchanged).
- [x] 2.4 Add an end-to-end verifier test that
  `examples/predictive-coder-minimal.q.orca.md` verifies clean
  under its current event name AND would still verify clean if the
  event were renamed from `measure_error` back to `read_error`
  (inline fixture, not a real file edit).

## 3. Spec + docs sync

- [x] 3.1 Confirm the delta spec at
  `openspec/changes/harden-completeness-detection/specs/verifier/spec.md`
  covers both detection paths and both scenarios.
- [x] 3.2 Run `openspec validate harden-completeness-detection --strict`
  and address any errors.

## 4. Verification

- [x] 4.1 Run `.venv/bin/python -m pytest tests/test_verifier.py -q`
  and confirm all tests pass.
- [x] 4.2 Run the full suite
  `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_cuquantum_backend.py --ignore=tests/test_cudaq_backend.py`
  to confirm no regressions elsewhere.
- [x] 4.3 Run `.venv/bin/q-orca verify examples/vqe-rotation.q.orca.md`
  and confirm the actionless-`collapse` machine still verifies clean
  (name-based fallback not regressed).
