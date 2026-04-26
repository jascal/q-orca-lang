## ADDED Requirements

### Requirement: Resource Bound Verification

The verifier SHALL run a `check_resource_invariants` rule that
evaluates each `Invariant(kind="resource")` against the metric
value computed by `q_orca/compiler/resources.py::estimate_resources`.
The rule SHALL be activated under the name `resource_bounds` in
`## verification rules` and SHALL be skipped (zero cost) when the
machine has no resource invariants.

For each resource invariant the rule SHALL:

1. Read the metric value from `estimate_resources(machine)`
   (memoized; one transpile pass per machine even with multiple
   invariants).
2. Apply the comparison operator from the invariant against the
   integer bound.
3. On violation, emit a `VerifyError` with code
   `RESOURCE_BOUND_EXCEEDED`, severity `error`, and a message
   containing the metric name, the measured value, the operator,
   and the bound.
4. On indeterminate measurement (the metric returns the literal
   string `"unknown"`), emit a `VerifyError` with code
   `RESOURCE_BOUND_INDETERMINATE` and severity `warning`.

The rule SHALL run after the existing structural and quantum
checks so a malformed circuit fails on its structural problems
first, before resource accounting is attempted.

#### Scenario: Resource bound is satisfied

- **WHEN** a machine has `cx_count <= 5` and the compiled circuit
  has 1 CX gate
- **THEN** `check_resource_invariants` emits no diagnostic, and the
  verify result remains valid

#### Scenario: Resource bound is exceeded

- **WHEN** a machine has `cx_count <= 0` and the compiled circuit
  contains a CNOT
- **THEN** `check_resource_invariants` emits a `VerifyError` with
  code `RESOURCE_BOUND_EXCEEDED`, severity `error`, and the
  message references the metric name `cx_count`, the measured
  value `1`, the operator `<=`, and the bound `0`

#### Scenario: T-count equality bound flags Clifford regression

- **WHEN** a machine has `t_count == 0` and the compiled circuit
  contains a `T` gate (decomposed by transpile to a non-zero T
  count)
- **THEN** `check_resource_invariants` emits
  `RESOURCE_BOUND_EXCEEDED` with the measured T-count and the
  expected `0`

#### Scenario: Multiple resource invariants share one transpile pass

- **WHEN** a machine has both `cx_count <= 12` and `t_count == 0`
- **THEN** `check_resource_invariants` evaluates both invariants
  using one memoized call to `estimate_resources` (no duplicate
  Qiskit transpile work)

#### Scenario: Rule is skipped when no resource invariants are present

- **WHEN** a machine has no `Invariant(kind="resource")` entries
- **THEN** `check_resource_invariants` returns immediately and does
  not invoke `estimate_resources`

#### Scenario: Indeterminate metric emits warning, not error

- **WHEN** a metric value is `"unknown"` (because of a runtime-bound
  loop construct that cannot be statically evaluated) and an
  invariant references that metric
- **THEN** `check_resource_invariants` emits a `VerifyError` with
  code `RESOURCE_BOUND_INDETERMINATE` and severity `warning`,
  and the verify result remains valid (warnings do not invalidate)

#### Scenario: Rule respects opt-out via verification rules

- **WHEN** a machine has resource invariants but its
  `## verification rules` block disables `resource_bounds`
- **THEN** `check_resource_invariants` is skipped and no
  `RESOURCE_BOUND_*` diagnostic is emitted
