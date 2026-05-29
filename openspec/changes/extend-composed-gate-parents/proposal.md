## Why

`add-composed-runtime` v1 deliberately scoped `run_composed` to the
*classical-orchestrator-parent* shape: a parent whose own transitions are plain
or context-update only, delegating all quantum work to children. A
gate/measurement-bearing action **on an invoke-bearing parent** raises a
structured "not yet supported" error. That leaves out a natural pattern — a
parent that prepares some of its own quantum state, invokes a child, and then
continues with more of its own gates — which several roadmap circuits (a
protocol machine that entangles locally then delegates a sub-protocol) want.
This change lifts that restriction.

## What Changes

- **Runtime**: extend `run_composed`'s parent walk to handle gate- and
  measurement-bearing transitions on an invoke-bearing parent, instead of
  erroring. The walk accumulates the parent's own gate-bearing transitions into
  circuit segments (reusing the iterative runtime's segment-flush machinery) and
  flushes them around invoke boundaries, so the parent's quantum register and
  measured bits evolve correctly across an invoke.
- The parent's quantum state and a child's are **independent** (the child has
  its own register/context); only the child's declared returns cross the
  boundary as classical values. An invoke therefore does not perturb the
  parent's accumulated quantum state — it flushes any pending parent segment
  first (so post-measurement bits are observable to the invoke's bindings and to
  guards), runs the child, binds returns, and resumes.
- Remove the `gate/measurement action on an invoke-bearing machine is not yet
  supported` runtime error; replace it with correct segment handling.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime`: the `Composed Machine Execution` requirement is broadened — an
  invoke-bearing parent MAY carry its own gate/measurement transitions, which
  the runtime executes as circuit segments flushed around invoke boundaries
  (rather than rejecting them).

## Impact

- **Code**: `q_orca/runtime/composed.py` — replace the gate/measure rejection
  with segment accumulation + flush, reusing `iterative._flush_segment` and the
  pending-transition buffer. ~80 LOC. No new modules.
- **Tests**: a parent that applies its own `H`/`CNOT`, invokes a quantum child,
  then measures and branches on the result; a parent whose gate segment precedes
  an invoke whose returns feed a subsequent parent guard. New cases in
  `tests/test_composed_runtime.py`.
- **Dependencies**: none new.
- **Sequenced after** `add-composed-runtime` (merged). **Independent of**
  `extend-nested-shot-aggregation` (they touch different parts of the walk but
  compose cleanly).
