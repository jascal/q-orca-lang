## ADDED Requirements

### Requirement: Concept Gram Matrix Analysis Helper

The compiler package SHALL expose an optional analysis helper
`compute_concept_gram(machine, prepare_action_label: str =
"prepare_concept") -> numpy.ndarray[complex]` that returns the
`N × N` concept-overlap matrix for machines following the
polysemantic product-state preparation convention.

The helper SHALL assume the following convention is in effect:

1. The named parametric action has signature
   `(qs, a: angle, b: angle, c: angle) -> qs` (exactly three angle
   parameters, no int parameters).
2. The action's effect is a product-state preparation of the form
   `Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)` (three single-qubit
   Ry gates on distinct qubits).
3. The machine's transitions table contains `N ≥ 1` call sites to
   this action, each with a literal angle triple.

Given this convention, `compute_concept_gram` SHALL enumerate the
call sites in transition-declaration order, build the product-state
`|c_i> = Ry(q_0, a_i) Ry(q_1, b_i) Ry(q_2, c_i) |000>` for each
call-site index `i`, and return the matrix with
`gram[i, j] = <c_i | c_j>` (complex-valued inner product).

The helper is an analysis utility and SHALL NOT be part of the
main compile / verify / simulate pipeline. It has no effect on any
compiler entry point other than being importable from the
`q_orca.compiler.concept_gram` module.

#### Scenario: Happy path on polysemantic-clusters example

- **GIVEN** the parsed machine from
  `examples/larql-polysemantic-clusters.q.orca.md`, which has 12
  call sites to a `prepare_concept` action meeting the convention
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the return value is a `(12, 12)` NumPy complex array
- **AND** `|gram[i, i]| == 1` for all diagonal entries
- **AND** `|gram[i, j]|² ∈ [0.65, 0.75]` for all `(i, j)` pairs
  where `i ≠ j` and `i, j` share a cluster
- **AND** `|gram[i, j]|² ∈ [0.02, 0.10]` for all `(i, j)` pairs
  where `i, j` are in different clusters

#### Scenario: Wrong signature shape raises structured error

- **GIVEN** a machine where the parametric action named
  `prepare_concept` has signature `(qs, c: int) -> qs` (single
  int parameter, not three angle parameters)
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the helper raises `ConceptGramConfigurationError`
  whose message names the action, the machine, and the required
  signature shape

#### Scenario: Missing action raises structured error

- **GIVEN** a machine with no parametric action named
  `prepare_concept`
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the helper raises `ConceptGramConfigurationError`
  whose message names the missing action and the machine, and
  lists the available parametric actions as a hint

#### Scenario: No call sites raises structured error

- **GIVEN** a machine with a `prepare_concept` action of the right
  shape but zero transitions that invoke it
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the helper raises `ConceptGramConfigurationError`
  noting that `prepare_concept` has no call sites in the
  transitions table
