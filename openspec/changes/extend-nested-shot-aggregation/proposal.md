## Why

`add-composed-runtime` computes shot-batched aggregates (`prob_`/`hist_`/`var_`)
only for **leaf** children — those with no invoke states of their own, which run
through `simulate_iterative` and expose `aggregate_counts`. When a child is
itself composed (it invokes grandchildren), `run_composed` recurses but discards
the measurement distribution (`aggregate_counts = {}`), so a parent that
shot-batches a *composed* quantum child gets empty aggregates. This blocks
multi-layer quantum workflows (e.g. a forward-pass child that itself delegates a
sub-circuit) from reporting statistics upward.

## What Changes

- **Runtime**: thread a measurement distribution through `ComposedRunResult` so a
  composed (non-leaf) child surfaces its per-shot measured-bit counts the same
  way a leaf child does. `run_composed` SHALL accumulate `aggregate_counts`
  across its own gate segments and its children's runs, and expose them on the
  result.
- `_run_invoke` SHALL read the child's `aggregate_counts` from the
  `ComposedRunResult` (for composed children) just as it reads them from the
  `QIterativeSimulationResult` (for leaf children), so the `prob_`/`hist_`/`var_`
  synthesis is identical regardless of whether the child is a leaf or composed.
- Shot batching SHALL propagate into the composed child's run so its
  measurement segments are sampled at the requested shot count.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime`: the `Composed Machine Execution` requirement gains a measured-bit
  distribution on `ComposedRunResult`; the `Shot-Batched Quantum Child
  Aggregation` requirement is broadened so aggregates are computed identically
  for leaf and composed children.

## Impact

- **Code**: `q_orca/runtime/types.py` — add `aggregate_counts: dict` to
  `ComposedRunResult`. `q_orca/runtime/composed.py` — accumulate
  `aggregate_counts` through `_walk_composed` (merging child + segment counts)
  and use the result's counts in `_run_invoke` for composed children;
  thread `inner_shots` into the composed child's options. ~50 LOC.
- **Tests**: a parent shot-batches a composed child (child invokes a leaf
  grandchild that measures); assert the parent receives non-empty
  `prob_`/`hist_` aggregates. New cases in `tests/test_composed_runtime.py`.
- **Dependencies**: none new.
- **Sequenced after** `add-composed-runtime` (merged). Composes with
  `extend-composed-gate-parents` (a composed child that has its own gate
  segments contributes to its distribution once both land) but does not require
  it — a composed child that only delegates to a measuring grandchild already
  benefits.
