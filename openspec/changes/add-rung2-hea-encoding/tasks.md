# Tasks: Rung-2 HEA Encoding Support

## 1. Grammar + AST: `## encoding` and `## theta` sections

- [x] 1.1 Add `EncodingDecl(kind: str, depth: int, entangler: str,
      rotations: tuple[str, ...], qubits: str | None)` and
      `ThetaBlock(rows: list[ThetaRow])` /
      `ThetaRow(concept: str, tensor: numpy.ndarray)` dataclasses
      to `q_orca/parser/ast.py`. Extend `QMachineDef` with two
      optional fields: `encoding: EncodingDecl | None = None` and
      `theta: ThetaBlock | None = None`.
- [x] 1.2 Add `"encoding"` and `"theta"` to `_KNOWN_SECTIONS` in
      `q_orca/parser/markdown_parser.py`. Add two new section
      parsers (`_parse_encoding_table`, `_parse_theta_table`)
      hooked into the existing dispatcher loop.
- [x] 1.3 Encoding parser accepts a key/value table. Required
      keys: `kind` (must be `hea` for this change), `depth`
      (positive int), `entangler` (`ring` | `chain`), `rotations`
      (subset of `Rx, Ry, Rz`, comma-separated). Optional `qubits`
      (default: register named `qubits`). Unknown keys → structured
      parser error naming the row.
- [x] 1.4 Theta parser: requires that an `## encoding` section
      precedes it in the same machine. One row per concept, columns
      `| concept | tensor |`. Tensor literal SHALL parse via
      `ast.literal_eval` to a nested list, then `numpy.asarray`
      with shape `(|rotations|, depth, n)`. Errors: missing
      encoding section, malformed literal, shape mismatch,
      duplicate concept name, non-numeric tensor entry.
- [x] 1.5 Parser tests in `tests/test_parser.py::TestHeaEncodingTheta`:
      encoding+theta happy path, theta-only machine (rejected),
      unknown encoding key, unknown rotation kind, bad depth,
      malformed tensor literal, tensor shape mismatch, duplicate
      theta row.

## 2. Compiler: `compute_concept_gram_hea`

- [x] 2.1 New file `q_orca/compiler/concept_gram_hea.py`. Function
      `compute_concept_gram_hea(machine, concept_action_label:
      str = "query_concept") -> numpy.ndarray[complex]`. Reads
      `machine.encoding` (must be `kind="hea"`) and `machine.theta`
      to recover per-concept θ tensors, builds each concept state
      by simulating the HEA circuit on `|0^n⟩`, returns
      `gram[i, j] = ⟨c_i | c_j⟩`.
- [x] 2.2 HEA layer simulation: per layer `ℓ ∈ [0, depth)` apply
      single-qubit rotations from `rotations` in declared order
      (`θ[r, ℓ, q]` for rotation kind `r` on qubit `q`), then
      apply the entangler block (CNOTs `(q, q+1)` for chain;
      additionally `(n-1, 0)` for ring). Reuses the
      `_apply_1q` / `_apply_cnot` helpers from
      `q_orca/compiler/concept_gram_mps.py` directly (no shared
      `_state_ops.py` extraction needed at this scope).
- [x] 2.3 `HeaGramConfigurationError` covers: missing
      `## encoding`, wrong `kind`, missing `## theta`, theta-row
      shape mismatch, call-site / theta-row count mismatch
      (positional pairing convention — see compiler spec delta),
      and zero call sites. Each message names the action, the
      machine, and the missing / wrong field.
- [x] 2.4 Re-export `compute_concept_gram_hea` and
      `HeaGramConfigurationError` from `q_orca/__init__.py` /
      `__all__`.
- [x] 2.5 Compiler tests in
      `tests/test_compiler.py::TestComputeConceptGramHea`: happy
      path (Hermitian gram, unit diagonal), all-zero θ sanity
      check (identity rotations + zero-controlled CNOTs → all-ones
      Gram), missing encoding section, wrong kind, missing theta
      section, call-site / theta-row count mismatch, post-parse
      theta-shape mismatch (programmatic mutation, since the
      parser rejects shape mismatches at parse time).

## 3. Verifier: Stage 4b HEA dispatch

- [x] 3.1 Add a new sub-stage `q_orca/verifier/hea_encoding.py`
      with `check_hea_encoding(machine)`. Stage 4b in
      `verifier/__init__.py` invokes it after the backend
      dispatch; it short-circuits to `[]` when the machine has no
      `## encoding` or the kind is not `hea`, otherwise it calls
      `compute_concept_gram_hea` and surfaces any
      `HeaGramConfigurationError` as a single `HEA_GRAM_INVALID`
      error. Existing rung-0 / rung-1 dispatch is unchanged.
- [x] 3.2 Surface `HEA_TIER_TOLERANCE = 0.025` as a module-level
      constant in `q_orca/verifier/hea_encoding.py` and reference
      it from the spec delta. Tier-ordering enforcement itself is
      out of scope for this change (no matching invariants
      grammar yet) and deferred to a follow-up proposal — the
      constant is exposed only for downstream tests.
- [x] 3.3 Verifier tests in
      `tests/test_verifier.py::TestHeaEncodingVerifier`: Stage 4b
      passes on a valid HEA machine; emits `HEA_GRAM_INVALID` on
      a call-site / theta-row count mismatch; emits
      `HEA_GRAM_INVALID` on a post-parse theta-shape mismatch;
      bypasses the dispatch entirely on a non-HEA machine
      (Bell-entangler, asserted via mock). Tier-ordering
      enforcement (the `HEA_TIER_ORDERING` code originally
      sketched here) is deferred to the follow-up proposal.

## 4. Example: `examples/larql-hea-minimal.q.orca.md`

- [x] 4.1 3-qubit concept register, three concepts in a
      sub-cluster + one outsider configuration. Encoding:
      `kind: hea`, `depth: 3`, `entangler: ring`,
      `rotations: Ry, Rz`. Theta tensors hand-picked to produce a
      sub-cluster (a–b ≈ 0.9999) vs cross-cluster outsider
      (a–c, b–c ≈ 0.38) Gram with a sub→cross gap ≈ 0.6162 — well
      above `HEA_TIER_TOLERANCE = 0.025`.
- [x] 4.2 Parses clean (`parsed.errors == []`), verifies valid
      with `skip_dynamic=True`, and the leading paragraph
      documents the analytic Gram with the documented separation.
- [x] 4.3 Added to `EXAMPLE_FILES` fixture in
      `tests/test_examples.py`. New test
      `test_larql_hea_minimal_pipeline` asserts: encoding
      declaration parses, theta block parses with shape
      `(2, 3, 3)`, three concepts in the theta block, three
      `query_concept` call sites, verify passes with
      `skip_dynamic=True`, `compute_concept_gram_hea` returns a
      `(3, 3)` complex array, diagonal == 1, sub-cluster ≥ 0.999,
      cross-cluster in [0.35, 0.42], and sub→cross gap clears
      `HEA_TIER_TOLERANCE`.

## 5. Documentation

- [x] 5.1 README "Bundled example machines" table grows a
      `larql-hea-minimal.q.orca.md` row, the example-count claim
      bumps from 15 → 19, and the "Shipped" landed-features list
      grows an "HEA concept encoding (rung 2)" bullet that
      summarizes the grammar, helper, and verifier sub-stage.
- [x] 5.2 `CHANGELOG.md` grows a `0.8.0` section with **Added** and
      **Changed** bullets describing the encoding/theta grammar,
      the helper, the verifier sub-stage, and the new example.
      Version bumped in `q_orca/__init__.py`.

## 6. Spec consistency

- [x] 6.1 `openspec validate add-rung2-hea-encoding --strict`
      passes.
- [x] 6.2 Full pytest suite green (787+ tests).
- [x] 6.3 Ruff clean across touched files (no new violations
      introduced; pre-existing violations on main are unchanged).

## 7. Archive

- [ ] 7.1 Run `openspec archive add-rung2-hea-encoding` after
      merge so the deltas land in
      `openspec/specs/{language,compiler,verifier}/spec.md`.
