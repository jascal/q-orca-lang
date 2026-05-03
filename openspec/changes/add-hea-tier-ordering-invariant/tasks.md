# add-hea-tier-ordering-invariant — tasks

## 1. AST + parser

- [ ] 1.1 `q_orca/ast.py` — `ThetaRow` gains
      `cluster: str | None = None`
- [ ] 1.2 `q_orca/parser/markdown_parser.py` — `## theta` block
      parser accepts the optional `cluster` column; mixed-form
      blocks (some rows with cluster, some without) raise
      `QParseError` naming the offending row
- [ ] 1.3 Theta-row `cluster` value SHALL be a non-empty trimmed
      string when the column is declared; empty cells raise
      `QParseError`
- [ ] 1.4 When the cluster column is omitted on the header line,
      every row gets `cluster = "_default"` post-parse
- [ ] 1.5 `## invariants` parser accepts
      `concept_gram_tier_separation <op> <decimal>` and produces
      `Invariant(kind="resource",
      metric="concept_gram_tier_separation", op=<op>, value=<float>)`
- [ ] 1.6 Decimal value outside `[0, 1]` raises `QParseError`
      naming the offending value

## 2. Helper

- [ ] 2.1 `q_orca/compiler/concept_gram_hea.py` —
      `compute_tier_separation(gram: np.ndarray, clusters:
      list[str]) -> float | None` returns the metric value or
      `None` when every cluster is a singleton
- [ ] 2.2 `compute_tier_separation` raises `ValueError` if
      `gram.shape != (len(clusters), len(clusters))`
- [ ] 2.3 Helper is documented as public-ish (analysis utility)
      and exported from `q_orca.compiler`

## 3. Verifier

- [ ] 3.1 `q_orca/verifier/hea_encoding.py` — extend
      `check_hea_encoding` to inspect `machine.invariants` for
      `metric == "concept_gram_tier_separation"`
- [ ] 3.2 When found AND `machine.encoding.kind == "hea"`, build
      Gram + cluster list and call `compute_tier_separation`;
      evaluate the declared inequality
- [ ] 3.3 New error codes: `HEA_TIER_INVARIANT_VIOLATED`,
      `HEA_TIER_UNDEFINED`,
      `HEA_TIER_INVARIANT_NOT_APPLICABLE`
- [ ] 3.4 `HEA_TIER_INVARIANT_NOT_APPLICABLE` emitted at warning
      severity when the invariant is declared on a non-HEA
      machine
- [ ] 3.5 The whole tier-invariant evaluation is gated by
      `VerifyOptions.skip_dynamic`, mirroring the existing
      consistency check

## 4. Tests

### Parser
- [ ] 4.1 `tests/test_parser.py::TestThetaClusterColumn` — 2-col
      form, 3-col form, mixed-form rejected, empty cluster
      rejected, default cluster assignment
- [ ] 4.2 `tests/test_parser.py::TestTierSeparationInvariant` —
      every operator, decimal value, out-of-range rejection

### Compiler
- [ ] 4.3 `tests/test_compiler.py::TestComputeTierSeparation` —
      happy path on Animals-style cluster fixture; all-singleton
      returns None; shape mismatch raises ValueError;
      single-cluster (every concept in one cluster) returns
      undefined-via-None as well

### Verifier
- [ ] 4.4 `tests/test_verifier.py::TestHeaTierOrderingInvariant`
      — declared invariant satisfied (no errors); declared
      invariant violated (HEA_TIER_INVARIANT_VIOLATED with
      cluster-pair attribution); all-singleton machine with
      invariant (HEA_TIER_UNDEFINED); skip_dynamic gate honored;
      non-HEA machine with invariant
      (HEA_TIER_INVARIANT_NOT_APPLICABLE warning, verification
      passes)

### Examples
- [ ] 4.5 `tests/test_examples.py::test_larql_hea_minimal_pipeline`
      extended to assert the parsed machine has
      `concept_gram_tier_separation >= 0.025` invariant and that
      it verifies clean

## 5. Example

- [ ] 5.1 `examples/larql-hea-minimal.q.orca.md` — `## theta`
      gains the `cluster` column (rows: `a → s1`, `b → s1`,
      `c → s2`)
- [ ] 5.2 New `## invariants` section in the same example
      declares `- concept_gram_tier_separation >= 0.025`
- [ ] 5.3 Example prose updated to point at the declarative
      invariant rather than the implicit constant

## 6. Docs / packaging

- [ ] 6.1 `CHANGELOG.md` — `0.9.0 (2026-05-XX)` section: theta
      cluster column, `concept_gram_tier_separation` invariant,
      Stage 4b enforcement
- [ ] 6.2 `q_orca/__init__.py` — `__version__ = "0.9.0"`
- [ ] 6.3 `README.md` — invariants section gains an HEA tier-
      separation example; HEA encoding bullet links to the
      invariant grammar

## 7. Validate + commit

- [ ] 7.1 `openspec validate add-hea-tier-ordering-invariant
      --strict` ✓
- [ ] 7.2 Full pytest suite green; ruff clean
- [ ] 7.3 Commit + push, open PR, merge after review

## 8. Archive

- [ ] 8.1 `openspec archive add-hea-tier-ordering-invariant`
      after merge — populate the new requirements into
      `openspec/specs/{language,verifier}/spec.md`
