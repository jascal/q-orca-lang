## Context

In `q_orca/runtime/composed.py::_run_invoke`, the child is dispatched two ways:
a **leaf** child (no invoke states) runs via `simulate_iterative`, which returns
a `QIterativeSimulationResult` carrying `aggregate_counts` (per-shot measured-bit
distribution); a **composed** child (has invoke states) runs via `run_composed`,
which returns a `ComposedRunResult` that does **not** carry `aggregate_counts`.
The aggregation code therefore sets `aggregate_counts = {}` for composed children
and `_compute_returns` produces empty `prob_`/`hist_`/`var_`. The fix is to make
the composed result carry the same distribution.

## Goals / Non-Goals

**Goals:**

- A composed (non-leaf) quantum child invoked with `shots=N>1` yields the same
  `prob_`/`hist_`/`var_` aggregates a leaf child would.
- One aggregation path: `_compute_returns` should not care whether the child was
  a leaf or composed.
- Shot count propagates into the composed child's run.

**Non-Goals:**

- Joint / cross-bit statistics (still per-bit; new statistic kinds are a separate
  vocabulary change).
- Aggregating across *multiple distinct* measurement segments into one labelled
  distribution beyond the existing accumulation behaviour (the same limitation
  leaf children have today).

## Decisions

### Decision 1: `ComposedRunResult.aggregate_counts`

Add `aggregate_counts: dict[str, int]` to `ComposedRunResult`. `run_composed`
populates it by merging the measured-bit counts produced along the run: from the
parent's own gate segments (when `extend-composed-gate-parents` is present) and
from each invoked child's result. Merging is by summing counts per full-bitstring
key — symmetric with how `simulate_iterative` accumulates across segments.

**Alternative considered:** return only the last child's counts. Rejected — a
composed child may delegate the measurement to a grandchild, and the
distribution that matters is whatever measured bits the child ultimately
produced; merging is the consistent rule.

### Decision 2: `_run_invoke` reads counts uniformly

`_run_invoke` obtains `aggregate_counts` from `getattr(child_result,
"aggregate_counts", {})` for *both* leaf and composed children (the leaf path
already exposes it; the composed path now does too). `_compute_returns` is
unchanged — it just receives a populated dict.

### Decision 3: Thread shots into the composed child

When a child is shot-batched (`shots=N>1`), the composed child's options carry
`inner_shots=N` (as they already do for leaf children), so the grandchild's
measurement segments are sampled at N shots and the counts reflect N draws.

## Risks / Trade-offs

- **[Risk] Count provenance is ambiguous when a composed child measures in more
  than one place.** → Mitigation: the merge sums per-bitstring keys, matching the
  leaf-child accumulation; per-bit marginals (`_per_bit_stats`) remain
  well-defined. Documented as the same limitation leaf children have.
- **[Trade-off] A composed child's intermediate (grandchild) measurements all
  fold into one distribution.** Acceptable for v1; a future change could label
  distributions per measurement site if a real workflow needs it.

## Open Questions

1. **Interaction with `extend-composed-gate-parents`.** If both land, a composed
   child contributes counts from *both* its own gate segments and its
   grandchildren. The merge handles this, but the two changes should land with a
   combined regression test (parent → composed child with its own gates → leaf
   grandchild) to pin the end-to-end distribution.
