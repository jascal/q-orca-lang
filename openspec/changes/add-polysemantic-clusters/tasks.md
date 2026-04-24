# Tasks: Structured-overlap Polysemantic Example

## 1. Design the concept dictionary

- [x] 1.1 Hand-pick 12 angle triples `(α_i, β_i, γ_i)` producing three
      clusters of 4 concepts each, with analytic intra-cluster
      pairwise overlap `|<c_i | c_j>|² ∈ [0.65, 0.75]` and
      cross-cluster overlap `|<c_i | c_j>|² < 0.10` (clean tier
      separation; tight [0.02, 0.10] bands are not geometrically
      achievable with uniform intra overlap, so many cross-cluster
      pairs are near-orthogonal). Record the Gram matrix in a short
      table in the example's leading paragraph.
- [x] 1.2 Compute the analytic polysemy column (feature `|f> = |Paris>`,
      a single-concept load rather than a 4-concept superposition —
      simpler to prepare in a single parametric call, and the column
      directly exposes row 0 of the Gram matrix so the three-tier
      `1.0 / 0.72 / ≲ 0.09` block structure is read off). Document in
      the example's leading paragraph.
- [x] 1.3 Sanity-check the design numerically: capitals tier ≈ 0.72,
      non-capitals tier ≲ 0.017 — a ~50× ratio, well above the 3×
      minimum.

## 2. Compiler helper: `compute_concept_gram`

- [x] 2.1 Add `q_orca/compiler/concept_gram.py` exposing
      `compute_concept_gram(machine, concept_action_label:
      str = "query_concept") -> numpy.ndarray[complex]`. Locates the
      named parametric action, enumerates its call sites in
      transition-declaration order, builds the product-state
      `|c_i>` per call using the bound angle values, and returns the
      `N × N` inner-product matrix.
- [x] 2.2 Raises `ConceptGramConfigurationError` on: missing action
      (with available-parametric-action hint), wrong signature (not
      exactly three angle parameters), and zero call sites. Each
      error message names the action and the machine.
- [x] 2.3 Export `compute_concept_gram` and
      `ConceptGramConfigurationError` from `q_orca/__init__.py`.
- [x] 2.4 Unit tests in `tests/test_compiler.py::TestComputeConceptGram`
      covering happy path (block structure on clusters example),
      wrong-signature error, missing-action error, no-call-sites
      error, and zero-angle identity matrix.

## 3. Example: `larql-polysemantic-clusters.q.orca.md`

- [x] 3.1 Example written with 3-qubit concept register, 12 concepts
      across 3 clusters, one parametric `prepare_concept(a, b, c)`
      (one call site, feature = |Paris>), one parametric
      `query_concept(a, b, c)` (12 call sites), convergent `done
      [final]` state. Leading paragraph documents the Gram matrix
      (tiered ASCII + numerical ranges) and the analytic polysemy
      column.
- [x] 3.2 Parses clean (`parsed.errors == []`), verifies valid
      (static), compiles to QASM + Qiskit + Mermaid without warnings.
      Covered by `test_larql_polysemantic_clusters_pipeline`.
- [x] 3.3 `compile_to_qiskit` produces 39 `qc.ry(...)` calls —
      3 for prepare + 3 × 12 = 36 for queries — confirming per-call-site
      multi-angle parametric expansion works.

### 3a. Parser fix (unscoped — discovered during implementation)

- [x] 3a.1 `q_orca/parser/markdown_parser.py::_parse_actions_table`
      now merges parametric angle-parameter names into the angle
      context before calling `_parse_gate_from_effect`, so templates
      like `Ry(qs[0], a)` with `a: angle` no longer double-emit the
      "rotation gate Ry has unrecognized angle 'a'" error that
      `_validate_parametric_template` already surfaces as a structured
      unbound-identifier diagnostic. No grammar change.

## 4. Tests

- [x] 4.1 `larql-polysemantic-clusters` added to `EXAMPLE_FILES`
      fixture in `tests/test_examples.py`.
- [x] 4.2 `test_larql_polysemantic_clusters_pipeline` asserts
      parametric-action signature shape (three angle params on both
      `prepare_concept` and `query_concept`), 12 parametric call
      sites on `query_concept`, QASM contains `qubit[3] q;`, Qiskit
      script contains `QuantumCircuit(3)` with 39 `qc.ry(` calls,
      and `compute_concept_gram(machine)` returns a 12×12 matrix
      whose intra-cluster 4×4 diagonal blocks all have off-diag
      |<c_i|c_j>|² in [0.65, 0.75] and whose cross-cluster 4×4
      off-diagonal blocks are all < 0.10.
- [x] 4.3 No separate shots-based regression test — demo exercises
      the shots path; pipeline test exercises the analytic path.

## 5. Demo: `demos/larql_polysemantic_clusters/demo.py`

- [x] 5.1 Mirrors `demos/larql_polysemantic_12/demo.py`: parse + verify
      → compile (Mermaid + QASM + Qiskit) → 12 independent Qiskit
      circuits at 1024 shots each → polysemy column print.
- [x] 5.2 Prints the analytic Gram matrix as a 3-tier ASCII heatmap
      (`#` ≥ 0.5, `.` ∈ [0.1, 0.5), blank < 0.1) using
      `compute_concept_gram`.
- [x] 5.3 Compares empirical vs. analytic polysemy: prints
      `max |error|`, `mc_std` bound, and pass/fail on
      `max_error < 3 · mc_std`. Exits nonzero on fail.
- [x] 5.4 Module docstring names the three clusters and points at the
      example file.

## 6. Documentation

- [x] 6.1 README "Parametric actions" section grows a
      "Structured overlap polysemy" sub-heading with a paragraph
      summary and links to the new example + demo, and back to
      `larql-polysemantic-12` as the minimum-mechanism demo.
- [x] 6.2 `CHANGELOG.md` `## Unreleased` grows a bullet under **Added**
      describing the new example, demo, and `compute_concept_gram`
      helper.
- [x] 6.3 No new top-level docs under `docs/language/` — the example
      file is the authoritative documentation for the pattern.

## 7. Spec consistency

- [x] 7.1 `openspec validate add-polysemantic-clusters --strict`
      passes.
- [x] 7.2 Full pytest suite green (561 passed, 6 skipped).
- [x] 7.3 Ruff clean across touched files.
- [x] 7.4 Demo run locally produces `max_error = 0.006 < threshold =
      0.047` → PASS.

## 8. Archive

- [ ] 8.1 Run `openspec archive add-polysemantic-clusters` after
      merge so the deltas land in
      `openspec/specs/{compiler,language}/spec.md`.
