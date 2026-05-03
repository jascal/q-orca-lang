## MODIFIED Requirements

### Requirement: HEA tier-separation invariant enforcement

The verifier SHALL enforce a declared `concept_gram_tier_separation`
invariant against the analytic Gram of any HEA-encoded machine.
Specifically, when a machine declares an `## encoding` section with
`kind == "hea"` AND a `concept_gram_tier_separation` invariant in
`## invariants`, Stage 4b SHALL compute the analytic Gram via
`compute_concept_gram_hea(machine)` and evaluate the declared
inequality against the metric `tier_separation` defined as:

```
tier_separation =
    min over clusters C with |C| >= 2 of
        mean(|<c_i|c_j>|² for c_i, c_j in C, i < j)
    − max over (i, j) cross-cluster pairs of |<c_i|c_j>|²
```

Cluster membership SHALL come from the per-row `cluster` field of
the `## theta` block — rows sharing a `cluster` value form one
tier; rows with distinct values form distinct tiers. Singleton
clusters contribute no intra-cluster pairs and SHALL be ignored
by the `min`. If every cluster is a singleton, `tier_separation`
is undefined and Stage 4b SHALL emit `HEA_TIER_UNDEFINED` at error
severity.

On inequality violation, Stage 4b SHALL emit
`HEA_TIER_INVARIANT_VIOLATED` at error severity, naming the
declared bound, the actual computed `tier_separation`, and at
least one cluster pair that drives the violation.

The check SHALL be gated by the same `VerifyOptions.skip_dynamic`
flag as the existing HEA consistency check. It SHALL NOT run when
`skip_dynamic=True`.

When a machine declares `concept_gram_tier_separation` but no HEA
encoding (rung-0 or rung-1 machine, or a machine without any
`## encoding` section), Stage 4b SHALL emit
`HEA_TIER_INVARIANT_NOT_APPLICABLE` at *warning* severity — the
invariant has no Gram to evaluate against. Verification SHALL NOT
fail solely because of this warning.

#### Scenario: Tier-separation invariant satisfied

- **GIVEN** an HEA machine with three concepts grouped as `s1: a,
  b` and `s2: c`, an analytic
  Gram with intra-`s1` mean overlap 0.9999 and max cross-cluster
  overlap 0.3837, and `## invariants` declaring
  `- concept_gram_tier_separation >= 0.025`
- **WHEN** Stage 4b runs
- **THEN** the verifier emits no `HEA_TIER_*` errors
- **AND** the consistency check (`HEA_GRAM_INVALID`) is unaffected

#### Scenario: Tier-separation invariant violated

- **GIVEN** an HEA machine with the same cluster assignment but
  whose theta values produce intra-`s1` mean 0.50 and max
  cross-cluster 0.55, with
  `- concept_gram_tier_separation >= 0.025` declared
- **WHEN** Stage 4b runs
- **THEN** the verifier emits `HEA_TIER_INVARIANT_VIOLATED` at
  error severity, naming the declared bound (`>= 0.025`), the
  actual computed tier_separation (negative), and the cluster
  pair `(s1, s2)`

#### Scenario: All-singleton clusters yield HEA_TIER_UNDEFINED

- **GIVEN** an HEA machine with three concepts each in a distinct
  singleton cluster (`s1`, `s2`, `s3`) and a
  `concept_gram_tier_separation >= 0.025` invariant
- **WHEN** Stage 4b runs
- **THEN** the verifier emits `HEA_TIER_UNDEFINED` at error
  severity, explaining that no cluster has at least two members

#### Scenario: Invariant honors skip_dynamic

- **GIVEN** an HEA machine that would otherwise emit
  `HEA_TIER_INVARIANT_VIOLATED`
- **WHEN** `verify(machine, VerifyOptions(skip_dynamic=True))`
  runs
- **THEN** the verifier does NOT compute the Gram and does NOT
  emit `HEA_TIER_INVARIANT_VIOLATED`

#### Scenario: Invariant on non-HEA machine warns but does not fail

- **GIVEN** a rung-0 product-state machine with no `## encoding`
  section but whose `## invariants` mistakenly declares
  `- concept_gram_tier_separation >= 0.025`
- **WHEN** Stage 4b runs
- **THEN** the verifier emits
  `HEA_TIER_INVARIANT_NOT_APPLICABLE` at warning severity
- **AND** verification SHALL NOT fail solely because of this
  warning
