# Design: Structured-overlap Polysemantic Example

## Context

The parent `extend-gate-set-and-parametric-actions` change shipped
two polysemantic examples (`larql-polysemantic-2`,
`larql-polysemantic-12`) to demonstrate parametric actions. Both use
the simplest possible concept dictionary: `|c_i> = Hadamard(qs[i])
|0^n>` — one concept per qubit, pairwise overlap fixed at 1/2 by the
Hadamard inner product structure. That choice kept the example
files short and the analytic polysemy values closed-form, but it
sacrifices the characteristic empirical signature of
polysemanticity: a *block*-structured overlap matrix where concepts
cluster into semantic groups with different intra- vs. inter-group
similarity.

This change adds a sibling example that keeps the same parametric
action mechanism but swaps in a richer concept dictionary. It is
additive — the two existing examples stay unchanged.

## Concept dictionary design

### Register and encoding

- 3-qubit concept register `qs = [q0, q1, q2]`.
- Each concept is a product state
  `|c_i> = Ry(q0, α_i) Ry(q1, β_i) Ry(q2, γ_i) |000>`.
- Single-qubit `Ry` rotations are the simplest choice that gives
  continuous, easily-invertible, real-valued unitaries. The overlap
  between two product states is
  `<c_i | c_j> = ∏_k cos((θ_{i,k} - θ_{j,k})/2)`,
  making the Gram matrix analytically tractable.

### Clustering strategy

Three clusters of four concepts each:

| Cluster   | Members                                     | Center angles `(α, β, γ)` |
|-----------|---------------------------------------------|---------------------------|
| capitals  | Paris, Tokyo, London, Berlin                | near `(0.2, 0.2, 0.2)`    |
| fruits    | apple, banana, cherry, durian               | near `(1.8, 1.8, 1.8)`    |
| vehicles  | car, boat, plane, rocket                    | near `(0.2, 1.8, 1.8)`    |

Within each cluster, the four members have angles scattered by ≤ 0.15
radians around the center. Across clusters, centers differ by ≥ 1.4
radians on at least two axes. The precise angle values will be
tuned during task 1.1 to hit the target bands:
- intra-cluster `|<c_i | c_j>|² ∈ [0.65, 0.75]`,
- inter-cluster `|<c_i | c_j>|² ∈ [0.02, 0.10]`.

Why these bands: we want the tier contrast to be visible on a
12-concept polysemy column — the intra-cluster values should be
roughly 5× the inter-cluster values so a reader can eyeball the
block structure even with Monte-Carlo noise from the demo's 1024
shots.

### Loaded feature

The `|f>` state loads the `capitals` cluster as
`|f> = (|Paris> + |Tokyo> + |London> + |Berlin>) / N`, where
`N = sqrt(4 + 12 * intra_cluster_overlap)` normalizes the
superposition. With `intra_cluster_overlap ≈ 0.7`, `N ≈ sqrt(12.4)`,
and
- `P(|000> | query_i) for i ∈ capitals ≈ (1 + 3 * 0.7)² / N² ≈ 0.77`
- `P(|000> | query_i) for i ∈ fruits ∪ vehicles ≈ (4 *
   0.05) / N² ≈ 0.02` (two orders of magnitude smaller)

The contrast is large enough that 1024 shots comfortably resolves
the two tiers.

## Alternatives considered

### Alternative 1: use an `int` + single `angle` parameter

A single-int parametric action `query_concept(c: int, θ: angle)`
with effect `Ry(qs[c mod 3], θ)` would give a more compact call site
(2 arguments vs. 3) but forces concepts into a single-qubit-active
encoding — at most 2 linearly independent states per qubit, so 6
total across 3 qubits, not 12. To fit 12 concepts that way we'd need
a 6-qubit register, which negates the "compact register" goal.
Rejected.

### Alternative 2: two-parameter polar form `Ry(θ) Rz(φ)`

Using `Ry(qs[0], θ) Rz(qs[0], φ)` per qubit (6 angles per concept
across 3 qubits) would give a richer concept manifold — the full
Bloch sphere per qubit instead of the Ry meridian. Rejected because
(a) with 12 concepts we don't need the full manifold, (b) `Rz`
phases don't change measurement probabilities in the computational
basis, so they're wasted expressiveness for a polysemy demo, and
(c) keeping the design as `Ry`-only makes the Gram matrix purely
real-valued and much easier to document in the example's markdown
table.

### Alternative 3: learned dictionary from a sparse autoencoder

The original motivation for polysemanticity is the Anthropic SAE
work (Elhage et al., `2209.10652`) where dictionaries are
*discovered* by training on activations, not hand-picked. Simulating
that would require shipping a trained autoencoder, a dataset of
activations, and training infrastructure. Rejected as far outside
scope for a q-orca example; the hand-picked dictionary is
sufficient to demonstrate the phenomenon.

### Alternative 4: skip the `concept_gram` helper

The demo could compute the Gram matrix inline with numpy without a
reusable helper. Rejected because the example's test in
`tests/test_examples.py` also needs to assert the clustered
structure, and having the helper as a single-source-of-truth
implementation avoids duplicating the product-state math between
demo and test.

## Naming

- Change ID: `add-polysemantic-clusters`. Emphasizes what's new
  relative to the existing polysemantic examples: *clusters*, not
  uniform overlap.
- Example: `larql-polysemantic-clusters.q.orca.md`. Parallel naming
  to `larql-polysemantic-2` / `larql-polysemantic-12` makes the
  family clear in `examples/` listings.
- Demo directory: `demos/larql_polysemantic_clusters/`. Same
  underscore convention as siblings.
- Compiler helper module: `q_orca/compiler/concept_gram.py`. Named
  after what it computes, not after the specific example, because
  it's potentially reusable for any future product-state concept
  demo.

## Open questions

- **Should `compute_concept_gram` support 2-angle or 4-angle
  signatures for future variants?** Current design hardcodes the
  3-angle shape matching this specific example. If a future 2-qubit
  clustered demo lands, the helper could grow to accept any
  positive number of angle parameters. Deferred — the hardcoded
  shape is sufficient for the single example this change ships, and
  generalizing before we have a second consumer is premature.

- **Should the structured-polysemantic invariants in the language
  spec be machine-checkable (e.g., a verifier rule) rather than
  documented in the spec text?** A verifier rule that flags
  "uniform-overlap polysemantic example" as a warning would
  over-specify what counts as "polysemantic" and would false-fire
  on perfectly valid non-polysemantic machines that happen to use
  parametric actions. Keeping the invariants as spec *text* (and
  asserting them in tests for the canonical example only) is the
  right level. Deferred indefinitely.
