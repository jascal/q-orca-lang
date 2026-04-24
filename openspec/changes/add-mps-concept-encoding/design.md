# Design: MPS-Encoded Hierarchical Polysemantic Example

## Context

The shipped `larql-polysemantic-clusters` example (rung 0) achieves
block-structured Gram via **product-state** `Ry` encoding on a
3-qubit register. Its three tiers — self (1.0), cluster-mate (0.72),
cross-cluster (< 0.09) — are the only tiers achievable on the
product manifold: the factorized overlap formula
`⟨c_i | c_j⟩ = ∏_k cos((θ_{i,k} − θ_{j,k})/2)` forces uniform
intra-cluster similarity whenever cluster members are placed
symmetrically around a center.

This change adds a sibling example that keeps the same parametric-
action mechanism, the same 3-qubit register, the same 12-concept
dictionary shape, and swaps in an **entangled** product-family
preparation: a CNOT-staircase MPS with bond dimension 2. The
addition is additive — the existing clusters example stays
unchanged and serves as the flat-tier reference.

Full ladder context (rungs 0–3) and the scaling analysis that
motivates picking rung 1 next are in
`docs/research/polysemantic-encoding-beyond-product-states.md`.
The TL;DR: rung 1 is the smallest departure from rung 0 that still
admits polynomial-time closed-form Gram analysis, and it is the
smallest rung that can express *graded* within-cluster structure.

## Concept dictionary design

### Register and encoding

- 3-qubit concept register `qs = [q0, q1, q2]`.
- Each concept is an MPS (bond dim 2) prepared by a CNOT-staircase:
  `|c_i⟩ = Ry(q0, α_i) · CNOT(q0, q1) · Ry(q1, β_i) · CNOT(q1, q2)
  · Ry(q2, γ_i) |000⟩`.
- The query action is the exact inverse: angle signs negated, gate
  order reversed (CNOTs are self-inverse, so they reappear in
  reversed order):
  `Ry(q2, −γ); CNOT(q1, q2); Ry(q1, −β); CNOT(q0, q1); Ry(q0, −α)`.

### Why CNOT-staircase at χ = 2

The CNOT-staircase is the minimal entangling pattern that produces
a valid MPS — each 2-qubit step creates rank-2 Schmidt correlations
between adjacent qubits, and non-adjacent qubits are only
conditionally coupled through the chain. Higher bond dimensions
would require multiple 2-qubit gates per step (for χ = 4, a
two-qubit KAK decomposition adds two more CNOTs per step); the χ =
2 staircase is one CNOT per step, matching the research note's
recommendation to ship the minimum non-trivial rung.

### Hierarchy topology

Linear CNOT chains induce 1D locality: correlations decay with
distance along the chain. Q0 and q2 are only correlated through q1.
This naturally suggests a two-level hierarchy where:

- **Super-group index** is carried by q0 (the left-most qubit) —
  concepts with very different α angles are nearly orthogonal
  because they differ on the "root" of the chain.
- **Sub-cluster index** is carried by q1 (the middle qubit) —
  concepts with similar α but different β fall into the same super-
  group but different sub-clusters.
- **Intra-sub-cluster index** is carried by q2 — concepts that
  share both α and β but differ in γ are within the same
  sub-cluster.

A 12-concept partition compatible with this structure: 3 super-
groups × 2 sub-clusters × 2 concepts = 12.

### Tier targets

Target Gram bands (exact values depend on angle design in task 1):

| tier | definition | target `\|⟨c_i\|c_j⟩\|²` band |
|---|---|---|
| self | `i = j` | 1.0 |
| sub-cluster-mate | same α, same β, different γ | 0.85 – 0.90 |
| super-group-sibling | same α, different β | 0.45 – 0.60 |
| cross-group | different α | < 0.15 |

These bands were chosen for clear 5× separation between adjacent
tiers under 1024-shot Monte-Carlo noise.

### Loaded feature

`|f⟩ = |c_0⟩` — a single-concept load, matching the clusters demo's
simplification. The polysemy column then exposes row 0 of the Gram
matrix directly, which is the cleanest way to show the four-tier
structure to a reader.

## Alternatives considered

### Alternative 1: use a brick-wall / tree CNOT topology

2D locality via brick-wall CNOTs (q0-q1, then q1-q2 layered, then
q0-q1 again) or tree topology (q0 as root, q1 and q2 as leaves)
would give different hierarchy shapes. The **linear chain** was
chosen for this proposal because:

1. It's the simplest topology — one CNOT per adjacent pair, no
   layering decisions.
2. The resulting hierarchy (1D locality) maps naturally onto a two-
   level super/sub partition.
3. Future rung-1 variants can explore brick-wall / tree as distinct
   proposals once this one has shown whether the analytic-benchmark
   pattern survives rung 1 at all.

### Alternative 2: parameterize over bond dimension

Making `bond_dim` a parameter of the helper from the start would
generalize to χ = 4, 8, etc. Rejected because:

1. χ > 2 requires multi-CNOT staircase steps; the effect string and
   parametric-action signature bloat quickly.
2. No second use case exists yet — the clusters and hierarchical
   examples both fit in 3-qubit registers where χ = 2 is sufficient.
3. The open research question "does χ > 2 buy useful extra tier
   structure at small n?" is itself worth a separate proposal.

`bond_dim = 2` is hardcoded in the helper's implementation; the
signature still takes `bond_dim` as a parameter to leave the door
open, but higher values raise `MpsGramConfigurationError` with a
"not yet implemented" hint.

### Alternative 3: reuse `compute_concept_gram` with a structural flag

A unified helper that takes an ansatz-kind flag
(`compute_concept_gram(machine, kind="product" | "mps")`) would
avoid duplicating error-handling scaffolding. Rejected because:

1. The two helpers have different input-shape requirements
   (product-state expects no entangling gates; MPS requires exactly
   the staircase pattern). A unified entry point would need
   ansatz-detection logic to route to the right evaluator.
2. Auto-detection is explicitly a non-goal of this proposal (see
   proposal.md).
3. Two focused helpers are easier to document, test, and error-
   message well than one dispatching helper.

If rung 2 or rung 3 lands and the set of helpers grows to three or
four, a unified entry point may become worthwhile. Deferred.

### Alternative 4: skip the helper, compute Gram inline in the demo

The demo could compute the MPS Gram matrix inline with numpy
without a reusable helper. Rejected for the same reason as in the
clusters proposal: the example's test in `tests/test_examples.py`
also needs to assert the four-tier structure, and a single-source-
of-truth implementation avoids duplicating the MPS contraction
math between demo and test.

## Naming

- Change ID: `add-mps-concept-encoding`. Emphasizes what's new
  relative to the existing `compute_concept_gram`: MPS rather than
  product-state. "Hierarchical" alone would be ambiguous with
  non-MPS hierarchical encodings.
- Example: `larql-polysemantic-hierarchical.q.orca.md`. Parallel
  naming to `larql-polysemantic-2` / `larql-polysemantic-12` /
  `larql-polysemantic-clusters`; the `hierarchical` suffix flags
  the four-tier structure without committing to the MPS
  implementation detail at the filename level (the implementation
  is documented in the file's leading paragraph).
- Demo directory: `demos/larql_polysemantic_hierarchical/`. Same
  underscore convention as siblings.
- Compiler helper module: `q_orca/compiler/concept_gram_mps.py`.
  Named after what it computes (concept Gram via MPS contraction),
  parallel to `concept_gram.py`.
- Error class: `MpsGramConfigurationError`, parallel to
  `ConceptGramConfigurationError`.

## Open questions

- **Should the helper use statevector sim or transfer-matrix
  contraction?** Task 2.2 uses statevector (O(N² · 2ⁿ)) for the
  initial implementation because (a) n ≤ 4 for the shipped example
  and (b) transfer-matrix contraction requires more careful
  handling of the CNOT-staircase → MPS-tensor correspondence. Task
  2.6 defers the asymptotically-correct contraction to tech-debt
  backlog. If a future example lands at n ≥ 8, task 2.6 becomes
  blocking.

- **Should sub-cluster-mate and super-group-sibling tiers be
  asserted as non-overlapping bands in the test, or just as tier
  counts?** Initial plan: band-check in the example test matching
  task 1's numeric bands. If angle design turns out to be noisy and
  the bands overlap within their ranges, fall back to asserting
  that (a) four distinct `|<c_i|c_j>|²` clusters exist in the off-
  diagonal and (b) they are ordered correctly (self > sub > super
  > cross). Decide during task 1.1.

- **Should the helper validate the CNOT structure exactly (the
  staircase) or more permissively (any MPS-like pattern)?** Initial
  plan: strict staircase pattern with a clear error message. This
  keeps the helper simple and the error mode unambiguous. A more
  permissive detector is future work once a second MPS topology
  (brick-wall, tree) is shipped.
