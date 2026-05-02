## ADDED Requirements

### Requirement: Hierarchical Polysemantic Example Pattern

The example library SHALL include at least one *hierarchical-
overlap* polysemantic machine that demonstrates MPS-encoded concept
geometry as distinct from product-state geometry. The canonical
file is `examples/larql-polysemantic-hierarchical.q.orca.md`.

A hierarchical-polysemantic example SHALL satisfy these invariants:

1. **Compact concept register.** The `## context` declares a
   fixed-size `qubits: list<qubit>` with `n` qubits where `2^n ≥ N`
   and `N` is the number of concepts. The canonical example uses
   `n = 3, N = 12`.

2. **MPS (bond-dim-2) concept encoding.** Each concept `c_i` is
   prepared from `|0^n>` by a CNOT-staircase circuit of the form
   `Ry(qs[0], a_0) · CNOT(qs[0], qs[1]) · Ry(qs[1], a_1) ·
   CNOT(qs[1], qs[2]) · ... · Ry(qs[n-1], a_{n-1})` — `n` single-
   qubit `Ry` rotations interleaved with `n-1` CNOTs between
   adjacent qubits. Higher-bond-dim variants MAY add further 2-
   qubit gates per staircase step; this requirement addresses only
   the bond-dim-2 canonical shape.

3. **Single parametric preparation action.** Exactly one parametric
   action with signature `(qs, <n angle-typed params>) -> qs` and a
   matching CNOT-staircase effect. The N concepts are 1-to-1 with
   the N parametric call sites to this action, not with N copy-
   pasted actions.

4. **Single parametric query action.** Exactly one parametric
   action with the same angle-typed signature as the prepare action
   and an effect that is the exact inverse of the prepare effect
   (gate order reversed, angle signs negated; CNOTs self-inverse
   so they reappear in reversed position).

5. **Documented hierarchical Gram matrix.** The example's leading
   paragraph SHALL tabulate the analytic `|<c_i | c_j>|²` matrix
   and SHALL call out at least **four tiers**: self (1.0), sub-
   cluster-mate, super-group-sibling, and cross-group. Flat-tier
   examples like `larql-polysemantic-clusters.q.orca.md` (three
   tiers) do NOT satisfy this invariant and are categorized
   separately.

6. **Documented polysemy column for a loaded concept.** The example
   SHALL identify a specific concept `c_0` and tabulate the
   analytic `P(|0^n> | query_i)` values when the feature state is
   `|f> = |c_0>`. The tabulated values SHALL exhibit the same four-
   tier structure as row 0 of the Gram matrix.

The existing `larql-polysemantic-2`, `larql-polysemantic-12`, and
`larql-polysemantic-clusters` examples remain valid and unchanged;
they demonstrate the parametric-action mechanism with progressively
richer product-state geometry. The new
`larql-polysemantic-hierarchical.q.orca.md` demonstrates the first
non-product-state encoding in the polysemantic example family.

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
  `qc.cx(` calls in the expected staircase pattern
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
