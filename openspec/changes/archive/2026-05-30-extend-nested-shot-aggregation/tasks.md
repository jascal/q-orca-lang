## 1. Result type

- [x] 1.1 Add `aggregate_counts: dict = field(default_factory=dict)` to
  `ComposedRunResult` in `q_orca/runtime/types.py`.

## 2. Runtime — accumulate + surface counts

- [x] 2.1 In `q_orca/runtime/composed.py::_walk_composed`, accumulate
  `aggregate_counts` across the run: merge (sum per full-bitstring key) the
  counts from each invoked child's result and from any parent gate segments.
- [x] 2.2 Populate `ComposedRunResult.aggregate_counts` on return (and on the
  no-invoke fast path, from the `simulate_iterative` result).
- [x] 2.3 In `_run_invoke`, read `aggregate_counts` uniformly via
  `getattr(child_result, "aggregate_counts", {})` for both leaf and composed
  children, so `_compute_returns` is unchanged.
- [x] 2.4 Ensure `inner_shots=N` is threaded into the composed child's options
  (so a shot-batched composed child samples its measurements N times).

## 3. Tests

- [x] 3.1 Parent shot-batches a composed child (child invokes a leaf grandchild
  that measures `bits[0]`); assert the parent receives non-empty
  `prob_bits_0` / `hist_bits_0` summing to N.
- [x] 3.2 Regression: the existing leaf-child aggregate path is unchanged.

## 4. End-to-end + docs

- [x] 4.1 Full suite green + examples `verify --strict`; ruff clean.
- [x] 4.2 If `extend-composed-gate-parents` has landed, add the combined
  regression (parent → composed child with its own gates → leaf grandchild).

## 5. Spec sync

- [ ] 5.1 At archive time, sync the `runtime` delta into
  `openspec/specs/runtime/spec.md`.
