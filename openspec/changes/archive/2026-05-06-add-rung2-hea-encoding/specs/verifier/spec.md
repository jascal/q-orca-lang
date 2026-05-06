## MODIFIED Requirements

### Requirement: Dynamic Quantum Verification

Unless `VerifyOptions.skip_dynamic` is set, the verifier SHALL attempt
to simulate the gate sequence through QuTiP when QuTiP is importable.
When QuTiP is unavailable the stage SHALL return a passing result. For
states declared as entangled it SHALL compute reduced density matrices
and Schmidt rank across the declared or inferred qubit pair.

The dynamic verifier's gate-effect-string parsing SHALL delegate to
`q_orca.effect_parser` and SHALL NOT maintain a private regex block.
Every gate kind recognized by the shared parser — including two-qubit
parameterized gates (`RXX`, `RYY`, `RZZ`) and controlled rotations
(`CRx`, `CRy`, `CRz`) — SHALL be recognized by the dynamic verifier
without per-site code changes.

When a machine declares an `## encoding` section with
`kind == "hea"`, Stage 4b SHALL invoke
`q_orca.compiler.compute_concept_gram_hea(machine)` to validate
that the encoding declaration and the `## theta` block are
consistent and that the per-concept HEA states can be
constructed. Any `HeaGramConfigurationError` raised by the helper
SHALL be surfaced as a Stage 4b verifier error with code
`HEA_GRAM_INVALID`. Because the check builds per-concept
statevectors via numpy simulation, it SHALL be gated by the same
`VerifyOptions.skip_dynamic` flag as the backend dispatch and
SHALL NOT run when `skip_dynamic=True`.

This change introduces only the *consistency* check; enforcement
of tier-ordering bands (e.g. "sub-cluster mean exceeds
cross-cluster max by at least `HEA_TIER_TOLERANCE = 0.025`") is
deferred to a follow-up proposal that defines the matching
invariant grammar. For now `HEA_TIER_TOLERANCE` is exposed as a
module-level constant so downstream tests and the follow-up
proposal share a single source of truth, but the verifier does
not yet read it.

For machines without an `## encoding` section, Stage 4b dispatch
behavior is unchanged: rung-0 product-state and rung-1
CNOT-staircase MPS encodings continue to be detected via existing
mechanisms (effect-string introspection / explicit rung-1 helper
call).

#### Scenario: No entanglement when expected

- **WHEN** a machine declares `entanglement(q0, q1) = True` but the
  simulated circuit produces a product state
- **THEN** the verifier emits `DYNAMIC_NO_ENTANGLEMENT` at error severity

#### Scenario: QuTiP unavailable

- **WHEN** `qutip` cannot be imported
- **THEN** the dynamic stage returns a passing result with no errors

#### Scenario: Two-qubit parameterized gates appear in the gate sequence

- **WHEN** an action's effect is
  `RZZ(qs[0], qs[1], gamma); RZZ(qs[1], qs[2], gamma)`
- **THEN** `_build_gate_sequence` emits a step containing two
  `RZZ` gate-dicts, each with `targets=[i, j]` and
  `params={"theta": <gamma>}` — not an empty step

#### Scenario: Controlled rotations retain their control qubit

- **WHEN** an action's effect is `CRx(qs[0], qs[1], beta)`
- **THEN** `_build_gate_sequence` emits a gate-dict with
  `name="CRX"`, `controls=[0]`, `targets=[1]`,
  `params={"theta": <beta>}` — not a bare `RX` with empty `controls`

#### Scenario: HEA encoding triggers consistency check

- **GIVEN** a machine with `## encoding` declaring `kind: hea`
  and a valid `## theta` block whose tensor shapes match
  `(|rotations|, depth, n)` and whose row count matches the
  number of `query_concept` call sites
- **WHEN** `verify(machine)` runs Stage 4b
- **THEN** `compute_concept_gram_hea(machine)` is invoked exactly
  once
- **AND** Stage 4b reports no `HEA_GRAM_INVALID` errors

#### Scenario: HEA shape mismatch surfaces a Stage 4b error

- **GIVEN** an HEA machine whose `## theta` block has a row
  whose tensor shape does not equal `(|rotations|, depth, n)`,
  but the row survived initial parsing (e.g., loaded
  programmatically)
- **WHEN** Stage 4b runs
- **THEN** the verifier emits `HEA_GRAM_INVALID` at error
  severity, naming the offending concept and the shape mismatch

#### Scenario: HEA call-site / theta-row mismatch surfaces a Stage 4b error

- **GIVEN** an HEA machine whose `query_concept` action has more
  call sites than the `## theta` block has rows
- **WHEN** Stage 4b runs
- **THEN** the verifier emits `HEA_GRAM_INVALID` at error
  severity, naming the call-site count and the theta-row count

#### Scenario: Non-HEA machine bypasses the HEA dispatch

- **GIVEN** a machine without an `## encoding` section (e.g., the
  rung-0 `larql-polysemantic-clusters` example)
- **WHEN** Stage 4b runs
- **THEN** the verifier does NOT call
  `compute_concept_gram_hea`
- **AND** existing rung-0 / rung-1 dispatch behavior is preserved

#### Scenario: HEA check honors skip_dynamic

- **GIVEN** an HEA machine that would otherwise raise
  `HEA_GRAM_INVALID` (e.g., a programmatically shape-mismatched
  theta tensor that survived initial parsing)
- **WHEN** `verify(machine, VerifyOptions(skip_dynamic=True))`
  runs
- **THEN** `compute_concept_gram_hea` is NOT invoked
- **AND** no `HEA_GRAM_INVALID` error is emitted
