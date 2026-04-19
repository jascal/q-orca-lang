## Why

Q-Orca's parameterized rotation gates currently accept only literal angles
(`pi/4`, `1.5708`, `3*pi/4`). The language spec at
`openspec/specs/language/spec.md` explicitly notes that the
"context-reference form is not yet supported" — the parser raises an error
on `Rx(qs[0], theta)` even when `theta` is declared as a context field.
This blocks the natural way to express variational algorithms: the QAOA
and VQE examples in `examples/` declare context fields like `gamma`,
`beta`, `theta` for documentation, but their actions hardcode `pi/4` and
`pi/8` because the angles can't actually reference those fields. Making
context fields usable as gate angles closes that gap and lets users sweep
parameters by editing a single context default rather than every gate
call site.

## What Changes

- Extend `q_orca.angle.evaluate_angle` to accept an optional `context`
  mapping `{name: float}` that resolves bare identifiers and simple
  compound forms.
- Recognize the new accepted forms in addition to today's grammar:
  - bare identifier: `gamma`
  - leading minus: `-gamma`
  - integer scaling: `2*gamma`, `2gamma`, `gamma/2`
  - π scaling: `gamma*pi`, `pi*gamma`
- Update the markdown parser so that when it encounters a rotation gate
  effect (single- or two-qubit), it builds a `{name: float}` map from the
  machine's `## context` table — using `float`/`int` fields that have a
  numeric default — and passes it to `evaluate_angle`.
- Promote unrecognized identifiers and identifiers without a numeric
  default to a precise parser error that names the missing field.
- Update the QAOA and VQE examples to use the context fields they already
  declare (e.g. `RZZ(qs[0], qs[1], gamma)` instead of
  `RZZ(qs[0], qs[1], pi/4)`).

## Capabilities

### New Capabilities
None. This change extends the existing language and compiler capabilities.

### Modified Capabilities
- `language`: the rotation-gate angle grammar gains context-reference
  forms; the unrecognized-symbolic-form error message is refined.
- `compiler`: the canonical angle evaluator shared by parser, Qiskit
  compiler, and dynamic verifier resolves context references identically
  in all three sites.

## Impact

- `q_orca/angle.py` — new optional `context` parameter to
  `evaluate_angle`.
- `q_orca/parser/markdown_parser.py` — collect context-default map and
  thread it into the action-table parser; pass it to `_evaluate_angle`
  for rotation gates.
- `q_orca/compiler/qiskit.py` and `q_orca/verifier/dynamic.py` — both
  read effect strings via `_evaluate_angle`; they need to pass the same
  context map for consistency.
- `examples/qaoa-maxcut.q.orca.md`, `examples/vqe-rotation.q.orca.md`,
  `examples/vqe-heisenberg.q.orca.md` — switch hardcoded angles to
  context references.
- Tests in `tests/` — new coverage for context-angle parsing, error
  cases, and example-file regressions.
- No new runtime dependencies.
