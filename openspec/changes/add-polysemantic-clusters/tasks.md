# Tasks: Structured-overlap Polysemantic Example

## 1. Design the concept dictionary

- [ ] 1.1 Hand-pick 12 angle triples `(α_i, β_i, γ_i)` producing three
      clusters of 4 concepts each, with analytic intra-cluster
      pairwise overlap `|<c_i | c_j>|² ∈ [0.65, 0.75]` and
      cross-cluster overlap `|<c_i | c_j>|² ∈ [0.02, 0.10]`.
      Record the Gram matrix in a short table in the example's
      leading paragraph.
- [ ] 1.2 Compute the analytic polysemy column for the feature state
      `|f> = normalize(Σ_{i ∈ capitals} |c_i>)`: expected
      P(|000>|query_i) values per concept. Document these in a
      second table alongside the Gram matrix.
- [ ] 1.3 Sanity-check the design with a scratch script before writing
      the example file — the clustered structure has to be visible
      in the expected polysemy column (i.e., capitals tier >
      non-capitals tier by at least 3× at the chosen cluster
      tightness).

## 2. Compiler helper: `compute_concept_gram`

- [ ] 2.1 Add `q_orca/compiler/concept_gram.py` exposing
      `compute_concept_gram(machine, prepare_action_label:
      str = "prepare_concept") -> numpy.ndarray[complex]`. The
      function SHALL locate the named parametric prepare action,
      enumerate its call sites in the transitions table, build the
      product-state `|c_i>` per call using the bound angle values,
      and return the `N × N` inner-product matrix with
      `gram[i, j] = <c_i | c_j>`.
- [ ] 2.2 The helper SHALL raise a structured
      `ConceptGramConfigurationError` when: the named action is not
      found, the named action has the wrong signature shape (must be
      exactly three angle parameters and no int parameter), or the
      transitions table contains zero call sites to it. Each error
      SHALL name the action and the machine.
- [ ] 2.3 Export `compute_concept_gram` and the error type from
      `q_orca/__init__.py` under a clearly-optional doc-comment
      noting the convention it assumes.
- [ ] 2.4 Add unit tests in `tests/test_compiler.py` covering: the
      happy path (Gram matrix of the new example matches the
      analytic block structure), the wrong-signature error (an
      action with two parameters raises the structured error), and
      the missing-action error.

## 3. Example: `larql-polysemantic-clusters.q.orca.md`

- [ ] 3.1 Write the example with: 3-qubit concept register, 12
      concepts across 3 clusters, one parametric prepare action,
      one parametric query action, 12 query transitions, convergent
      `done [final]` state (structure mirrors
      `larql-polysemantic-12.q.orca.md`). The leading paragraph
      SHALL document both the Gram matrix and the expected polysemy
      column as markdown tables.
- [ ] 3.2 Verify the example parses clean (`parsed.errors == []`),
      passes the verifier (static + dynamic), compiles to QASM and
      Qiskit without warning, and generates a Mermaid diagram. The
      pipeline test in task 4.1 covers this.
- [ ] 3.3 Confirm that `compile_to_qiskit` produces 12 distinct
      `qc.ry(...)` emissions per call site (i.e., per-call-site
      parametric expansion still works at 12 multi-angle call
      sites, matching what `test_larql_polysemantic_12_pipeline`
      asserts for the single-int version).

## 4. Tests

- [ ] 4.1 Add `larql-polysemantic-clusters` to the
      `EXAMPLE_FILES` fixture in `tests/test_examples.py` so the
      shared verify-all-examples fixture covers it.
- [ ] 4.2 Add `test_larql_polysemantic_clusters_pipeline` in
      `tests/test_examples.py`: asserts the parametric-action
      signature shape (`[(name, type) for p in action.parameters]`
      includes three angle params on both `prepare_concept` and
      `query_concept`), 12 parametric call sites on
      `query_concept`, QASM contains `qubit[3] q;`, Qiskit script
      contains `QuantumCircuit(3)`, and
      `compute_concept_gram(machine)` returns a 12×12 matrix whose
      intra-cluster 4×4 diagonal blocks are all > 0.5 in absolute
      magnitude and whose cross-cluster 4×4 off-diagonal blocks are
      all < 0.2 in absolute magnitude.
- [ ] 4.3 No separate shots-based regression test — Monte-Carlo
      variance at 1024 shots is too high for a deterministic
      assertion across 12 concepts. The demo exercises the shots
      path; the pipeline test exercises the analytic path.

## 5. Demo: `demos/larql_polysemantic_clusters/demo.py`

- [ ] 5.1 Mirror `demos/larql_polysemantic_12/demo.py` structurally:
      parse + verify → compile (Mermaid + QASM + Qiskit) → 12
      independent Qiskit simulations at 1024 shots each → print the
      polysemy column.
- [ ] 5.2 Print the analytic Gram matrix as an ASCII heatmap using
      `compute_concept_gram`. Use 3 tiers for the heatmap (high /
      mid / low) so the clustered block structure is visible to the
      eye.
- [ ] 5.3 Print a summary line comparing the empirical vs. analytic
      polysemy columns: `max_abs_error`, `mc_std`, and pass/fail on
      `max_abs_error < 3 * mc_std`. Exit nonzero on the pass/fail
      bit so CI could call the demo directly if desired.
- [ ] 5.4 Add a short module docstring naming the three clusters and
      pointing at the example file.

## 6. Documentation

- [ ] 6.1 README "Parametric actions" section grows a sub-heading
      "Structured overlap polysemy" with a one-paragraph summary
      and a pointer to the new example + demo. Link to the simple
      `larql-polysemantic-12.q.orca.md` from the new subsection as
      the minimum mechanism demo.
- [ ] 6.2 `CHANGELOG.md` `## Unreleased` section grows a single
      additive bullet under **Added** for the new example, demo,
      and `compute_concept_gram` helper.
- [ ] 6.3 No new top-level docs under `docs/language/` — the
      example file itself is the authoritative documentation for
      the pattern.

## 7. Spec consistency

- [ ] 7.1 `openspec validate add-polysemantic-clusters --strict`
      passes.
- [ ] 7.2 Full pytest suite green.
- [ ] 7.3 Ruff clean across touched files.
- [ ] 7.4 Run the demo locally (`python demos/larql_polysemantic_clusters/demo.py`)
      and record the empirical polysemy column in the demo's
      docstring or a companion `README.md` snippet.

## 8. Archive

- [ ] 8.1 Run `openspec archive add-polysemantic-clusters` after
      merge so the deltas land in
      `openspec/specs/{compiler,language}/spec.md`.
