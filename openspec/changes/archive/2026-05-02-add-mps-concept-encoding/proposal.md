## Why

The shipped `larql-polysemantic-clusters` example
(`add-polysemantic-clusters`, PR #31) demonstrates structured
polysemy on the **product-state manifold** — 12 concepts on a
3-qubit register encoded as `|c_i⟩ = Ry(q0, α_i) Ry(q1, β_i) Ry(q2,
γ_i) |000⟩`. Its three-tier block-Gram matrix (self 1.0 /
cluster-mate 0.72 / cross-cluster < 0.09) is a correct demonstration
of the *mechanism* — clustered concept geometry — but it is the
simplest shape that mechanism can produce. Three structural limits
follow directly from staying on the product manifold:

1. **Uniform intra-cluster tier.** Tetrahedral scatter around
   axis-aligned cluster centers is isotropic, so every intra-cluster
   pair has overlap ≈ 0.72 by construction. Real sparse-autoencoder
   dictionaries (Elhage et al., `2209.10652`; Anthropic
   interpretability, `2309.08600`) show *graded* within-cluster
   similarity, not flat tiers.

2. **Capacity ceiling at `N = O(n²)`.** Product states on n qubits
   have n angular dimensions. Clean block-Gram tier separation uses
   at most `O(n²)` of that budget (`K ≤ n` clusters × `m ≤ n`
   tetrahedral members). Pushing past ~50 concepts on a small
   register is not possible with rung-0 encoding.

3. **No sub-cluster structure.** Three tiers (self / cluster /
   cross) are the only tiers achievable on the product manifold.
   Hierarchical dictionaries (sub-clusters within clusters, super-
   clusters above clusters) need correlations that factored states
   cannot express.

The natural next rung is **matrix-product states with bond
dimension 2** — the smallest departure from the product-state scheme
that introduces correlations between adjacent qubits. The research
note `docs/research/polysemantic-encoding-beyond-product-states.md`
lays out the full ladder (rungs 0–3) and argues that rung 1 is the
right next step because:

- it needs **no grammar changes** — CNOT is already parsed and
  multi-gate effect strings already work;
- it preserves the **analytic-benchmark property** that makes the
  shipped demos pedagogically valuable — bond-2 transfer-matrix
  contraction runs in `O(n · χ⁶)` closed-form, not `O(2ⁿ)`;
- it answers a concrete question about whether graded within-cluster
  structure is useful pedagogically.

This proposal ships the rung-1 example, demo, and compiler helper,
leaving rungs 2–3 as scoped future proposals.

## What Changes

**New example — bond-2 MPS concept encoding:**

- New file `examples/larql-polysemantic-hierarchical.q.orca.md`.
  Same 3-qubit register as the clusters example, but each concept is
  now prepared by a CNOT-staircase MPS rather than a product. The
  parametric prepare action `prepare_concept(a: angle, b: angle, c:
  angle) -> qs` has effect
  `Ry(qs[0], a); CNOT(qs[0], qs[1]); Ry(qs[1], b); CNOT(qs[1],
  qs[2]); Ry(qs[2], c)` and the query action `query_concept` has the
  exact inverse (gates reversed, angle signs negated, CNOTs
  self-inverse).
- 12 concepts organized as a **two-level hierarchy**: 3 super-groups
  of 2 sub-clusters of 2 concepts each (or a similar 12-concept
  hierarchical partition, determined in task 1). Expected Gram
  signature: *four tiers* — self (1.0), sub-cluster-mate
  (≈ 0.85–0.90), super-group-sibling (≈ 0.45–0.60), cross-group
  (< 0.15). Exact bands determined during angle design.
- Leading paragraph documents the four-tier Gram matrix as an ASCII
  table and tabulates the analytic polysemy column with
  `|f⟩ = |c_0⟩`.

**New compiler helper — MPS-bond-2 Gram:**

- New function `q_orca.compiler.concept_gram_mps.compute_concept_
  gram_mps(machine, concept_action_label: str = "query_concept",
  bond_dim: int = 2) -> numpy.ndarray[complex]`. Detects the CNOT-
  staircase pattern in the effect string, builds transfer matrices
  per call site, and contracts pairwise to compute
  `gram[i, j] = ⟨c_i | c_j⟩`. Runtime `O(N² · n · χ⁶)` — polynomial
  in all parameters at fixed bond dim.
- Raises `MpsGramConfigurationError` on: missing action (with
  available-parametric-action hint), wrong signature (not exactly n
  angle parameters), unrecognized gate pattern (not a valid CNOT-
  staircase), and zero call sites.
- Co-exists with `compute_concept_gram` — the existing helper is
  unchanged. Callers pick between them based on which pattern their
  example uses. Auto-detection of effect structure is deferred.
- Exported from `q_orca/__init__.py` alongside
  `compute_concept_gram`.

**New demo:**

- New file `demos/larql_polysemantic_hierarchical/demo.py`. Parallels
  `demos/larql_polysemantic_clusters/demo.py`: parse + verify →
  compile (Mermaid + QASM + Qiskit) → N independent circuits at 1024
  shots each → polysemy column print → pass/fail on
  `max_error < 3 · mc_std`. Adds a second Gram-heatmap section
  showing the four-tier hierarchy vs. the clusters demo's three-tier
  flat block structure.

**Documentation:**

- `README.md` "Parametric actions" section grows a "Hierarchical
  polysemy" sub-heading pointing at the new example, and back-
  references `larql-polysemantic-clusters` as the flat-tier variant.
- `CHANGELOG.md` `## Unreleased` grows a bullet under **Added**.
- `docs/research/polysemantic-encoding-beyond-product-states.md`
  already exists and frames this proposal as rung 1 of the ansatz
  ladder. No changes to that file.

**No changes to:**

- Parser grammar. `CNOT`, `Ry`, and multi-gate effects already
  parse. The staircase is just a longer effect string.
- Parametric-action expansion. Angle literals at call sites are
  already bound per-site.
- Verifier rules. No new diagnostic; the new example verifies under
  the existing rule set.
- AST shapes.
- The existing `compute_concept_gram` helper.

## Capabilities

### New Capabilities

- `compiler`: gains `compute_concept_gram_mps` — an MPS / tensor-
  network generalization of `compute_concept_gram` that handles
  CNOT-staircase entangled concept encodings. Opt-in via explicit
  import; no impact on the main compile / verify / simulate pipeline
  and no effect on machines that do not use the MPS preparation
  convention.

### Modified Capabilities

- `language`: no grammar changes, but the example-library surface
  formally includes "hierarchical (MPS-encoded) polysemantic" as a
  supported pattern alongside the flat-block "clustered
  polysemantic" pattern. The spec delta codifies the invariants
  that such an example SHALL satisfy.

## Impact

- `examples/larql-polysemantic-hierarchical.q.orca.md` — new file,
  ~220 lines, mirroring `larql-polysemantic-clusters.q.orca.md`
  structure.
- `demos/larql_polysemantic_hierarchical/demo.py` — new file, ~250
  lines, mirroring `demos/larql_polysemantic_clusters/demo.py`.
- `q_orca/compiler/concept_gram_mps.py` — new file, ~140 lines. Uses
  numpy + the existing angle evaluator. No new runtime dependency
  (tensor contraction is numpy `einsum`).
- `q_orca/__init__.py` — export `compute_concept_gram_mps` and
  `MpsGramConfigurationError`.
- `tests/test_examples.py` — add `larql-polysemantic-hierarchical`
  to `EXAMPLE_FILES` fixture and add a dedicated pipeline test
  asserting the four-tier Gram structure.
- `tests/test_compiler.py` — add `TestComputeConceptGramMps` class
  covering happy path, wrong-signature error, missing-action error,
  non-staircase-effect error, zero-call-sites error, and a
  degenerate-angles check (all-zero angles → identity-like Gram).
- `README.md`, `CHANGELOG.md` — standard doc bumps.
- No new runtime dependency. numpy already a Qiskit dependency.

## Non-Goals

- **No general-bond-dimension helper.** The helper fixes
  `bond_dim = 2`. Higher bond dims require a more general transfer-
  matrix builder and per-concept bond-specific contractions;
  deferred until there's a second use case.
- **No automatic ansatz detection.** The caller explicitly picks
  `compute_concept_gram` (rung 0) vs. `compute_concept_gram_mps`
  (rung 1). Structural detection of effect patterns is a future
  compiler-analysis feature, out of scope.
- **No hierarchical clustering in the verifier.** The hierarchy is
  documented in the example's markdown table and asserted in tests;
  the verifier has no notion of tiers.
- **No learned MPS dictionary.** Like the clusters example, concept
  angles are hand-picked. Training-from-activations is out of scope
  for this proposal.
- **No 2D / tree CNOT topologies.** The staircase is 1D (linear
  chain of CNOTs). Brick-wall or tree patterns would induce
  different hierarchy shapes and are listed as an open research
  question in the companion research note, not a scope item here.
- **Does not retire `larql-polysemantic-clusters`.** That example
  remains the rung-0 demo (flat block Gram, product-state encoding).
  The hierarchical example is additive — the two live side-by-side
  so readers can see rung 0 → rung 1.
