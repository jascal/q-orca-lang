## MODIFIED Requirements

### Requirement: Hierarchical Polysemantic Example Pattern

The example library SHALL include at least one *hierarchical-
overlap* polysemantic machine that demonstrates a concept geometry
whose pairwise overlap matrix is **non-factorized** — that is,
`⟨c_i | c_j⟩` does NOT decompose as a product over per-qubit
cosines of single-angle differences. The canonical file is
`examples/larql-polysemantic-hierarchical.q.orca.md`.

A hierarchical-polysemantic example SHALL satisfy these invariants:

1. **Compact concept register.** The `## context` declares a
   fixed-size `qubits: list<qubit>` with `n` qubits where `2^n ≥ N`
   and `N` is the number of concepts. The canonical example uses
   `n = 3, N = 12`.

2. **Bond-2 MPS concept encoding with non-factorized Gram.** Each
   concept `c_i` is prepared from `|0^n⟩` by a CNOT-staircase
   circuit consisting of `n` single-qubit `Ry` rotations interleaved
   with `n-1` CNOTs between adjacent qubits. The angle bound to
   each `Ry` MAY be a single parameter or a *linear combination* of
   the action's angle parameters (e.g., `α + β`). At least one of
   the `Ry` rotations SHALL bind a multi-term linear combination so
   that the Gram matrix does not factorize. The canonical example
   uses the cross-coupled-by-sum encoding

       Ry(qs[0], a)
       ; CNOT(qs[0], qs[1])
       ; Ry(qs[1], a + b)
       ; CNOT(qs[1], qs[2])
       ; Ry(qs[2], b + c)

   Higher-bond-dim variants MAY add further 2-qubit gates per
   staircase step; this requirement addresses only the bond-dim-2
   canonical shape.

3. **Non-factorization criterion.** The encoding's Gram matrix
   SHALL differ measurably from the same-angle product-state Gram.
   Specifically: with `gram_prod[i, j] = ∏_k cos((θ_{i,k} −
   θ_{j,k})/2)` over the action's `n` angle parameters, the canonical
   example SHALL satisfy `max_{i ≠ j} | |gram[i,j]|² −
   |gram_prod[i,j]|² | ≥ 0.05`. The strict-staircase shape
   `Ry(qs[k], <single param>)` interleaved with CNOTs — used by
   `add-mps-concept-encoding` and shown to factorize in this
   change's design.md — does NOT satisfy the non-factorization
   criterion and is NOT a permitted shape for the canonical
   hierarchical example. (It remains a permitted shape for *future*
   examples that document the factorization explicitly as a
   teaching point.)

4. **Single parametric preparation action.** Exactly one parametric
   action with signature `(qs, <n angle-typed params>) -> qs` and a
   matching CNOT-staircase effect satisfying invariants 2 and 3.
   The N concepts are 1-to-1 with the N parametric call sites to
   this action, not with N copy-pasted actions.

5. **Single parametric query action.** Exactly one parametric
   action with the same angle-typed signature as the prepare action
   and an effect that is the exact inverse of the prepare effect
   (gate order reversed, angle-expression signs negated, CNOTs
   self-inverse so they reappear in reversed position). When the
   prepare effect binds a linear combination like `Ry(qs[k], a + b)`,
   the inverse is `Ry(qs[k], -(a + b))` (equivalently `Ry(qs[k], -a
   - b)`).

6. **Documented hierarchical Gram matrix.** The example's leading
   paragraph SHALL tabulate the analytic `|⟨c_i | c_j⟩|²` matrix
   and SHALL call out at least **four tiers**: self (1.0), sub-
   cluster-mate, super-group-sibling, and cross-group. Flat-tier
   examples like `larql-polysemantic-clusters.q.orca.md` (three
   tiers) do NOT satisfy this invariant and are categorized
   separately.

7. **Documented polysemy column for a loaded concept.** The example
   SHALL identify a specific concept `c_0` and tabulate the
   analytic `P(|0^n⟩ | query_i)` values when the feature state is
   `|f⟩ = |c_0⟩`. The tabulated values SHALL exhibit the same four-
   tier structure as row 0 of the Gram matrix.

The existing `larql-polysemantic-2`, `larql-polysemantic-12`, and
`larql-polysemantic-clusters` examples remain valid and unchanged;
they demonstrate the parametric-action mechanism with progressively
richer product-state geometry. The
`larql-polysemantic-hierarchical.q.orca.md` example demonstrates
the first non-product-state, non-factorized-Gram encoding in the
polysemantic example family.

#### Scenario: Canonical example parses and verifies

- **WHEN** `parse_q_orca_markdown(open(
  "examples/larql-polysemantic-hierarchical.q.orca.md").read())` is
  invoked
- **THEN** `parsed.errors == []`
- **AND** `verify(parsed.file.machines[0]).valid == True`

#### Scenario: Canonical example compiles to expected register size

- **GIVEN** the canonical example has `n = 3, N = 12`
- **WHEN** `compile_to_qasm(machine)` and `compile_to_qiskit(machine)`
  are invoked
- **THEN** the QASM output contains `qubit[3] q;`
- **AND** the Qiskit script contains `QuantumCircuit(3)`
- **AND** the Qiskit script contains both `qc.ry(` calls and
  `qc.cx(` calls in the expected staircase pattern, with the
  second and third `qc.ry(` calls receiving the *evaluated* linear
  combination (e.g., `qc.ry(a_value + b_value, 1)`) rather than a
  single bound parameter
- **AND** the total number of `qc.ry(` calls matches the per-
  call-site expansion (3 for prepare + 3 × 12 = 36 for queries,
  total 39)
- **AND** the total number of `qc.cx(` calls matches the staircase
  CNOT expansion (2 for prepare + 2 × 12 = 24 for queries,
  total 26)

#### Scenario: Four-tier structure is checkable via compute_concept_gram_mps

- **GIVEN** the canonical example
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the returned matrix's `|gram[i,j]|²` values partition
  into exactly four tiers as documented in the example's leading
  paragraph, within a numerical tolerance of `1e-6` on each entry

#### Scenario: Encoding's Gram differs measurably from same-angle product-state Gram

- **GIVEN** the canonical example and its 12 angle triples `(a_i,
  b_i, c_i)`
- **WHEN** `gram_mps = compute_concept_gram_mps(machine)` and
  `gram_prod[i, j] = cos((a_i − a_j)/2) · cos((b_i − b_j)/2) ·
  cos((c_i − c_j)/2)` are computed
- **THEN** `max_{i ≠ j} | |gram_mps[i,j]|² − |gram_prod[i,j]|² |
  ≥ 0.05`

#### Scenario: Strict-staircase factorizing shape is rejected as canonical

- **GIVEN** a candidate hierarchical example whose prepare effect
  is the strict-staircase shape `Ry(qs[0], a); CNOT(qs[0], qs[1]);
  Ry(qs[1], b); CNOT(qs[1], qs[2]); Ry(qs[2], c)` (single-bound-
  param Ry rotations with no linear combinations)
- **WHEN** the encoding's Gram is compared against the same-angle
  product-state Gram
- **THEN** the two Grams are equal to within machine epsilon (the
  staircase factorizes), violating invariant 3 of this requirement
- **AND** the example does NOT satisfy this requirement as the
  canonical hierarchical example
