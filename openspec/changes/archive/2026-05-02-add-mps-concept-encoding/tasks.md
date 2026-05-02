# Tasks: MPS-Encoded Hierarchical Polysemantic Example

## 1. Design the hierarchical concept dictionary

- [x] 1.1 Pick 12 angle triples `(α_i, β_i, γ_i)` producing a
      two-level hierarchy under the CNOT-staircase MPS encoding
      `|c_i⟩ = Ry(q0, α_i) CNOT(q0, q1) Ry(q1, β_i) CNOT(q1, q2)
      Ry(q2, γ_i) |000⟩`. Target four Gram-matrix tiers:
      self (1.0), sub-cluster-mate (≈ 0.85–0.90), super-group-
      sibling (≈ 0.45–0.60), cross-group (< 0.15). Numerically
      verify the four-tier structure by computing the analytic
      overlap matrix via transfer-matrix contraction before writing
      the example file.
      Final design: α ∈ {0, 2π/3, 4π/3} (super-group, q0),
      β ∈ {-0.75, +0.75} (sub-cluster, q1), γ ∈ {-0.35, +0.35}
      (concept, q2). Per-tier achieved bands (numerically verified
      via `compute_concept_gram_mps` in step 2): self 1.000,
      sub-mate 0.882 (uniform), super-sib [0.472, 0.535],
      cross-group [0.118, 0.250]. Cross max sits at the cyclic-α
      cos²(π/3)=0.25 floor (above the < 0.15 stretch target);
      design.md's fallback applies — four ordered tiers with strict
      inter-tier separation (sub→super gap 0.347; super→cross gap
      0.222), which is what the pipeline test asserts.
- [x] 1.2 Document the 12-concept hierarchy (3 super-groups × 2 sub-
      clusters × 2 concepts, or whatever partition the angle design
      supports) in the example's leading paragraph with a Gram
      heatmap table.
      Hierarchy is named (animals/fruits/vehicles super-groups;
      mammals/birds, berries/tropical, land/air sub-clusters; 12
      named concepts) and documented in the example's leading
      paragraph with the angle table, the analytic per-tier band
      table, and an ASCII Gram heatmap that resolves the four tiers.
- [x] 1.3 Compute the analytic polysemy column for
      `|f⟩ = |c_0⟩` and tabulate it in the example's leading
      paragraph. Expected to show all four tiers in one column.
      Polysemy column for `|f⟩ = |dog⟩ = |c_0⟩` tabulated in the
      example: 1.000 (dog/self), 0.882 (cat/sub-mate), 0.535 / 0.472
      (robin/eagle, super-sib), and eight cross-group entries
      ranging 0.118 – 0.250. All four tiers appear in the single
      column.

## 2. Compiler helper: `compute_concept_gram_mps`

- [x] 2.1 Add `q_orca/compiler/concept_gram_mps.py` exposing
      `compute_concept_gram_mps(machine, concept_action_label:
      str = "query_concept", bond_dim: int = 2) -> numpy.ndarray
      [complex]`. Detect the CNOT-staircase pattern by parsing the
      action's effect string: expects alternating `Ry(qs[k], var)`
      and `CNOT(qs[k], qs[k+1])` for `k = 0..n-1` (with the final
      CNOT absent — n rotations, n-1 CNOTs).
      Module ships with `_RY_SEGMENT_RE` + `_CNOT_SEGMENT_RE`
      single-segment matchers and a `_parse_staircase_effect`
      helper that walks the segments in order, asserts the
      alternating Ry/CNOT pattern, sign uniformity (all-positive
      = prep, all-negated = inverse), the qubit/CNOT order for
      each form, and positional alignment between angle params
      and qubit subscripts. Register size is inferred via the
      shared `q_orca.compiler.qasm._infer_qubit_count` helper, so
      the same `qubits: list<qubit>` convention used by the
      QASM/Qiskit compilers carries through.
- [x] 2.2 For each call site, build a statevector by evaluating the
      CNOT-staircase circuit directly (bond-dim 2 → 2-qubit unitary
      per staircase step, all numpy). For each pair `(i, j)`, compute
      `gram[i, j] = ⟨c_i | c_j⟩` as the statevector inner product.
      Runtime `O(N² · 2ⁿ)` for n ≤ 8; transfer-matrix contraction
      for larger n is a future optimization (see task 2.6).
      `_build_concept_state` walks either the prep-form or
      inverse-form staircase on a `(2,)*n` numpy tensor; gates
      land via `_apply_1q` (single-qubit Ry via `tensordot` +
      `moveaxis`) and `_apply_cnot` (a cached 4×4 CNOT reshaped
      to (2,2,2,2)). Final inner products via `np.vdot` on
      flattened states.
- [x] 2.3 Raises `MpsGramConfigurationError` on: missing action
      (with available-parametric-action hint), wrong signature
      (not exactly n angle parameters matching register size),
      unrecognized gate pattern (non-staircase effect), and zero
      call sites. Each message names the action, the machine, and
      the required shape.
      `MpsGramConfigurationError` covers all four required
      cases plus the bond-dim guard from §2.6 and the
      mixed-signs / param-position-mismatch / non-adjacent-CNOT
      sub-cases that the staircase parser surfaces.
- [x] 2.4 Export `compute_concept_gram_mps` and
      `MpsGramConfigurationError` from `q_orca/__init__.py`.
      Both names re-exported from the top-level package and listed
      under `__all__` next to the existing `compute_concept_gram` /
      `ConceptGramConfigurationError` entries.
- [~] 2.5 Unit tests in `tests/test_compiler.py::TestComputeConcept
      GramMps` covering: happy path (four-tier hierarchy on the new
      example), wrong-signature error, missing-action error, non-
      staircase-effect error, no-call-sites error, and zero-angle
      identity-like matrix.
      Partial: 15 tests landed covering every error path (wrong
      signature — int param and too-few angles; missing action;
      no call sites; non-staircase product-state, non-adjacent
      CNOT, wrong segment kind; mixed signs; param/position
      mismatch; unsupported bond dim) plus structural happy
      paths (zero-angle identity gram, diagonal unit-modulus on
      mixed angles, prep-form, inverse-form, and an n=2 register
      with two computational-basis call sites at angles (0,π) and
      (π,0) showing orthogonality). The four-tier hierarchy
      happy-path on the actual example is gated on §3.1 (the
      example file) and lands with task 4.2.
- [x] 2.6 **Deferred**: actual transfer-matrix contraction (O(n ·
      χ⁶) closed-form) instead of statevector sim. Add a TODO
      comment in `concept_gram_mps.py` and list the task in
      `openspec/changes/tech-debt-backlog/tasks.md`.
      Inline `TODO(deferred)` block added next to the statevector
      construction in `compute_concept_gram_mps`, including the
      transfer-matrix sketch (per-site `T_k = sum_b A_k^b ⊗
      A_k^b†` rank-4 tensor + chain contraction) and a back-
      reference to the polysemantic-encoding research note.
      Tech-debt tracking lives in the inline TODO rather than a
      separate tech-debt-backlog entry — that change wrapped at
      24/24 in PR #44 and there's no live entry to extend; if the
      shipped example library ever pushes n past ~8 we'll spin
      this out as `vectorize-mps-gram` per the §4.1 convention.

## 3. Example: `larql-polysemantic-hierarchical.q.orca.md`

- [x] 3.1 Write the example with: 3-qubit concept register
      (`qubits: list<qubit>`), 12 concepts in a two-level hierarchy,
      one parametric `prepare_concept(a: angle, b: angle, c: angle)`
      (one call site, feature = `c_0`), one parametric
      `query_concept(a: angle, b: angle, c: angle)` (12 call sites),
      convergent `done [final]` state. Leading paragraph documents
      the hierarchy and the four-tier Gram matrix.
      `examples/larql-polysemantic-hierarchical.q.orca.md` ships
      the machine `LarqlPolysemanticHierarchical` (15 states, 25
      transitions, 2 actions). The leading paragraph documents the
      animals/fruits/vehicles super-groups, the angle table, the
      four-tier Gram band table, the ASCII heatmap, and the
      polysemy column for `|f⟩ = |dog⟩`.
- [x] 3.2 Parses clean (`parsed.errors == []`), verifies valid
      (static), compiles to QASM + Qiskit + Mermaid without
      warnings. Covered by
      `test_larql_polysemantic_hierarchical_pipeline`.
      Verified end-to-end: `parse_q_orca_markdown` returns no errors,
      `verify(skip_dynamic=True)` reports VALID with 0 errors and
      0 warnings, and the QASM/Qiskit/Mermaid compilers produce the
      expected register and gate counts.
- [x] 3.3 `compile_to_qiskit` produces the expected gate count —
      3 rotations + 2 CNOTs for prepare (5 gates) + 5 gates × 12
      queries + 2 additional CNOTs in query inversions = 65 gates.
      Exact count verified during implementation; tasks document
      the number once measured.
      Measured: 39 `qc.ry(` calls and 26 `qc.cx(` calls — i.e.,
      13 transitions × (3 Ry + 2 CX) = 65 gates total. Asserted in
      `test_larql_polysemantic_hierarchical_pipeline`.

## 4. Tests

- [x] 4.1 `larql-polysemantic-hierarchical` added to `EXAMPLE_FILES`
      fixture in `tests/test_examples.py`.
- [x] 4.2 `test_larql_polysemantic_hierarchical_pipeline` asserts:
      parametric-action signature shape (three angle params on both
      `prepare_concept` and `query_concept`), 12 parametric call
      sites on `query_concept`, QASM contains `qubit[3] q;`, Qiskit
      script contains `QuantumCircuit(3)` with the expected
      `qc.ry(` and `qc.cx(` counts, and
      `compute_concept_gram_mps(machine)` returns a 12×12 matrix
      whose four tiers land in the documented bands.
      Test landed and asserts: signature shape on both parametric
      actions, 12 query call sites, `qubit[3] q;` in QASM,
      `QuantumCircuit(3)` plus 39 ry / 26 cx in the Qiskit script,
      diagonal == 1, and the four off-diagonal tiers (sub_min ≥ 0.85,
      sub_max ≤ 0.90, super in [0.45, 0.56], cross_max ≤ 0.26) with
      strict sub→super (≥ 0.20) and super→cross (≥ 0.15)
      separation.
- [x] 4.3 Demo run exercises the shots path; pipeline test exercises
      the analytic path.
      Demo runs 12 independent prepare+query Qiskit circuits at 1024
      shots each (shots path); pipeline test only calls
      `compute_concept_gram_mps` (analytic path), so the two paths
      cover disjoint code.

## 5. Demo: `demos/larql_polysemantic_hierarchical/demo.py`

- [x] 5.1 Mirrors `demos/larql_polysemantic_clusters/demo.py`:
      parse + verify → compile (Mermaid + QASM + Qiskit) → 12
      independent Qiskit circuits at 1024 shots each → polysemy
      column print.
- [x] 5.2 Prints the analytic Gram matrix as a 4-tier ASCII heatmap
      (`#` ≥ 0.7, `o` ∈ [0.3, 0.7), `.` ∈ [0.1, 0.3), blank < 0.1)
      using `compute_concept_gram_mps`.
- [x] 5.3 Compares empirical vs. analytic polysemy: prints
      `max |error|`, `mc_std` bound, pass/fail on
      `max_error < 3 · mc_std`. Exits nonzero on fail.
- [x] 5.4 Module docstring names the hierarchy topology, points at
      the example file, and references the sibling clusters demo.
      Closing section prints a side-by-side comparison of the
      rung-0 (flat) vs. rung-1 (hierarchical) Gram signatures.

## 6. Documentation

- [x] 6.1 README "Parametric actions" section grows a
      "Hierarchical polysemy" sub-heading with a paragraph summary
      and links to the new example + demo, and back to
      `larql-polysemantic-clusters` as the flat-tier variant.
- [x] 6.2 `CHANGELOG.md` `## Unreleased` grows a bullet under
      **Added** describing the new example, demo, and
      `compute_concept_gram_mps` helper.
- [x] 6.3 No new top-level docs under `docs/language/` — the
      example file is the authoritative documentation for the
      pattern. The research note at
      `docs/research/polysemantic-encoding-beyond-product-states.md`
      already frames this as rung 1.

## 7. Spec consistency

- [x] 7.1 `openspec validate add-mps-concept-encoding --strict`
      passes.
- [x] 7.2 Full pytest suite green.
      770 passed, 6 skipped — including the new
      `test_larql_polysemantic_hierarchical_pipeline` test and the
      auto-parameterized `test_verify_all_examples` coverage.
- [x] 7.3 Ruff clean across touched files.
- [x] 7.4 Demo run locally produces `max_error < threshold` → PASS.
      Demo PASS recorded — `max_err = 0.0158` < threshold
      `0.0469` (3 × Monte-Carlo std bound at 1024 shots).

## 8. Archive

- [ ] 8.1 Run `openspec archive add-mps-concept-encoding` after
      merge so the deltas land in
      `openspec/specs/{compiler,language}/spec.md`.
