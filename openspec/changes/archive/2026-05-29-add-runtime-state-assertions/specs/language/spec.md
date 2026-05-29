## MODIFIED Requirements

### Requirement: State Headings

Each state SHALL be introduced by its own `## state <name>` heading. The
state name SHALL be Unicode NFC normalized. The parser SHALL accept
optional `[initial]`, `[final]`, and `[assert: …]` annotations on the
heading and an optional blockquote description immediately following it.

The `[assert: …]` annotation SHALL carry one or more semicolon-separated
*category expressions* describing the expected quantum-register
configuration at that state. Recognized category expressions are:

- `classical(qs[k])`, `classical(qs[a..b])`
- `superposition(qs[k])`, `superposition(qs[a..b])`
- `entangled(qs[i], qs[j])`
- `separable(qs[i], qs[j])`

Each category expression SHALL be parsed into a `QAssertion` AST node
with fields `category`, `targets: list[QubitSlice]`, and `source_span`,
and collected into `QState.assertions: list[QAssertion]`. Multiple
bracketed annotations on the same heading SHALL be conjunctive — both
`[final]` and `[assert: classical(qs[3..4])]` may appear on the same
heading. The order of bracketed annotations SHALL NOT be significant.

Unrecognized category names inside `[assert: …]` SHALL produce a
structured `unknown_assertion_category` parser error referencing the
heading.

#### Scenario: Named ket state with annotations

- **WHEN** a heading reads `## state |ψ> = (|00> + |11>)/√2 [final]`
- **THEN** the resulting `QStateDef` has name `|ψ>`, `state_expression`
  of `(|00> + |11>)/√2`, and `is_final=True`

#### Scenario: Implicit initial state

- **WHEN** a machine has multiple `## state` headings but none is
  marked `[initial]`
- **THEN** the first state in declaration order SHALL be treated as
  initial

#### Scenario: Single-category assertion annotation

- **WHEN** a heading reads `## state |bell> [assert: entangled(qs[0], qs[1])]`
- **THEN** the resulting `QStateDef` has `assertions` of length 1 with
  `category="entangled"` and `targets=[QubitSlice(0), QubitSlice(1)]`

#### Scenario: Multi-category assertion annotation

- **WHEN** a heading reads `## state |encoded> [assert: superposition(qs[0..2]); entangled(qs[0], qs[1]); entangled(qs[1], qs[2])]`
- **THEN** the resulting `QStateDef` has `assertions` of length 3, in
  declaration order, each with the expected `category` and `targets`

#### Scenario: Slice form on a single qubit

- **WHEN** a heading reads `## state |coherent> [assert: superposition(qs[0])]`
- **THEN** the parsed `QAssertion` has
  `targets=[QubitSlice(start=0, end=0)]`

#### Scenario: Range form across multiple qubits

- **WHEN** a heading reads `## state |joint> [assert: classical(qs[3..4])]`
- **THEN** the parsed `QAssertion` has
  `targets=[QubitSlice(start=3, end=4)]`

#### Scenario: Conjunctive annotation with `[final]`

- **WHEN** a heading reads `## state |measured> [final, assert: classical(qs[3..4])]`
- **THEN** the resulting `QStateDef` has `is_final=True` AND
  `assertions` of length 1 with `category="classical"`

#### Scenario: Unknown assertion category produces a parse error

- **WHEN** a heading reads `## state |unsure> [assert: thermalised(qs[0])]`
- **THEN** the parser emits `unknown_assertion_category` referencing
  the heading and naming `thermalised` as the unrecognized category

### Requirement: Verification Rules

The parser SHALL accept a `## verification rules` bullet list. Each
bullet SHALL be parsed as `<kind>: <description>`. Known kinds SHALL
include `unitarity`, `entanglement`, `completeness`, `no_cloning`, and
`state_assertions`. All other kinds SHALL be preserved as custom rules.

The `state_assertions` rule SHALL activate the
`check_state_assertions` verifier stage defined in the verifier spec.
Absence of the rule SHALL leave that stage skipped, even if `[assert:
…]` annotations are present on individual states.

#### Scenario: Opting into unitarity

- **WHEN** `## verification rules` contains `- unitarity: all gates preserve norm`
- **THEN** the machine has a `VerificationRule(kind="unitarity")` that
  causes the Stage-4 quantum check to run

#### Scenario: Opting into state assertions

- **WHEN** `## verification rules` contains `- state_assertions: …`
- **THEN** the machine has a `VerificationRule(kind="state_assertions")`
  that causes the assertion-checking stage to run

## ADDED Requirements

### Requirement: Assertion Policy Section

The parser SHALL accept an optional `## assertion policy` section
containing a Markdown table whose first column is `Setting` and whose
second column is `Value`. Trailing columns (e.g. `Notes`) SHALL be
parsed and discarded. The recognized settings and their value types
are:

- `shots_per_assert: int` (default `512`)
- `confidence: float in [0, 1]` (default `0.99`)
- `on_failure: 'error' | 'warn'` (default `'error'`)
- `backend: 'auto' | <backend name>` (default `'auto'`)

Unknown setting names SHALL produce an `unknown_assertion_policy_setting`
parser error referencing the row. A value that fails type validation
SHALL produce an `assertion_policy_value_error` referencing the row,
the setting, and the offending value.

If the section is absent, the parser SHALL produce
`QMachine.assertion_policy = AssertionPolicy()` with the four defaults
above. If the section is present, the parser SHALL produce an
`AssertionPolicy` with the specified overrides applied to those
defaults.

#### Scenario: Default policy when section is absent

- **WHEN** a machine declares `[assert: …]` annotations but no
  `## assertion policy` section
- **THEN** the parsed `QMachine` has
  `assertion_policy = AssertionPolicy(shots_per_assert=512, confidence=0.99, on_failure='error', backend='auto')`

#### Scenario: Single-setting override

- **WHEN** the section contains a row `| shots_per_assert | 128 |`
- **THEN** the parsed `AssertionPolicy` has `shots_per_assert=128` and
  retains all other defaults

#### Scenario: All four settings overridden

- **WHEN** the section contains rows for all four recognized settings
- **THEN** the parsed `AssertionPolicy` has all four fields set to the
  declared values

#### Scenario: Unknown setting produces a parse error

- **WHEN** the section contains a row `| basis_pref | Z |`
- **THEN** the parser emits `unknown_assertion_policy_setting`
  referencing the row and naming `basis_pref`

#### Scenario: Out-of-range confidence produces a parse error

- **WHEN** the section contains a row `| confidence | 1.5 |`
- **THEN** the parser emits `assertion_policy_value_error` referencing
  `confidence` and the offending value `1.5`

#### Scenario: Notes column is accepted and ignored

- **WHEN** the section contains a header `| Setting | Value | Notes |`
  and a row `| shots_per_assert | 256 | fast for CI |`
- **THEN** the parsed `AssertionPolicy` has `shots_per_assert=256` and
  the notes content is not stored on the AST
