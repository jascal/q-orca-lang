## ADDED Requirements

### Requirement: Resources Section

The parser SHALL accept an optional top-level `## resources` section
containing a 2- or 3-column markdown table. The first column is
`Metric`; the second is `Basis`; the optional third is `Notes`.

The first column SHALL contain one of the five recognized metric
names: `gate_count`, `depth`, `cx_count`, `t_count`,
`logical_qubits`. Unknown names SHALL produce a structured parser
error referencing the offending row.

The second and third columns are informational; the parser SHALL
NOT validate their contents beyond requiring the table to be
well-formed markdown.

The parsed metric names SHALL populate
`QMachine.resource_metrics: list[str]`. When the section is absent,
`resource_metrics` SHALL be an empty list, and downstream consumers
(the compiler's resource report, the verifier's
`check_resource_invariants` rule) SHALL fall back to the default
metric set: all five recognized names.

#### Scenario: Two-column resources section parses

- **WHEN** a machine contains
  ```
  ## resources

  | Metric         | Basis            |
  |----------------|------------------|
  | gate_count     | logical          |
  | cx_count       | native           |
  ```
- **THEN** `machine.resource_metrics == ["gate_count", "cx_count"]`

#### Scenario: Three-column resources section parses identically

- **WHEN** a machine contains
  ```
  ## resources

  | Metric         | Basis            | Notes                |
  |----------------|------------------|----------------------|
  | gate_count     | logical          | total before decomp  |
  | cx_count       | native           | NISQ-relevant        |
  ```
- **THEN** `machine.resource_metrics == ["gate_count", "cx_count"]`
  and the `Notes` column contents are ignored

#### Scenario: Unknown metric name in resources section

- **WHEN** a machine contains a `## resources` row with metric name
  `qubit_count` (not one of the five recognized names)
- **THEN** the parser appends a structured `unknown_resource_metric`
  error referencing the row and the unrecognized name, and the
  metric is not added to `resource_metrics`

#### Scenario: Resources section is optional

- **WHEN** a machine has no `## resources` section
- **THEN** `machine.resource_metrics == []` and parsing succeeds
  with no warnings

## MODIFIED Requirements

### Requirement: Invariants

The parser SHALL accept a `## invariants` bullet list and SHALL
recognize three forms:

- `entanglement(qN, qM) = True`
- `schmidt_rank(qN, qM) <op> <number>`
- `<resource_metric> <op> <integer>` where `<resource_metric>` is
  one of `gate_count`, `depth`, `cx_count`, `t_count`,
  `logical_qubits` and `<op>` is one of `<=`, `<`, `==`, `>=`, `>`.

Resource-form invariants SHALL produce
`Invariant(kind="resource", metric=<name>, op=<op>, value=<int>)`.
The existing `entanglement` and `schmidt_rank` forms SHALL continue
to produce the same AST as before (with `metric=None`).

Unrecognized forms SHALL be silently ignored, preserving
backwards-compatibility with existing files that may use a
not-yet-recognized invariant idiom.

#### Scenario: Schmidt rank invariant

- **WHEN** `## invariants` contains `- schmidt_rank(q0, q1) >= 2`
- **THEN** the machine has an `Invariant(kind="schmidt_rank",
  qubits=[0, 1], op="ge", value=2.0, metric=None)`

#### Scenario: Resource invariant — gate count

- **WHEN** `## invariants` contains `- gate_count <= 40`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="gate_count", op="le", value=40)`

#### Scenario: Resource invariant — T-count zero

- **WHEN** `## invariants` contains `- t_count == 0`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="t_count", op="eq", value=0)`

#### Scenario: Resource invariant — logical qubit ceiling

- **WHEN** `## invariants` contains `- logical_qubits <= 3`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="logical_qubits", op="le", value=3)`

#### Scenario: Resource invariant — depth bound

- **WHEN** `## invariants` contains `- depth <= 20`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="depth", op="le", value=20)`

#### Scenario: Resource invariant — CX count bound

- **WHEN** `## invariants` contains `- cx_count <= 12`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="cx_count", op="le", value=12)`
