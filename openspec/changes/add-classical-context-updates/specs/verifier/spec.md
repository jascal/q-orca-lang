## MODIFIED Requirements

### Requirement: Pipeline Ordering

The verifier SHALL run stages in the following order: structural,
completeness, determinism, classical-context, quantum (static),
dynamic (QuTiP), superposition leak. If the structural stage produces
any error, later stages SHALL be skipped. Otherwise, every
non-skipped stage SHALL run and their errors SHALL be merged into a
single result.

#### Scenario: Structural failure halts the pipeline

- **WHEN** a machine has no `[initial]` state and no states at all
- **THEN** `verify()` returns a result whose only errors come from the
  structural stage and no other stages run

#### Scenario: Merged errors from multiple stages

- **WHEN** a valid machine declares a `## verification rules` bullet
  for `unitarity` and also has an orphan event
- **THEN** the result includes an `ORPHAN_EVENT` warning from the
  structural stage AND runs the Stage-4 unitarity check

#### Scenario: Classical-context stage runs between completeness and quantum

- **WHEN** a machine has a context-update action that references an
  undeclared context field
- **THEN** the verifier emits `UNDECLARED_CONTEXT_FIELD` from the
  classical-context stage, and the quantum static stage still runs

## ADDED Requirements

### Requirement: Classical Context Update — Static Typing

The verifier SHALL statically type-check every context-update action
unless `VerifyOptions.skip_classical_context` is set: the LHS must
reference a declared numeric context field, list-element LHS must
be within bounds of the field's default value, and field-reference
RHS must also be a declared numeric field. For each
`QContextMutation`:

- The LHS `target_field` SHALL reference a declared `ContextField`.
  Otherwise: `UNDECLARED_CONTEXT_FIELD` at error severity.
- A scalar LHS (no `target_idx`) SHALL have type `int`. A list-index
  LHS SHALL have element type `float` (i.e., the field type is
  `list<float>`). Otherwise: `CONTEXT_FIELD_TYPE_MISMATCH` at error
  severity.
- A list-index LHS's `target_idx` SHALL be within the bounds of the
  field's default-value list. Otherwise:
  `CONTEXT_INDEX_OUT_OF_RANGE` at error severity.
- A field-reference RHS SHALL reference a declared `int` or `float`
  context field. Otherwise: same
  `UNDECLARED_CONTEXT_FIELD` or `CONTEXT_FIELD_TYPE_MISMATCH` codes.

#### Scenario: Missing field

- **WHEN** an action's effect is `nonexistent += 1`
- **THEN** the verifier emits `UNDECLARED_CONTEXT_FIELD` at error severity

#### Scenario: Wrong type

- **WHEN** the machine declares `| label | string | "foo" |` and an
  action's effect is `label += 1`
- **THEN** the verifier emits `CONTEXT_FIELD_TYPE_MISMATCH` at error
  severity

#### Scenario: List index out of range

- **WHEN** the machine declares `| theta | list<float> | [0.0, 0.0] |`
  and an action's effect is `theta[5] += 0.1`
- **THEN** the verifier emits `CONTEXT_INDEX_OUT_OF_RANGE` at error
  severity

### Requirement: Classical Context Update — Feedforward Completeness

The verifier SHALL enforce that any context-update effect
referencing `bits[i]` in its condition is preceded, on every
reachable path, by a transition that writes `bits[i]`. For each
context-update action whose effect has a non-None `bit_idx`, the
verifier SHALL confirm that on every path from the initial state
to any transition carrying that action, some prior transition's
action writes to `bits[bit_idx]` via `measure(qs[_]) -> bits[bit_idx]`
or an equivalent `mid_circuit_measure` effect.

#### Scenario: Bit read before write

- **WHEN** a machine has a context-update effect
  `if bits[0] == 1: theta[0] -= eta` but no prior transition in the
  graph writes to `bits[0]`
- **THEN** the verifier emits `BIT_READ_BEFORE_WRITE` at error severity

#### Scenario: Bit written on every path

- **WHEN** every path to the context-update action passes through a
  transition with `measure(qs[2]) -> bits[0]`
- **THEN** no `BIT_READ_BEFORE_WRITE` error is emitted
