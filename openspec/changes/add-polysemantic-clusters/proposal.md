## Why

The shipped polysemantic examples (`larql-polysemantic-2.q.orca.md`,
`larql-polysemantic-12.q.orca.md`) demonstrate the *parametric-action
mechanism* — one `query_concept(c: int)` action stamping 12 call sites
out of a single template — but the *quantum geometry* they use is the
degenerate case for the phenomenon they're named after. Every pair of
concepts has identical Hadamard-based overlap 1/2, so the polysemy
table has exactly two tiers: 3/4 (in-feature) and 1/3 (out-of-feature),
with nothing in between. A polysemanticity demo whose Gram matrix is
*uniform* doesn't look like polysemanticity; it looks like a single
cross-talk scalar.

Three gaps follow from the uniform-overlap choice:

1. **The Gram matrix has no structure.** Every off-diagonal entry is
   1/2. The characteristic empirical signature of polysemantic
   representations (Elhage et al., `2209.10652`) is that concepts
   sharing a semantic cluster report higher probability than
   cross-cluster concepts — a *block* Gram matrix, not a uniform one.
   Sparse-autoencoder dictionaries discovered in real transformers
   show tiered overlap, not flat overlap.

2. **Concept encoding is 1-qubit-per-concept.** The parent proposal's
   original language called for a 3-qubit concept register; the
   shipped 12-qubit variant deviates because `Hadamard(qs[c])` with
   `c ∈ {0..11}` requires the subscript to stay in range. A richer
   encoding — per-concept product-state angles — fits all 12 concepts
   into the originally intended 3-qubit register.

3. **Multi-parameter parametric actions are under-demonstrated.**
   The compiler's parametric-expansion path (see
   `q_orca/compiler/parametric.py`) already supports actions with
   mixed `int` + multiple `angle` parameters, but no example in the
   repo exercises that surface. A 3-qubit clustered demo naturally
   drives the mixed-parameter path with ~12 angle-typed bound
   arguments per call site.

The intent is to convert the polysemantic example family from a
*mechanism* demo (12 call sites from one template) into a
*phenomenon* demo (clustered concepts, block Gram matrix, tiered
polysemy scores that recover the cluster structure empirically).

## What Changes

**New example — structured overlaps, compact register:**

- New file `examples/larql-polysemantic-clusters.q.orca.md`. A 3-qubit
  concept register with 12 concepts grouped into 3 clusters of 4:
  `capitals = {Paris, Tokyo, London, Berlin}`,
  `fruits = {apple, banana, cherry, durian}`,
  `vehicles = {car, boat, plane, rocket}`. Each concept is prepared as
  a product state `Ry(qs[0], α_i) Ry(qs[1], β_i) Ry(qs[2], γ_i) |000>`
  using hand-picked per-concept angles that induce:
  - intra-cluster pairwise overlap `|<c_i | c_j>|² ≈ 0.7` (tight
    cluster);
  - cross-cluster pairwise overlap `|<c_i | c_j>|² ≈ 0.05` (nearly
    orthogonal clusters).
- One parametric preparation action
  `prepare_concept(a: angle, b: angle, c: angle) -> qs` with effect
  `Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)` and one parametric query
  action `query_concept(a: angle, b: angle, c: angle) -> qs` with
  effect `Ry(qs[2], -c); Ry(qs[1], -b); Ry(qs[0], -a)`. Both signatures
  exercise multi-angle parametric expansion.
- The `|f>` preparation loads the `capitals` cluster as
  `(|Paris> + |Tokyo> + |London> + |Berlin>) / N`. 12 query transitions
  call `query_concept` with each concept's angle triple; the expected
  polysemy table has:
  - capitals (in-feature): ~0.85 probability on `|000>`,
  - fruits / vehicles (out-of-feature): ~0.15 probability on `|000>`,
  - the 0.70 intra-cluster / 0.05 inter-cluster Gram structure
    recoverable by inspecting the full 12-row polysemy column.

**New demo:**

- New file `demos/larql_polysemantic_clusters/demo.py`. Runs 12
  independent Qiskit circuits (one per query), prints the analytic
  Gram matrix, prints the empirical polysemy column at 1024 shots per
  concept, and plots (ASCII-art) the intra-vs-inter cluster contrast.
  Mirrors `demos/larql_polysemantic_12/demo.py` structurally so a
  reader can diff the two demos to see what "structured" adds over
  "uniform."

**New compiler helper — Gram-matrix report:**

- New function `q_orca.compiler.concept_gram.compute_concept_gram(
  machine, prepare_action_label="prepare_concept") -> numpy.ndarray`.
  Walks the machine, extracts every call site to the named preparation
  action, builds the corresponding product-state statevector per call,
  and returns the `N × N` complex inner-product matrix. Used by the
  new demo's Gram-matrix print and by a test that verifies the
  example's clustered structure.
- The helper is **not** part of the main compile / verify pipeline.
  It's an optional analysis utility exported from
  `q_orca.compiler.concept_gram` for demo and test code. Runtime cost
  is `O(N · 2^n)` statevector math, fine for `N ≤ 16, n ≤ 4`.

**Documentation:**

- `README.md` "Parametric actions" section grows a second code block
  under a "Structured overlap polysemy" heading pointing at
  `examples/larql-polysemantic-clusters.q.orca.md` as the richer
  example, with `larql-polysemantic-12.q.orca.md` kept as the minimal
  mechanism demo.
- `CHANGELOG.md` `## Unreleased` grows a third bullet for the new
  example + demo + helper.

**No changes to:**

- Parser grammar (multi-angle parametric signatures already parse).
- Compiler parametric-expansion core (multi-angle substitution already
  works in `parametric.py:expand_action_call`).
- Verifier rules (no new diagnostic; the new example verifies under
  the existing rule set).
- AST shapes.

## Capabilities

### New Capabilities

- `compiler`: gains an optional `concept_gram` analysis module for
  computing the concept overlap matrix of a machine that follows the
  polysemantic preparation convention (one parametric prepare action,
  product-state concept encoding). Opt-in via explicit import; zero
  impact on machines that don't use the convention.

### Modified Capabilities

- `language`: no grammar changes, but the example-library surface
  formally includes "structured (clustered) polysemantic" as a
  supported pattern. The spec delta codifies the invariants that such
  an example SHALL satisfy (product-state encoding, single parametric
  prepare action, single parametric query action, documented Gram
  structure).

## Impact

- `examples/larql-polysemantic-clusters.q.orca.md` — new file, ~200
  lines, closely mirroring `larql-polysemantic-12.q.orca.md` structure.
- `demos/larql_polysemantic_clusters/demo.py` — new file, ~200 lines,
  mirroring `demos/larql_polysemantic_12/demo.py`.
- `q_orca/compiler/concept_gram.py` — new file, ~80 lines, numpy +
  existing angle evaluator, no new runtime dependency.
- `q_orca/__init__.py` — export `compute_concept_gram`.
- `tests/test_examples.py` — add `larql-polysemantic-clusters` to the
  example fixture list and add a dedicated pipeline test asserting
  the clustered Gram structure (intra-cluster > 0.5 diagonal blocks,
  inter-cluster < 0.2 off-diagonal blocks).
- `tests/test_compiler.py` — add a case for `compute_concept_gram`
  using the new example.
- `README.md` — new subsection under "Parametric actions" pointing at
  the new example.
- `CHANGELOG.md` — `## Unreleased` additive bullet.
- No new runtime dependency. numpy is already a dependency of the
  Qiskit path.

## Non-Goals

- **No automatic concept-dictionary learning.** The 12 angle triples
  are hand-picked. Real polysemanticity research discovers them from
  an autoencoder; this demo posits a fixed dictionary to showcase the
  phenomenon, not to replicate the learning setup.
- **No angle-sweep or optimization surface.** The angles are literals
  in the example file. Future work might explore parametrized
  `## context` angles that a demo script varies, but that's outside
  this scope.
- **No Gram-matrix check as a verifier rule.** The structural
  invariants are asserted in tests, not as a runtime verifier pass.
  Making Gram structure a verifier diagnostic would need a general
  "concept algebra" syntax in the language, which is a much larger
  scope.
- **No generalization of the concept-encoding convention.** The
  `concept_gram` helper hardcodes the "parametric prepare action with
  three angle parameters, one per qubit" shape. It's an analysis
  utility for this demo family, not a general framework.
- **Does not retire `larql-polysemantic-12.q.orca.md`.** That example
  remains the minimum-interesting parametric-action demo (single
  int-parameter, uniform overlap). The clustered version is
  additive — the two live side by side so readers can see the
  progression.
