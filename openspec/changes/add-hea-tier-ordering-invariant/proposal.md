## Why

`add-rung2-hea-encoding` shipped a Stage 4b consistency check that
proves the HEA encoding declaration, the `## theta` block, and the
transitions table are mutually consistent — but the spec deferred
tier-ordering enforcement to a follow-up proposal that defines an
invariant grammar. As a result `HEA_TIER_TOLERANCE = 0.025` is
exported as a module-level constant nobody reads.

Today a user writing an HEA-encoded machine can prove "the encoding
is internally consistent and statevectors build cleanly" but has no
declarative way to claim "this dictionary's intra-cluster overlaps
are at least 0.025 above its inter-cluster overlaps" — the
load-bearing claim that distinguishes a structured polysemantic
encoding from a random one. Today that claim lives in example
prose ("sub→cross gap: 0.6162 — well above the Stage 4b consistency
tolerance") and ad-hoc test scripts; it is not a verified property
of the machine.

This change adds:

1. A `cluster` column to the `## theta` block grammar (optional —
   omitting it preserves today's behavior). The cluster label is the
   declarative tier annotation: rows sharing a `cluster` value form
   one tier; rows with distinct values form distinct tiers.
2. A new resource-form invariant
   `concept_gram_tier_separation <op> <number>` that the verifier
   evaluates against the analytic Gram for HEA-encoded machines.
3. Verifier wiring so Stage 4b reads `concept_gram_tier_separation`
   invariants against the Gram returned by
   `compute_concept_gram_hea`. `HEA_TIER_TOLERANCE` remains the
   recommended-default tolerance (still exposed as a module-level
   constant) but the invariant value is whatever the machine
   declares.

After this change, a researcher can write
`- concept_gram_tier_separation >= 0.025` in `## invariants` and
have the verifier reject the machine if its analytic Gram doesn't
clear that separation. The follow-up referenced in
`add-rung2-hea-encoding` is closed.

## What Changes

- **MODIFIED** `language` capability:
  - `## theta` block grammar accepts an optional `cluster` column.
    When present, every row's `cluster` value SHALL be a non-empty
    string. Rows omitting the column (or all rows, in a
    column-less theta) SHALL be treated as belonging to a single
    implicit cluster `_default`.
  - `## invariants` accepts a new resource-form bullet:
    `concept_gram_tier_separation <op> <decimal>`, where `<op>`
    is one of `<=`, `<`, `==`, `>=`, `>` and `<decimal>` is a
    real number in `[0, 1]`. Parsed into
    `Invariant(kind="resource",
    metric="concept_gram_tier_separation", op=<op>, value=<float>)`.

- **MODIFIED** `verifier` capability:
  - When a machine declares an `## encoding` section with
    `kind == "hea"` AND a `concept_gram_tier_separation`
    invariant in `## invariants`, Stage 4b SHALL compute the
    Gram via `compute_concept_gram_hea(machine)` and evaluate
    the declared inequality against the analytic
    `tier_separation` metric defined as:
    ```
    tier_separation =
        min over clusters C with |C| >= 2 of
            mean(|<c_i|c_j>|² for c_i, c_j in C, i < j)
        − max over (i, j) cross-cluster pairs of |<c_i|c_j>|²
    ```
    Singleton clusters contribute no intra-cluster pairs and are
    ignored by the `min`. If every cluster is a singleton (no
    intra-cluster pairs anywhere), `tier_separation` is undefined
    and the verifier SHALL emit a Stage 4b error with code
    `HEA_TIER_UNDEFINED`.
  - On inequality violation, Stage 4b SHALL emit a Stage 4b error
    with code `HEA_TIER_INVARIANT_VIOLATED` naming the declared
    bound, the actual computed `tier_separation`, and the
    cluster pair driving the violation.
  - The check SHALL be gated by the same
    `VerifyOptions.skip_dynamic` flag as the existing HEA
    consistency check. It SHALL NOT run when `skip_dynamic=True`.
  - When a machine declares the invariant but no HEA encoding
    (e.g., a rung-0 product-state machine), the verifier SHALL
    emit `HEA_TIER_INVARIANT_NOT_APPLICABLE` at *warning*
    severity — the invariant has no Gram to evaluate against.

## Capabilities

### Modified Capabilities

- `language` — `## theta` gains optional `cluster` column;
  `## invariants` accepts `concept_gram_tier_separation` form
- `verifier` — Stage 4b evaluates
  `concept_gram_tier_separation` invariants against the analytic
  HEA Gram

## Impact

- `q_orca/ast.py` — `ThetaRow` gains optional `cluster: str | None`
  field
- `q_orca/parser/markdown_parser.py` — `## theta` accepts the
  3-column form; `## invariants` parser learns the new metric name
- `q_orca/compiler/concept_gram_hea.py` — `compute_concept_gram_hea`
  surface unchanged; new helper `_compute_tier_separation(gram,
  clusters)` reused by the verifier and tests
- `q_orca/verifier/hea_encoding.py` — `check_hea_encoding` extended
  to read `concept_gram_tier_separation` invariants and dispatch
  to the new helper; gains `HEA_TIER_INVARIANT_VIOLATED`,
  `HEA_TIER_UNDEFINED`, and
  `HEA_TIER_INVARIANT_NOT_APPLICABLE` codes
- `examples/larql-hea-minimal.q.orca.md` — gains `cluster` column
  and a `## invariants` section declaring the tier separation; the
  example now demonstrates the closed-loop check
- Tests across `tests/test_parser.py`, `tests/test_compiler.py`,
  `tests/test_verifier.py`, `tests/test_examples.py`
- `CHANGELOG.md`, `README.md`, version bump to 0.9.0

No breaking changes for files that don't declare a `cluster`
column or `concept_gram_tier_separation` invariant — current
HEA examples continue to verify under the consistency-only check.
