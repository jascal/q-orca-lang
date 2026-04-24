## ADDED Requirements

### Requirement: Structured Polysemantic Example Pattern

The example library SHALL include at least one *structured-overlap*
polysemantic machine that demonstrates block-structured concept
geometry as distinct from uniform-overlap geometry. The canonical
file is `examples/larql-polysemantic-clusters.q.orca.md`.

A structured-polysemantic example SHALL satisfy these invariants:

1. **Compact concept register.** The `## context` declares a
   fixed-size `qubits: list<qubit>` with `n` qubits where `2^n ≥ N`
   and `N` is the number of concepts. The canonical example uses
   `n = 3, N = 12`.
2. **Product-state concept encoding.** Each concept `c_i` is prepared
   from `|0^n>` by a product-state unitary (one single-qubit rotation
   per qubit) with hand-picked per-concept angles. The canonical
   rotation family is `Ry`; future variants MAY substitute other
   single-qubit rotations.
3. **Single parametric preparation action.** Exactly one parametric
   action with signature
   `(qs, <n angle-typed params>) -> qs` and a matching product-state
   effect. The N concepts are 1-to-1 with the N angle-typed call
   sites to this action, not with N copy-pasted actions.
4. **Single parametric query action.** Exactly one parametric action
   with the same angle-typed signature as the prepare action and an
   effect that is the inverse of the prepare effect (gate order
   reversed, angle signs negated).
5. **Documented clustered Gram matrix.** The example's leading
   paragraph SHALL tabulate the analytic `|<c_i | c_j>|²` matrix
   and SHALL call out at least two tiers (intra-cluster overlap and
   cross-cluster overlap). Uniform-overlap examples like
   `larql-polysemantic-12.q.orca.md` do NOT satisfy this invariant
   and are categorized separately.
6. **Documented polysemy column for a loaded cluster.** The example
   SHALL identify a specific cluster `S ⊂ {0..N-1}` and tabulate the
   analytic `P(|0^n> | query_i)` values when the feature state is
   `|f> = normalize(Σ_{i ∈ S} |c_i>)`. The tabulated values SHALL
   exhibit the same tier structure as the Gram matrix (an
   in-cluster tier and an out-of-cluster tier).

The existing `larql-polysemantic-2.q.orca.md` and
`larql-polysemantic-12.q.orca.md` examples remain valid and
unchanged; they demonstrate the parametric-action *mechanism* with
uniform overlap. The new `larql-polysemantic-clusters.q.orca.md`
demonstrates the *phenomenon* on top of the same mechanism.

#### Scenario: Canonical example parses and verifies

- **WHEN** `parse_q_orca_markdown(open(
  "examples/larql-polysemantic-clusters.q.orca.md").read())` is
  invoked
- **THEN** `parsed.errors == []`
- **AND** `verify(parsed.file.machines[0]).valid == True`

#### Scenario: Canonical example compiles to expected register size

- **GIVEN** the canonical example has `n = 3, N = 12`
- **WHEN** `compile_to_qasm(machine)` and `compile_to_qiskit(machine)`
  are invoked
- **THEN** the QASM output contains `qubit[3] q;`
- **AND** the Qiskit script contains `QuantumCircuit(3)`
- **AND** the Qiskit script contains 12 separate sub-sequences
  corresponding to the 12 query call sites, each of which emits one
  `qc.ry(...)` per concept-register qubit after the prepare segment

#### Scenario: Structured invariants are checkable via concept_gram

- **GIVEN** the canonical example
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the returned matrix's `|gram[i,j]|²` values exhibit the
  block structure documented in the example's Gram-matrix table,
  within a numerical tolerance of `1e-6` on each entry
