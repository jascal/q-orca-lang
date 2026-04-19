## ADDED Requirements

### Requirement: Invoke State Annotation

The parser SHALL accept `invoke: <ChildMachineName>(<arg_bindings>)
[shots=<int>]` as a state-level annotation, alongside `[initial]`
and `[final]`. An invoke annotation marks a state as delegating to
another machine declared in the same file. Argument bindings take
the form `<child_param>=<parent_expr>`, comma-separated; the RHS
is either a bare parent-context-field identifier or an indexed
reference (`theta[0]`). Return bindings appear in the state's
body after a `returns:` line, with the analogous
`<parent_field>=<child_return>` form.

An invoke state SHALL NOT also be `[initial]` or `[final]`. A
state SHALL have at most one `invoke:` annotation. Transitions
out of an invoke state SHALL fire only after the child has
completed.

#### Scenario: Classical child with keyword args

- **WHEN** a state heading is
  `## state |train> [invoke: EpochRunner(epoch=iteration, lr=eta)]`
- **THEN** the resulting `QStateDef` has an `invoke` field of kind
  `QInvoke` with child `EpochRunner`, arg bindings
  `{epoch: iteration, lr: eta}`, and `shots=None`

#### Scenario: Quantum child with shots and returns

- **WHEN** a state body declares
  `## state |train> [invoke: QForward(theta=theta) shots=1024]` with a
  body line `> returns: bits_0_prob=prob_bits_0, bits_0_hist=hist_bits_0`
- **THEN** the state's `QInvoke` has `shots=1024`, return bindings
  `{bits_0_prob: prob_bits_0, bits_0_hist: hist_bits_0}`

#### Scenario: Invoke plus initial is a parse error

- **WHEN** a state heading is
  `## state |start> [initial] [invoke: Init()]`
- **THEN** the parser emits a structured error — an invoke state
  cannot also be initial or final

### Requirement: Returns Section

The parser SHALL accept an optional `## returns` section whose
table has `Name`, `Type`, and optional `Statistics` columns. Each
return row declares one value the machine exposes to a caller.
`Name` is a context-field identifier or an indexed reference
(`bits[0]`); `Type` uses the grammar from the `## context` section;
`Statistics` is a comma-separated list from the vocabulary
`{expectation, histogram, variance}`.

The `Statistics` column SHALL be populated only on machines that
also perform measurement (contain a transition with a
`measurement` or `mid_circuit_measure` effect). A non-empty
`Statistics` cell on a non-measurement machine is a parse error.

#### Scenario: Classical machine declares simple returns

- **WHEN** a machine has
  `## returns` with one row `| converged | bool | |`
- **THEN** the machine's `returns` list has one `QReturnDef` with
  `name="converged"`, `type=QTypeScalar(kind="bool")`, and empty
  `statistics`

#### Scenario: Quantum machine declares aggregate statistics

- **WHEN** a measurement-bearing machine declares a returns row
  `| bits[0] | bit | expectation, histogram |`
- **THEN** the `QReturnDef` has `name="bits[0]"`, `type=bit`, and
  `statistics=["expectation", "histogram"]`

#### Scenario: Statistics on a non-measurement machine rejected

- **WHEN** a machine with no measurement effects declares a
  returns row with `Statistics` = `expectation`
- **THEN** the parser emits a structured error — statistics
  annotations require a measurement-bearing machine

### Requirement: Execution Mode Flag

The parser SHALL accept an optional `shots=<int>` modifier on an
`invoke:` annotation. The integer SHALL be at least 1; otherwise
a parse error is emitted. Parse-time enforcement of
"classical-child-rejects-shots" is not possible because the
child's kind is unknown at parse time; that rule is enforced by
the verifier's composition stage.

#### Scenario: Shots=0 rejected at parse

- **WHEN** a state heading is
  `## state |s> [invoke: Child() shots=0]`
- **THEN** the parser emits a structured error — shots must be at
  least 1
