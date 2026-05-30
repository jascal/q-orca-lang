## Context

`run_composed` (in `q_orca/runtime/composed.py`) walks an invoke-bearing parent
with `_walk_composed`. For non-invoke states it handles plain transitions and
`context_update` actions, but any `gate` / `mid_circuit_measure` / `measurement`
/ `conditional_gate` action raises `QIterativeRuntimeError("…not yet
supported")`. The single-machine `simulate_iterative` already knows how to do
this correctly: it accumulates gate-bearing transitions into a `segment` and
`_flush_segment` builds + runs the circuit, updating `bits` and
`aggregate_counts`. v1 simply did not wire that into the composed walk.

## Goals / Non-Goals

**Goals:**

- An invoke-bearing parent may interleave its own gate/measurement transitions
  with invoke states, and they execute correctly.
- Reuse `iterative._flush_segment` and the `_PendingTransition` buffer — do not
  re-implement circuit building.
- Preserve the boundary semantics: parent and child quantum registers are
  independent; only classical returns cross. An invoke flushes any pending
  parent segment first so its measured bits are visible to the invoke bindings
  and to downstream guards.

**Non-Goals:**

- A *shared* quantum register between parent and child (passing live qubits into
  a child). Composition remains classical-at-the-boundary by design.
- Nested shot-batched aggregation through composed children — that is the
  sibling change `extend-nested-shot-aggregation`.

## Decisions

### Decision 1: Adopt the iterative runtime's segment model in the composed walk

`_walk_composed` gains a `segment: list[_PendingTransition]` buffer and a
`guard_map`-aware flush, mirroring `simulate_iterative`. A gate/measurement
transition appends to the segment instead of erroring. The segment flushes (via
`_flush_segment`, updating `bits`/`aggregate_counts`) on three boundaries:
(a) before applying a `context_update` (so branch selection sees the bits),
(b) before executing an invoke (so the invoke's arg/return bindings and the
next guards see the bits), and (c) on reaching a final state.

**Alternative considered:** delegate whole gate-only sub-walks to
`simulate_iterative`. Rejected — the parent walk needs a single coherent
`bits`/context thread across invoke boundaries, which a sub-call would fragment.

### Decision 2: Invoke does not touch the parent's quantum state

When the walk reaches an invoke state it first flushes the pending parent
segment, then dispatches the child exactly as today (the child runs on its own
register), binds the child's classical returns into the parent context, and
resumes. The parent's post-flush `bits` and quantum state are unchanged by the
invoke. This keeps the boundary classical and matches the verifier's typing
contract (returns are typed classical values, not qubits).

### Decision 3: Keep the depth ceiling and the no-invoke fast path

The no-invoke fast path (delegating straight to `simulate_iterative`) is
unchanged. The depth ceiling still bounds recursion. Only the invoke-bearing
walk gains segment handling.

## Risks / Trade-offs

- **[Risk] Ordering bugs around the invoke flush.** A parent segment that should
  flush *before* an invoke (so bits feed the bindings) vs. *after*. →
  Mitigation: always flush the pending segment as the first step of invoke
  handling; a regression test pins that a parent measurement preceding an invoke
  is observable to a guard after the invoke.
- **[Trade-off] Parent and child registers stay independent.** A user wanting a
  child to operate on the parent's live qubits cannot express it; they must
  return classical values. This is intentional (composition is classical at the
  boundary) and documented.

## Open Questions

1. **Conditional-gate (feedforward) actions on the parent.** v1 lumps
   `conditional_gate` into the rejected set; this change includes it in segment
   handling. Confirm the iterative runtime's `_flush_segment` already supports
   conditional gates (it routes through the qiskit circuit builder, which does)
   — pin with a test.
