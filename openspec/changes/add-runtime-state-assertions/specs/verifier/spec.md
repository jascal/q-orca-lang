## MODIFIED Requirements

### Requirement: Pipeline Ordering

The verifier SHALL run stages in the following order: structural,
completeness, determinism, quantum (static), dynamic (QuTiP),
superposition leak, state assertions. If the structural stage produces
any error, later stages SHALL be skipped. Otherwise, every non-skipped
stage SHALL run and their errors SHALL be merged into a single result.

The state-assertions stage SHALL be skipped when the machine declares
no `state_assertions` verification rule, when no `## state` heading
carries an `[assert: …]` annotation, or when
`VerifyOptions.skip_state_assertions` is set.

#### Scenario: Structural failure halts the pipeline

- **WHEN** a machine has no `[initial]` state and no states at all
- **THEN** `verify()` returns a result whose only errors come from the
  structural stage and no other stages run

#### Scenario: Merged errors from multiple stages

- **WHEN** a valid machine declares a `## verification rules` bullet
  for `unitarity` and also has an orphan event
- **THEN** the result includes an `ORPHAN_EVENT` warning from the
  structural stage AND runs the Stage-4 unitarity check

#### Scenario: State-assertions stage skipped when no rule declared

- **WHEN** a machine carries `[assert: …]` annotations on its states
  but does not declare `state_assertions` under `## verification rules`
- **THEN** the state-assertions stage SHALL NOT run and no
  assertion-related diagnostics are emitted

#### Scenario: State-assertions stage skipped when no annotations

- **WHEN** a machine declares `state_assertions` under
  `## verification rules` but no state carries an `[assert: …]`
  annotation
- **THEN** the state-assertions stage SHALL run trivially and emit no
  diagnostics

## ADDED Requirements

### Requirement: State Assertions Stage

The verifier SHALL run `q_orca.verifier.assertions.check_state_assertions(machine,
backend)` and merge its diagnostics into the verification result whenever
the `state_assertions` verification rule is declared and at least one
state carries an `[assert: …]` annotation.

For each `QAssertion` on each annotated state, the stage SHALL:

1. Build the circuit prefix that drives the machine from `[initial]` to
   the annotated state along its declared transitions, honouring any
   intervening mid-circuit measurements via outcome-conditional replay
   on the chosen backend.
2. Run `assertion_policy.shots_per_assert` samples on the backend
   selected by `assertion_policy.backend` (`auto` resolves to QuTiP).
3. Evaluate the assertion's predicate against the sample distribution
   (Z-basis counts for `classical` / `superposition`; reduced
   density-matrix purity via partial trace for `entangled` /
   `separable`).
4. Compute a confidence bound (Wilson score interval or analogous);
   compare against `assertion_policy.confidence`.
5. Emit exactly one diagnostic per evaluated assertion, drawn from
   `ASSERTION_PASSED`, `ASSERTION_FAILED`, or
   `ASSERTION_INCONCLUSIVE`.

When the chosen backend is unavailable (e.g. QuTiP not installed and
`backend='auto'`), the stage SHALL emit one
`ASSERTION_BACKEND_MISSING` diagnostic naming the missing backend and
SHALL NOT attempt to evaluate any assertion. When the compile target
is a real device (no simulator path), the stage SHALL emit a single
informational `ASSERTIONS_SKIPPED_NO_SIMULATOR` diagnostic and SHALL
NOT evaluate any assertion.

Assertion failures SHALL be reported at error severity when
`assertion_policy.on_failure='error'` and at warning severity when
`assertion_policy.on_failure='warn'`. `ASSERTION_INCONCLUSIVE` and
`ASSERTION_BACKEND_MISSING` SHALL always be at warning severity.
`ASSERTIONS_SKIPPED_NO_SIMULATOR` SHALL be at info severity.

If a state is already flagged unreachable by the structural stage,
the assertion-checking stage SHALL skip that state silently and emit
no diagnostic for any of its assertions.

#### Scenario: Passing classical assertion

- **WHEN** a state declared `[assert: classical(qs[0])]` is reached by
  a circuit prefix that prepares `|0>` and applies no further gates
- **THEN** the verifier emits `ASSERTION_PASSED` for that assertion at
  info severity and adds no errors

#### Scenario: Passing superposition assertion

- **WHEN** a state declared `[assert: superposition(qs[0])]` is reached
  after `Hadamard(qs[0])`
- **THEN** the verifier emits `ASSERTION_PASSED` and adds no errors

#### Scenario: Passing entangled assertion on a Bell pair

- **WHEN** a state declared `[assert: entangled(qs[0], qs[1])]` is
  reached after `Hadamard(qs[0]); CNOT(qs[0], qs[1])`
- **THEN** the verifier emits `ASSERTION_PASSED` and the reduced
  density matrix on `(0, 1)` has `Tr(ρ²) < 1 - ε`

#### Scenario: Failing entangled assertion is an error

- **WHEN** a state declared `[assert: entangled(qs[0], qs[1])]` is
  reached after `Hadamard(qs[0])` only (no CNOT)
- **THEN** the verifier emits `ASSERTION_FAILED` at error severity
  citing the state and the assertion source span

#### Scenario: Inconclusive assertion at small shot counts

- **WHEN** a machine sets `shots_per_assert=16` and an assertion at the
  Wilson-score boundary cannot clear `confidence=0.99`
- **THEN** the verifier emits `ASSERTION_INCONCLUSIVE` at warning
  severity rather than `ASSERTION_FAILED`

#### Scenario: Backend missing emits a single warning

- **WHEN** `assertion_policy.backend='auto'` and QuTiP cannot be
  imported
- **THEN** the verifier emits exactly one `ASSERTION_BACKEND_MISSING`
  warning naming `qutip`, and no per-assertion diagnostics

#### Scenario: Real-device target skips assertions

- **WHEN** the compile target is a real device with no simulator path
- **THEN** the verifier emits a single
  `ASSERTIONS_SKIPPED_NO_SIMULATOR` info diagnostic and evaluates no
  assertion predicate

#### Scenario: Slice form of `superposition` requires only one qubit

- **WHEN** a state declared `[assert: superposition(qs[0..2])]` is
  reached in a GHZ-style state where individual marginals are mixed
- **THEN** the verifier emits `ASSERTION_PASSED` because at least one
  qubit's marginal Z-basis sample shows both outcomes non-trivially

#### Scenario: `on_failure='warn'` downgrades severity

- **WHEN** a machine sets `on_failure='warn'` and an assertion fails
- **THEN** the diagnostic is `ASSERTION_FAILED` at warning severity
  rather than error severity

#### Scenario: Unreachable state assertion skipped

- **WHEN** a state with `[assert: …]` annotations is flagged
  `UNREACHABLE` by the structural stage
- **THEN** the assertion-checking stage emits no diagnostic for any
  assertion on that state
