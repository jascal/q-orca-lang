## MODIFIED Requirements

### Requirement: Pipeline Ordering

The verifier SHALL run stages in the following order: structural,
completeness, determinism, classical-context, composition,
quantum (static), dynamic (QuTiP), superposition leak. If the
structural stage produces any error, later stages SHALL be
skipped. Otherwise, every non-skipped stage SHALL run and their
errors SHALL be merged into a single result.

#### Scenario: Structural failure halts the pipeline

- **WHEN** a machine has no `[initial]` state and no states at all
- **THEN** `verify()` returns a result whose only errors come from
  the structural stage and no other stages run

#### Scenario: Merged errors from multiple stages

- **WHEN** a valid machine declares a `## verification rules` bullet
  for `unitarity` and also has an orphan event
- **THEN** the result includes an `ORPHAN_EVENT` warning from the
  structural stage AND runs the Stage-4 unitarity check

#### Scenario: Composition stage runs before quantum-static

- **WHEN** a machine has an invoke state referencing an unresolved
  child machine
- **THEN** the verifier emits `UNRESOLVED_CHILD_MACHINE` from the
  composition stage, and the quantum static stage still runs

## ADDED Requirements

### Requirement: Composition — Child Resolution and Typing

The verifier SHALL statically check every invoke state unless
`VerifyOptions.skip_composition` is set: the child machine must
resolve to another machine in the same file, argument bindings
must type-unify with the child's context, return bindings must
type-unify with the child's `## returns` declarations. For each
invoke state:

- The child machine name SHALL resolve to a `QMachineDef` in the
  same `QOrcaFile`. Otherwise: `UNRESOLVED_CHILD_MACHINE` at error
  severity.
- Each argument binding SHALL have a LHS that matches a declared
  context field on the child; otherwise: `INVOKE_ARG_UNDECLARED`.
- Each argument binding's RHS parent-side type SHALL unify with
  the child-side field type; otherwise:
  `INVOKE_ARG_TYPE_MISMATCH`.
- Each return binding's RHS SHALL match a name declared in the
  child's `## returns` section; otherwise: `INVOKE_RETURN_UNDECLARED`.
- Each return binding's LHS parent-side field type SHALL unify
  with the child-side return type (for `shots=1`) or with the
  synthesized-aggregate type (for `shots>1`); otherwise:
  `INVOKE_RETURN_TYPE_MISMATCH`.

#### Scenario: Unresolved child machine

- **WHEN** an invoke state references `Missing` but no machine
  named `Missing` exists in the file
- **THEN** the verifier emits `UNRESOLVED_CHILD_MACHINE` at error
  severity

#### Scenario: Arg type mismatch

- **WHEN** a parent binds `theta=theta` but the parent's `theta`
  is `list<float>` and the child's `theta` parameter is `float`
- **THEN** the verifier emits `INVOKE_ARG_TYPE_MISMATCH` at error
  severity

#### Scenario: Return references undeclared aggregate

- **WHEN** a parent binds `hist=hist_bits_0` under `shots=1024`
  but the child's `## returns` row for `bits[0]` lists only
  `expectation` (no `histogram`)
- **THEN** the verifier emits `INVOKE_RETURN_UNDECLARED` at error
  severity

### Requirement: Composition — Shots-Flag Rules

The verifier SHALL enforce that shot-batched mode is used only
with quantum children: `shots=N` on an invoke whose resolved
child has no measurement-bearing transitions is
`SHOTS_ON_CLASSICAL_CHILD` at error severity. Quantum children
with `shots` omitted default to `shots=1`.

#### Scenario: Shots on classical child

- **WHEN** a parent state is
  `[invoke: ClassicalChild() shots=100]` and `ClassicalChild` has
  no measurement effects
- **THEN** the verifier emits `SHOTS_ON_CLASSICAL_CHILD` at error
  severity

#### Scenario: Default shots=1 on quantum child

- **WHEN** a parent state is `[invoke: QChild(theta=theta)]` (no
  shots) and `QChild` is measurement-bearing
- **THEN** no error is emitted; the invoke is treated as
  `shots=1` for return-type unification purposes

### Requirement: Composition — Recursive Verification and Cycles

The verifier SHALL run the full verifier pipeline on each
resolved child and SHALL surface child errors into the parent
result with a `child_path` breadcrumb. Any machine that invokes
itself directly or transitively SHALL be rejected with
`INVOKE_CYCLE` at error severity.

#### Scenario: Child error bubbles up with path prefix

- **WHEN** a parent invokes `Child` from state `|train>` and
  `Child` has an `INCOMPLETE_EVENT_HANDLING` error on its
  `|idle>` state
- **THEN** the parent's verification result includes an error
  whose `location` dict carries
  `{"invoke_state": "|train>", "child_path":
    [{"state": "|idle>", "event": "<event>"}]}`

#### Scenario: Direct self-invoke

- **WHEN** a machine `Loop` has a state
  `[invoke: Loop()]`
- **THEN** the verifier emits `INVOKE_CYCLE` at error severity

#### Scenario: Transitive cycle

- **WHEN** machine `A` invokes `B` and `B` invokes `A`
- **THEN** the verifier emits `INVOKE_CYCLE` on both machines
