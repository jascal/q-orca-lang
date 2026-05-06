# add-hea-tier-ordering-invariant — tasks

## 1. AST + parser

- [x] 1.1 `q_orca/ast.py` — `ThetaRow` gains
      `cluster: str | None = None`
- [x] 1.2 `q_orca/parser/markdown_parser.py` — `## theta` block
      parser accepts the optional `cluster` column; mixed-form
      blocks (some rows with cluster, some without) raise
      `QParseError` naming the offending row
- [x] 1.3 Theta-row `cluster` value SHALL be a non-empty trimmed
      string when the column is declared; empty cells raise
      `QParseError`
- [x] 1.4 When the cluster column is omitted on the header line,
      every row gets `cluster = "_default"` post-parse
- [x] 1.5 `## invariants` parser accepts
      `concept_gram_tier_separation <op> <decimal>` and produces
      `Invariant(kind="resource",
      metric="concept_gram_tier_separation", op=<op>, value=<float>)`
- [x] 1.6 Decimal value outside `[0, 1]` raises `QParseError`
      naming the offending value

## 2. Helper

- [x] 2.1 `q_orca/compiler/concept_gram_hea.py` —
      `compute_tier_separation(gram: np.ndarray, clusters:
      list[str]) -> float | None` returns the metric value or
      `None` when every cluster is a singleton
- [x] 2.2 `compute_tier_separation` raises `ValueError` if
      `gram.shape != (len(clusters), len(clusters))`
- [x] 2.3 Helper is documented as public-ish (analysis utility)
      and exported from `q_orca.compiler`

## 3. Verifier

- [x] 3.1 `q_orca/verifier/hea_encoding.py` — extend
      `check_hea_encoding` to inspect `machine.invariants` for
      `metric == "concept_gram_tier_separation"`
- [x] 3.2 When found AND `machine.encoding.kind == "hea"`, build
      Gram + cluster list and call `compute_tier_separation`;
      evaluate the declared inequality
- [x] 3.3 New error codes: `HEA_TIER_INVARIANT_VIOLATED`,
      `HEA_TIER_UNDEFINED`,
      `HEA_TIER_INVARIANT_NOT_APPLICABLE`
- [x] 3.4 `HEA_TIER_INVARIANT_NOT_APPLICABLE` emitted at warning
      severity when the invariant is declared on a non-HEA
      machine
- [x] 3.5 The whole tier-invariant evaluation is gated by
      `VerifyOptions.skip_dynamic`, mirroring the existing
      consistency check

## 4. Tests

### Parser
- [x] 4.1 `tests/test_parser.py::TestThetaClusterColumn` — 2-col
      form, 3-col form, mixed-form rejected, empty cluster
      rejected, default cluster assignment
- [x] 4.2 `tests/test_parser.py::TestTierSeparationInvariant` —
      every operator, decimal value, out-of-range rejection

### Compiler
- [x] 4.3 `tests/test_compiler.py::TestComputeTierSeparation` —
      happy path on Animals-style cluster fixture; all-singleton
      returns None; shape mismatch raises ValueError;
      single-cluster (every concept in one cluster) returns
      undefined-via-None as well

### Verifier
- [x] 4.4 `tests/test_verifier.py::TestHeaTierOrderingInvariant`
      — declared invariant satisfied (no errors); declared
      invariant violated (HEA_TIER_INVARIANT_VIOLATED with
      cluster-pair attribution); all-singleton machine with
      invariant (HEA_TIER_UNDEFINED); skip_dynamic gate honored;
      non-HEA machine with invariant
      (HEA_TIER_INVARIANT_NOT_APPLICABLE warning, verification
      passes)

### Examples
- [x] 4.5 `tests/test_examples.py::test_larql_hea_minimal_pipeline`
      extended to assert the parsed machine has
      `concept_gram_tier_separation >= 0.025` invariant and that
      it verifies clean

## 5. Example

- [x] 5.1 `examples/larql-hea-minimal.q.orca.md` — `## theta`
      gains the `cluster` column (rows: `a → s1`, `b → s1`,
      `c → s2`)
- [x] 5.2 New `## invariants` section in the same example
      declares `- concept_gram_tier_separation >= 0.025`
- [x] 5.3 Example prose updated to point at the declarative
      invariant rather than the implicit constant

## 6. Docs / packaging

- [x] 6.1 `CHANGELOG.md` — `0.9.0 (2026-05-XX)` section: theta
      cluster column, `concept_gram_tier_separation` invariant,
      Stage 4b enforcement
- [x] 6.2 `q_orca/__init__.py` — `__version__ = "0.9.0"`
- [x] 6.3 `README.md` — invariants section gains an HEA tier-
      separation example; HEA encoding bullet links to the
      invariant grammar

## 7. Validate + commit

- [x] 7.1 `openspec validate add-hea-tier-ordering-invariant
      --strict` ✓
- [x] 7.2 Full pytest suite green; ruff clean
- [x] 7.3 Commit + push, open PR, merge after review.
      (Shipped as PR #57 → `642dc1f`.)

## 8. Archive

- [x] 8.1 `openspec archive add-hea-tier-ordering-invariant`
      after merge — populate the new requirements into
      `openspec/specs/{language,verifier}/spec.md`
