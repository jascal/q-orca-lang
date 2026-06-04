## MODIFIED Requirements

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
- `stabilizer_fallback: 'state-vector' | 'error'` (default `'error'`)

The `backend` value `'auto'` selects the Clifford-aware backend
resolution (a Clifford machine routes to the stabilizer backend, any
other to the state-vector backend). The values `'stabilizer'` and
`'stim'` are recognized backend names that force the stabilizer path.
`stabilizer_fallback` governs only the case where the stabilizer
backend is forced on a machine the Clifford classifier rejects:
`'error'` makes that fatal, `'state-vector'` downgrades it to a warning
and uses the state-vector path.

Unknown setting names SHALL produce an `unknown_assertion_policy_setting`
parser error referencing the row. A value that fails type validation
SHALL produce an `assertion_policy_value_error` referencing the row,
the setting, and the offending value.

If the section is absent, the parser SHALL produce
`QMachine.assertion_policy = AssertionPolicy()` with the defaults
above. If the section is present, the parser SHALL produce an
`AssertionPolicy` with the specified overrides applied to those
defaults.

#### Scenario: Default policy when section is absent

- **WHEN** a machine declares `[assert: …]` annotations but no
  `## assertion policy` section
- **THEN** the parsed `QMachine` has
  `assertion_policy = AssertionPolicy(shots_per_assert=512, confidence=0.99, on_failure='error', backend='auto', stabilizer_fallback='error')`

#### Scenario: Single-setting override

- **WHEN** the section contains a row `| shots_per_assert | 128 |`
- **THEN** the parsed `AssertionPolicy` has `shots_per_assert=128` and
  retains all other defaults

#### Scenario: All settings overridden

- **WHEN** the section contains rows for all recognized settings
- **THEN** the parsed `AssertionPolicy` has all fields set to the
  declared values

#### Scenario: Stabilizer backend with explicit fallback

- **WHEN** the section contains rows `| backend | stabilizer |` and
  `| stabilizer_fallback | state-vector |`
- **THEN** the parsed `AssertionPolicy` has `backend='stabilizer'` and
  `stabilizer_fallback='state-vector'`

#### Scenario: Invalid stabilizer_fallback value produces a parse error

- **WHEN** the section contains a row `| stabilizer_fallback | qutip |`
- **THEN** the parser emits `assertion_policy_value_error` referencing
  `stabilizer_fallback` and the offending value `qutip`

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
