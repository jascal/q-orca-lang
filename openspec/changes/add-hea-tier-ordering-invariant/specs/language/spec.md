## MODIFIED Requirements

### Requirement: Theta block grammar with optional cluster column

The `## theta` block parser SHALL accept either a 2-column form
`| concept | tensor |` (existing) or a 3-column form
`| concept | cluster | tensor |` (new). Per-row, `cluster` SHALL
be a non-empty trimmed string. When the cluster column is omitted
on the header line, every row SHALL be assigned the implicit
cluster label `_default`.

A machine SHALL NOT mix forms within a single `## theta` block —
either every row declares a cluster or none does. Mixed-form blocks
SHALL be rejected as a parse error.

#### Scenario: Two-column theta block parses with implicit cluster

- **WHEN** a machine's `## theta` is `| concept | tensor |` with N
  rows
- **THEN** the parser produces N `ThetaRow` instances each with
  `cluster == "_default"`

#### Scenario: Three-column theta block carries declared clusters

- **GIVEN** a machine's `## theta` block:
  ```
  | concept | cluster | tensor |
  |---------|---------|--------|
  | a | s1 | [[...]] |
  | b | s1 | [[...]] |
  | c | s2 | [[...]] |
  ```
- **WHEN** the parser runs
- **THEN** the resulting `ThetaRow`s have
  `cluster == "s1"`, `"s1"`, `"s2"` respectively

#### Scenario: Empty cluster value is rejected

- **WHEN** a 3-column theta row has an empty cluster cell
- **THEN** the parser raises a parse error naming the offending
  row index

### Requirement: concept_gram_tier_separation invariant

The `## invariants` parser SHALL accept the resource-form bullet
`concept_gram_tier_separation <op> <decimal>` where `<op>` is one
of `<=`, `<`, `==`, `>=`, `>` and `<decimal>` is a real number in
`[0, 1]`. The parser SHALL produce
`Invariant(kind="resource", metric="concept_gram_tier_separation",
op=<op>, value=<float>)`.

Existing invariant forms (`entanglement`, `schmidt_rank`, and the
integer-valued resource metrics `gate_count`, `depth`, `cx_count`,
`t_count`, `logical_qubits`) SHALL continue to parse unchanged.

#### Scenario: Tier-separation invariant parses

- **WHEN** `## invariants` contains
  `- concept_gram_tier_separation >= 0.025`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="concept_gram_tier_separation", op="ge", value=0.025)`

#### Scenario: Tier-separation invariant accepts decimal value

- **WHEN** `## invariants` contains
  `- concept_gram_tier_separation > 0.5`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="concept_gram_tier_separation", op="gt", value=0.5)`

#### Scenario: Out-of-range decimal value is rejected

- **WHEN** `## invariants` contains
  `- concept_gram_tier_separation >= 1.5`
- **THEN** the parser raises a parse error naming the
  out-of-range value
