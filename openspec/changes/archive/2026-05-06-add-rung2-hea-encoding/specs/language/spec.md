## ADDED Requirements

### Requirement: Encoding Declaration Section

The parser SHALL recognize an optional top-level `## encoding`
section by which a `.q.orca.md` machine declares an explicit ansatz
shape. When present, the parser SHALL parse it as a key/value table
with the following keys:

| Key | Required | Type | Allowed values |
|-----|----------|------|----------------|
| `kind` | yes | string | `hea` |
| `depth` | yes | int | positive integer |
| `entangler` | yes | string | `ring` \| `chain` |
| `rotations` | yes | string | comma-separated subset of `{Rx, Ry, Rz}` (preserving declaration order) |
| `qubits` | no | string | name of a `## context` register field; defaults to `qubits` |

The parser SHALL produce an `EncodingDecl(kind, depth, entangler,
rotations, qubits)` AST node whose `rotations` field is a tuple in
the declared order.

Unknown keys, missing required keys, or out-of-range values SHALL
raise a structured parser error naming the offending row. Future
ansatz kinds (e.g. `alternating-layered`, `brick-wall`) MAY extend
the `kind` enumeration; this requirement covers `kind: hea` only.

#### Scenario: Minimal HEA encoding declaration parses

- **GIVEN** a machine containing
  ```
  ## encoding
  | key | value |
  |-----|-------|
  | kind | hea |
  | depth | 3 |
  | entangler | ring |
  | rotations | Ry, Rz |
  ```
- **WHEN** `parse_q_orca_markdown(...)` is invoked
- **THEN** `parsed.errors == []`
- **AND** `machine.encoding == EncodingDecl(kind="hea", depth=3,
  entangler="ring", rotations=("Ry", "Rz"), qubits=None)`

#### Scenario: Unknown encoding key surfaces a structured error

- **GIVEN** an encoding section containing `| frob | yes |`
- **WHEN** parsing
- **THEN** the parser emits an error naming the unknown key
  `frob` and the row number, and the machine's `encoding` field
  remains unset

#### Scenario: Unknown rotation kind is rejected

- **GIVEN** an encoding section with `rotations: Ry, Foo`
- **WHEN** parsing
- **THEN** the parser emits an error naming `Foo` as an
  unsupported rotation; supported values are `Rx`, `Ry`, `Rz`

#### Scenario: Non-positive depth is rejected

- **GIVEN** an encoding section with `depth: 0`
- **WHEN** parsing
- **THEN** the parser emits an error noting that `depth` SHALL be
  a positive integer

### Requirement: Theta Parameter Block Section

The parser SHALL recognize an optional top-level `## theta` section
that declares per-concept HEA parameter tensors. The parser SHALL
accept this section only in machines that also declare an
`## encoding` section, and SHALL parse it as a table with two
columns:

| Column | Type | Notes |
|--------|------|-------|
| `concept` | identifier | unique concept name |
| `tensor` | nested-list literal | rank-3 numeric tensor |

Each row's `tensor` literal SHALL be parsed via Python's
`ast.literal_eval` and converted to a `numpy.ndarray` with shape
`(|rotations|, depth, n)` where `rotations` and `depth` come from
`## encoding` and `n` is the size of the resolved qubits register.

The parser SHALL produce a `ThetaBlock` AST node containing one
`ThetaRow(concept, tensor)` per row, in declaration order.

Errors:

- **No encoding section.** A `## theta` section without a preceding
  `## encoding` section SHALL emit a structured error.
- **Malformed tensor literal.** Any value that fails
  `ast.literal_eval` SHALL emit an error naming the row and the
  parse failure reason.
- **Shape mismatch.** A tensor whose shape differs from
  `(|rotations|, depth, n)` SHALL emit an error naming the row,
  the actual shape, and the expected shape.
- **Duplicate concept name.** Two rows with the same `concept`
  SHALL emit an error naming the duplicate and both row numbers.
- **Non-numeric entry.** Any non-numeric leaf in the tensor SHALL
  emit an error naming the row and the offending value.

#### Scenario: Theta block parses to per-concept tensors

- **GIVEN** a machine with `rotations: Ry, Rz`, `depth: 3`,
  `qubits: list<qubit>` of size 3, and a `## theta` section
  declaring three concepts `a`, `b`, `c`, each with a
  `[[[...,...,...],...,...],...]` literal of shape `(2, 3, 3)`
- **WHEN** parsing
- **THEN** `parsed.errors == []`
- **AND** `machine.theta.rows[0] == ThetaRow(concept="a",
  tensor=<numpy ndarray shape (2,3,3)>)`
- **AND** all three rows are present in declaration order

#### Scenario: Theta without encoding is rejected

- **GIVEN** a machine that declares `## theta` but not `## encoding`
- **WHEN** parsing
- **THEN** the parser emits an error stating that `## theta`
  requires a preceding `## encoding` section

#### Scenario: Tensor shape mismatch is reported

- **GIVEN** an encoding declaring `(rotations=Ry,Rz; depth=3;
  n=3)` (expected shape `(2, 3, 3)`) and a theta row whose tensor
  has shape `(2, 3, 4)`
- **WHEN** parsing
- **THEN** the parser emits an error naming the concept, the
  actual shape `(2, 3, 4)`, and the expected shape `(2, 3, 3)`

#### Scenario: Duplicate concept rows are rejected

- **GIVEN** a theta block with two rows both named `a`
- **WHEN** parsing
- **THEN** the parser emits an error naming `a` and both row
  positions

### Requirement: Minimal HEA Example Pattern

The example library SHALL include at least one rung-2 (HEA)
polysemantic machine demonstrating the explicit `## encoding` /
`## theta` grammar. The canonical file is
`examples/larql-hea-minimal.q.orca.md`.

A minimal HEA example SHALL satisfy these invariants:

1. **Compact concept register.** The `## context` declares a
   fixed-size `qubits: list<qubit>` with `n` qubits. The canonical
   example uses `n = 3` and three concepts.

2. **HEA encoding.** The machine declares an `## encoding` section
   with `kind: hea`, `depth ≥ 2`, `entangler ∈ {ring, chain}`, and
   a `rotations` subset of `{Rx, Ry, Rz}` of size at least 1.

3. **Concept-aligned theta block.** The `## theta` block declares
   exactly one row per parametric call site referenced in the
   transitions table. Each tensor has shape
   `(|rotations|, depth, n)`.

4. **Documented Gram matrix.** The example's leading paragraph
   SHALL tabulate the analytic `|<c_i | c_j>|²` matrix and SHALL
   call out at least three tiers (self, sub-cluster, cross), with
   strict inter-tier separation greater than the Stage 4b
   tolerance of `0.025`.

#### Scenario: Canonical HEA example parses and verifies

- **WHEN** `parse_q_orca_markdown(open(
  "examples/larql-hea-minimal.q.orca.md").read())` is invoked
- **THEN** `parsed.errors == []`
- **AND** `verify(parsed.file.machines[0]).valid == True`
- **AND** `machine.encoding.kind == "hea"`
- **AND** `len(machine.theta.rows) == len(<query call sites>)`

#### Scenario: HEA Gram is checkable via compute_concept_gram_hea

- **GIVEN** the canonical example
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the returned matrix is `(N, N)` complex
- **AND** `|gram[i, i]| == 1` for all diagonal entries
- **AND** the off-diagonal `|gram[i, j]|²` entries partition into
  the documented tiers, each tier separated from the next by at
  least the Stage 4b tolerance of `0.025`
