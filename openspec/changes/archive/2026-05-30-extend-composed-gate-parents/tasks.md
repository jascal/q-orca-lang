## 1. Runtime — parent segment handling

- [x] 1.1 In `q_orca/runtime/composed.py::_walk_composed`, add a
  `segment: list[_PendingTransition]` buffer (import `_PendingTransition` and
  `_flush_segment` from `iterative`).
- [x] 1.2 Append gate / measurement / conditional-gate transitions to the
  segment instead of raising the "not yet supported" error.
- [x] 1.3 Flush the segment (via `_flush_segment`, updating `bits` /
  `aggregate_counts`) before a `context_update`, before an invoke, and on
  reaching a final state.
- [x] 1.4 Remove the gate/measurement rejection branch.

## 2. Boundary semantics

- [x] 2.1 Ensure invoke handling flushes the pending parent segment *first* so
  measured bits are observable to the invoke bindings and to subsequent guards.
- [x] 2.2 Confirm the invoke leaves the parent's quantum state untouched (child
  runs on its own register; only classical returns cross).

## 3. Tests

- [x] 3.1 Parent applies its own `H`/`CNOT`, invokes a quantum child, then
  measures and branches — assert the parent's bits reflect its own circuit.
- [x] 3.2 Parent measurement precedes an invoke whose post-invoke guard selects
  on that bit — assert the guard sees it.
- [x] 3.3 Conditional-gate (feedforward) action on the parent flushes correctly.

## 4. End-to-end + docs

- [x] 4.1 Full suite green + all examples `verify --strict`; ruff clean.
- [x] 4.2 Note the lifted restriction in the composed-runtime docs / fixture
  comments.

## 5. Spec sync

- [ ] 5.1 At archive time, sync the `runtime` delta into
  `openspec/specs/runtime/spec.md`.
