## ADDED Requirements

### Requirement: HEA Concept Gram Matrix Analysis Helper

The compiler package SHALL expose an optional analysis helper
`compute_concept_gram_hea(machine, concept_action_label: str =
"query_concept") -> numpy.ndarray[complex]` that returns the `N × N`
concept-overlap matrix for machines following the rung-2
hardware-efficient ansatz (HEA) encoding.

The helper SHALL assume the following convention is in effect:

1. The machine has a parsed `EncodingDecl` with `kind == "hea"`,
   `depth ≥ 1`, `entangler ∈ {"ring", "chain"}`, and a non-empty
   `rotations` tuple over `{"Rx", "Ry", "Rz"}`.

2. The machine has a parsed `ThetaBlock` with one `ThetaRow` per
   parametric call site referenced in the transitions table. Each
   row's tensor has shape `(|rotations|, depth, n)` where `n` is
   the size of the encoding's resolved qubits register.

3. The transitions table contains `N` call sites to
   `concept_action_label`. The helper enumerates them in
   transition-declaration order and pairs each positionally with a
   theta row in declaration order (call site `i` ↔
   `theta.rows[i]`). The number of call sites SHALL equal the
   number of theta rows; mismatch raises
   `HeaGramConfigurationError`.

Given this convention, `compute_concept_gram_hea` SHALL build each
concept state `|c_i⟩` by simulating the HEA circuit on `|0^n⟩`
(per-layer single-qubit rotations from `rotations` in declared
order, then the entangler block — CNOT chain `(q, q+1)` for chain;
chain plus the wrap-around `(n-1, 0)` for ring), and SHALL return
the matrix with `gram[i, j] = ⟨c_i | c_j⟩`.

The helper is an analysis utility and SHALL NOT be part of the
main compile / verify / simulate pipeline. It is importable from
`q_orca.compiler.concept_gram_hea` and re-exported from the
top-level `q_orca` package alongside `compute_concept_gram` and
`compute_concept_gram_mps`.

QASM and Qiskit emit for HEA-encoded machines is **out of scope**
for this requirement — the helper builds states directly via numpy
without going through the QASM / Qiskit compilers.

#### Scenario: Happy path on minimal HEA example

- **GIVEN** the parsed machine from
  `examples/larql-hea-minimal.q.orca.md`, which has three
  concepts on a 3-qubit register with depth=3 ring-entangler HEA
  and rotation set `(Ry, Rz)`
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the return value is a `(3, 3)` NumPy complex array
- **AND** `|gram[i, i]| == 1` for all diagonal entries within
  `1e-9`
- **AND** the off-diagonal `|gram[i, j]|²` entries partition into
  the documented tiers within tolerance `1e-6`

#### Scenario: Missing encoding section raises structured error

- **GIVEN** a machine without an `## encoding` section
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` whose
  message names the machine and indicates that an `## encoding`
  section with `kind: hea` is required

#### Scenario: Wrong encoding kind raises structured error

- **GIVEN** a machine whose encoding has `kind: alternating-layered`
  (or any non-`hea` kind)
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` whose
  message names the actual kind and indicates that this helper
  handles `kind: hea` only

#### Scenario: Missing theta block raises structured error

- **GIVEN** a machine with an `## encoding` section but no
  `## theta` section
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` whose
  message names the machine and indicates that a `## theta` block
  is required

#### Scenario: Theta-shape mismatch raises structured error

- **GIVEN** an encoding declaring `rotations=(Ry, Rz)`, `depth=3`,
  `n=3` (expected per-row shape `(2, 3, 3)`) and a theta row
  whose tensor has shape `(2, 3, 4)` that survived initial
  parsing (e.g., loaded programmatically)
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` whose
  message names the concept, the actual shape, and the expected
  shape

#### Scenario: Call-site / theta-row count mismatch raises structured error

- **GIVEN** a machine whose transitions table has 4 call sites to
  `query_concept` but a `## theta` block declaring only 3 rows
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` naming
  the call-site count, the theta-row count, and listing the
  declared theta-row concept names as a hint

#### Scenario: No call sites raises structured error

- **GIVEN** a machine with valid `## encoding` and `## theta`
  sections but zero transitions invoking `query_concept`
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` noting
  that `query_concept` has no call sites in the transitions
  table

#### Scenario: All-zero theta produces an identity-like Gram

- **GIVEN** a machine with valid HEA encoding and a theta block
  where every row is the all-zero tensor of the correct shape
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** every concept state equals `|0^n⟩` (zero rotations
  produce identities; CNOTs on `|0^n⟩` are identities)
- **AND** `gram` is the all-ones matrix within `1e-9`
