# Tasks: Rung-2 HEA Encoding Support

## 1. Grammar + AST: `## encoding` and `## theta` sections

- [ ] 1.1 Add `EncodingDecl(kind: str, depth: int, entangler: str,
      rotations: tuple[str, ...], qubits: str | None)` and
      `ThetaBlock(rows: list[ThetaRow])` /
      `ThetaRow(concept: str, tensor: numpy.ndarray)` dataclasses
      to `q_orca/parser/ast.py`. Extend `QMachineDef` with two
      optional fields: `encoding: EncodingDecl | None = None` and
      `theta: ThetaBlock | None = None`.
- [ ] 1.2 Add `"encoding"` and `"theta"` to `_KNOWN_SECTIONS` in
      `q_orca/parser/markdown_parser.py`. Add two new section
      parsers (`_parse_encoding_section`, `_parse_theta_section`)
      hooked into the existing dispatcher loop.
- [ ] 1.3 Encoding parser accepts a key/value table. Required
      keys: `kind` (must be `hea` for this change), `depth`
      (positive int), `entangler` (`ring` | `chain`), `rotations`
      (subset of `Rx, Ry, Rz`, comma-separated). Optional `qubits`
      (default: register named `qubits`). Unknown keys → structured
      parser error naming the row.
- [ ] 1.4 Theta parser: requires that an `## encoding` section
      precedes it in the same machine. One row per concept, columns
      `| concept | tensor |`. Tensor literal SHALL parse via
      `ast.literal_eval` to a nested list, then `numpy.asarray`
      with shape `(|rotations|, depth, n)`. Errors: missing
      encoding section, malformed literal, shape mismatch,
      duplicate concept name, non-numeric tensor entry.
- [ ] 1.5 Parser tests in `tests/test_parser.py`: encoding-only
      machine, theta-only machine (rejected), encoding+theta happy
      path, unknown encoding key, unknown rotation kind, bad
      depth, malformed tensor literal, tensor shape mismatch,
      duplicate theta row.

## 2. Compiler: `compute_concept_gram_hea`

- [ ] 2.1 New file `q_orca/compiler/concept_gram_hea.py`. Function
      `compute_concept_gram_hea(machine, concept_action_label:
      str = "query_concept") -> numpy.ndarray[complex]`. Reads
      `machine.encoding` (must be `kind="hea"`) and `machine.theta`
      to recover per-concept θ tensors, builds each concept state
      by simulating the HEA circuit on `|0^n⟩`, returns
      `gram[i, j] = ⟨c_i | c_j⟩`.
- [ ] 2.2 HEA layer simulation: per layer `ℓ ∈ [0, depth)` apply
      single-qubit rotations from `rotations` in declared order
      (`θ[r, ℓ, q]` for rotation kind `r` on qubit `q`), then
      apply the entangler block (CNOTs `(q, q+1)` for chain;
      additionally `(n-1, 0)` for ring). Reuse the
      `_apply_1q` / `_apply_cnot` helpers from
      `q_orca/compiler/concept_gram_mps.py` (extract them into a
      shared `q_orca/compiler/_state_ops.py` if cleaner).
- [ ] 2.3 `HeaGramConfigurationError` covers: missing
      `## encoding`, wrong `kind`, missing `## theta`, theta-row
      shape mismatch, missing-concept (a transitions call site
      references a concept not in `theta`), zero call sites. Each
      message names the action, the machine, and the missing /
      wrong field.
- [ ] 2.4 Re-export `compute_concept_gram_hea` and
      `HeaGramConfigurationError` from `q_orca/__init__.py` /
      `__all__`.
- [ ] 2.5 Compiler tests in
      `tests/test_compiler.py::TestComputeConceptGramHea`: happy
      path on `examples/larql-hea-minimal.q.orca.md` (three-tier
      Gram), missing encoding section, wrong kind, missing theta
      section, theta-shape mismatch, missing-concept call site,
      zero-call-sites, and a degenerate-theta sanity check
      (all-zero θ → identity-like Gram, no entangler effect).

## 3. Verifier: Stage 4b HEA dispatch

- [ ] 3.1 Identify the Stage 4b dispatch site (currently
      `verifier/__init__.py:60-62` per the q-orca-lang internals
      survey). Branch on `machine.encoding is not None and
      machine.encoding.kind == "hea"` → call
      `compute_concept_gram_hea` instead of the rung-1
      effect-string-detected path. Existing rung-0 / rung-1
      dispatch is unchanged.
- [ ] 3.2 Tier-ordering tolerance for HEA Stage 4b is `0.025`
      (the spike-validated value). Surface as a module-level
      constant `HEA_TIER_TOLERANCE = 0.025` and reference it from
      both the verifier dispatch and the spec delta.
- [ ] 3.3 Verifier tests in `tests/test_verifier.py`: Stage 4b
      pass when the example's three tiers are well-separated;
      Stage 4b error (`HEA_TIER_ORDERING`) when invariants
      declare a tighter band than θ supports.

## 4. Example: `examples/larql-hea-minimal.q.orca.md`

- [ ] 4.1 3-qubit concept register, three concepts in a
      sub-cluster + one outsider configuration. Encoding:
      `kind: hea`, `depth: 3`, `entangler: ring`,
      `rotations: Ry, Rz`. Theta tensors hand-picked to produce a
      three-tier Gram (self 1.0, sub-cluster ≈ 0.7–0.8, cross
      ≤ 0.2).
- [ ] 4.2 Parses clean (`parsed.errors == []`), verifies valid
      under Stage 4b at tolerance 0.025, and the leading paragraph
      documents the analytic Gram with an ASCII heatmap.
- [ ] 4.3 Add to `EXAMPLE_FILES` fixture in
      `tests/test_examples.py`. New test
      `test_larql_hea_minimal_pipeline` asserts: encoding
      declaration parses, theta block parses with shape
      `(2, 3, 3)`, three concepts in the theta block,
      `compute_concept_gram_hea` returns a `(3, 3)` complex array,
      diagonal == 1, and the off-diagonal tiers land in the
      documented bands.

## 5. Documentation

- [ ] 5.1 README "Parametric actions" section grows an "HEA
      encoding" sub-heading with a paragraph summary, the encoding
      declaration syntax, and a link to the new example. Back-
      references rung-0 / rung-1 examples.
- [ ] 5.2 `CHANGELOG.md` `## Unreleased` grows an **Added** bullet
      describing the new example, helper, encoding/theta sections,
      and verifier extension.

## 6. Spec consistency

- [ ] 6.1 `openspec validate add-rung2-hea-encoding --strict`
      passes.
- [ ] 6.2 Full pytest suite green.
- [ ] 6.3 Ruff clean across touched files.

## 7. Archive

- [ ] 7.1 Run `openspec archive add-rung2-hea-encoding` after
      merge so the deltas land in
      `openspec/specs/{language,compiler,verifier}/spec.md`.
