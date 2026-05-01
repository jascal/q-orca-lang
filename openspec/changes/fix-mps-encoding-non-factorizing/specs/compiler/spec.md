## MODIFIED Requirements

### Requirement: MPS Concept Gram Matrix Analysis Helper

The compiler package SHALL expose an optional analysis helper
`compute_concept_gram_mps(machine, concept_action_label: str =
"query_concept", bond_dim: int = 2) -> numpy.ndarray[complex]`
that returns the `N × N` concept-overlap matrix for machines
following the MPS (matrix product state) concept-preparation
convention.

The helper SHALL assume the following convention is in effect:

1. The named parametric action has signature
   `(qs, <n angle parameters>) -> qs` where `n` matches the size of
   the `qubits` register declared in `## context`. The number of
   angle parameters is NOT fixed at three — it scales with the
   register size.

2. The action's effect is a CNOT-staircase of the form
   `Ry(qs[0], <expr_0>); CNOT(qs[0], qs[1]); Ry(qs[1], <expr_1>);
   CNOT(qs[1], qs[2]); ... Ry(qs[n-1], <expr_{n-1}>)` — exactly `n`
   single-qubit `Ry` rotations and `n-1` CNOTs between adjacent
   qubits, in staircase order. Each `<expr_k>` SHALL be a *linear
   combination of the action's bound angle parameters* — i.e., a
   sum of terms each of the form `c · p` where `c` is a numeric
   coefficient (defaulting to 1 when omitted) and `p` is one of the
   action's angle parameter names. A single-parameter expression
   like `Ry(qs[0], a)` is the degenerate case `1 · a` and SHALL be
   accepted. The inverse pattern (for query actions: reversed gate
   order, negated angle expressions, CNOTs self-inverse) is also
   accepted.

3. The machine's transitions table contains `N ≥ 1` call sites to
   this action, each with a literal angle tuple.

4. The `bond_dim` parameter is currently fixed at `2`. Values other
   than `2` SHALL raise `MpsGramConfigurationError` with a message
   indicating that higher bond dimensions are not yet implemented.

Given this convention, `compute_concept_gram_mps` SHALL enumerate
the call sites in transition-declaration order, build the MPS state
`|c_i⟩` per call by evaluating the staircase circuit on `|0^n⟩`
(substituting the bound argument values into each `Ry`'s linear-
combination angle expression to produce a float angle), and return
the matrix with `gram[i, j] = ⟨c_i | c_j⟩` (complex-valued inner
product; values are real for the canonical `Ry` + CNOT staircase
encoding).

The helper is an analysis utility and SHALL NOT be part of the
main compile / verify / simulate pipeline. It has no effect on any
compiler entry point other than being importable from the
`q_orca.compiler.concept_gram_mps` module (and re-exported from the
top-level `q_orca` package).

The helper coexists with `compute_concept_gram` (the product-state
helper from `add-polysemantic-clusters`) — the two are separate
entry points and the caller picks based on which preparation
convention their example uses. Automatic ansatz detection is out
of scope.

#### Scenario: Happy path on polysemantic-hierarchical example with cross-coupled angles

- **GIVEN** the parsed machine from
  `examples/larql-polysemantic-hierarchical.q.orca.md`, which has
  12 call sites to a `query_concept` action with a cross-coupled-
  by-sum staircase effect (e.g., `Ry(qs[0], a); CNOT(qs[0], qs[1]);
  Ry(qs[1], a + b); CNOT(qs[1], qs[2]); Ry(qs[2], b + c)`)
- **WHEN** `compute_concept_gram_mps(machine)` is invoked (default
  label `"query_concept"`, default `bond_dim = 2`)
- **THEN** the return value is a `(12, 12)` NumPy complex array
- **AND** `|gram[i, i]| == 1` for all diagonal entries
- **AND** the off-diagonal `|gram[i, j]|²` entries partition into
  exactly four tiers as documented in the example's leading
  paragraph, within a tolerance of `1e-6` per entry
- **AND** the helper successfully evaluates each Ry's linear-
  combination angle expression by substituting the call site's
  bound argument values

#### Scenario: Single-parameter Ry continues to parse (degenerate linear combination)

- **GIVEN** a machine with a strict single-bound-param staircase
  effect `Ry(qs[0], a); CNOT(qs[0], qs[1]); Ry(qs[1], b); CNOT(qs[1],
  qs[2]); Ry(qs[2], c)`
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper parses each Ry's angle as a 1-term linear
  combination (`1 · a`, `1 · b`, `1 · c`) and returns the same Gram
  matrix it produced before this change

#### Scenario: Non-linear angle expression raises structured error

- **GIVEN** a machine where one Ry's angle expression is non-linear
  in the bound parameters — e.g., `Ry(qs[1], a * b)`,
  `Ry(qs[1], sin(a))`, `Ry(qs[1], a^2)`, or `Ry(qs[1], 2.5)` (a
  bare numeric literal with no parameter reference)
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` with kind
  `unrecognized_angle_expression` whose message names the offending
  expression, the action, the machine, and lists the supported
  shape (linear combination of bound angle parameters with optional
  numeric coefficients)

#### Scenario: Wrong signature shape raises structured error

- **GIVEN** a machine where the parametric action named
  `query_concept` has signature `(qs, c: int) -> qs` (single int
  parameter, not n angle parameters)
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` whose
  message names the action, the machine, and the required
  signature shape (n angle parameters matching register size)

#### Scenario: Non-staircase effect raises structured error

- **GIVEN** a machine where `query_concept` has the right signature
  shape but an effect that is not a CNOT-staircase (e.g., product-
  state only — no CNOTs — or CNOTs between non-adjacent qubits)
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` whose
  message identifies the unexpected gate pattern and names the
  required staircase shape

#### Scenario: Missing action raises structured error

- **GIVEN** a machine with no parametric action named
  `query_concept`
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` whose
  message names the missing action and the machine, and lists the
  available parametric actions as a hint

#### Scenario: No call sites raises structured error

- **GIVEN** a machine with a `query_concept` action of the right
  shape but zero transitions that invoke it
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` noting
  that `query_concept` has no call sites in the transitions table

#### Scenario: Unsupported bond dimension raises structured error

- **GIVEN** the canonical example
- **WHEN** `compute_concept_gram_mps(machine, bond_dim=4)` is
  invoked
- **THEN** the helper raises `MpsGramConfigurationError` with a
  message indicating that only `bond_dim=2` is currently
  implemented
