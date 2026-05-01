## Why

The just-archived `add-mps-concept-encoding` change (PR #46) shipped
`examples/larql-polysemantic-hierarchical.q.orca.md` as the rung-1
example demonstrating that an entangled (bond-2 MPS) concept
encoding produces a graded four-tier Gram matrix that the rung-0
product-state encoding cannot. The proposal's design rationale
(`openspec/changes/add-mps-concept-encoding/design.md:9-12`) and the
ladder framing in
`docs/research/polysemantic-encoding-beyond-product-states.md:124-128`
both rest on the claim that the MPS lift escapes the factorized
overlap formula `⟨c_i | c_j⟩ = ∏_k cos((θ_{i,k} − θ_{j,k})/2)` —
"The moment you leave [product states], that factorization dies."

That claim is mathematically false for the shipped encoding.
Numerical verification on the example's exact 12 angles **and** on
arbitrary random angles produces

    max |gram_mps[i,j] − gram_prod_state[i,j]| ≈ 1.1e-16

— machine epsilon — where `gram_prod_state` is the Gram of the
product-state encoding `|c⟩ = Ry(q0,α)·Ry(q1,β)·Ry(q2,γ)|000⟩` with
the same angle triples. The Ry-CNOT-Ry-CNOT-Ry staircase on the
`|000⟩` vacuum produces a state with Schmidt rank 2 across both
bipartitions (so it IS genuinely entangled), but the inner product
factorizes anyway as

    ⟨c_i | c_j⟩ = cos((α_i − α_j)/2)
                · cos((β_i − β_j)/2)
                · cos((γ_i − γ_j)/2)

— identical to the rung-0 closed form. The four-tier signature
emerges entirely from the angle design (cyclic α at 2π/3 spacing →
cos²(π/3) = 0.25 cross-group floor; β = ±0.75 → super-sib ≈ 0.535;
γ = ±0.35 → sub-mate ≈ 0.882), not from the bond-2 lift. A plain
product-state encoding with the same 12 (α,β,γ) triples reproduces
the exact same four-tier signature.

The verifier didn't catch this because the existing tests check
that the Gram has four ordered tiers — true under the broken
encoding because the angle design produces them — and that the
implementation matches its own analytic prediction. None of the
existing checks test the *conceptual* claim that MPS encoding is
necessary for the hierarchy.

This change replaces the encoding with one whose Gram **genuinely
depends on the entanglement structure** (i.e., differs measurably
from any product-state encoding with the same parameter count) and
propagates the corrected framing through the example, demo, README,
design doc, and research note. Three encoding variants have been
numerically validated as breaking the factorization while preserving
a Schmidt-rank-2 register; the change picks one in task 1 and
re-derives the analytic tier bands.

(Source: external code review of PR #46, 2026-05-01; numerical
verification logged in
`docs/research/polysemantic-encoding-beyond-product-states.md` task
6 of this change.)

## What Changes

**Encoding swap in
`examples/larql-polysemantic-hierarchical.q.orca.md`:**

- Replace the `prepare_concept(a, b, c)` and `query_concept(a, b, c)`
  effects with one of the candidate encodings validated in task 1.
  Recommended primary candidate (lowest framing churn):

      prepare: Ry(qs[0], a)
             ; CNOT(qs[0], qs[1])
             ; Ry(qs[1], a + b)
             ; CNOT(qs[1], qs[2])
             ; Ry(qs[2], b + c)

  Each angle still has a "primary" qubit (α→q0, β→q1, γ→q2) but
  also influences the chain neighbour, breaking the cross-amplitude
  cancellation that produces the factorization. Numerical check:
  `max ||gram|² − |gram_prod|²| ≈ 0.32` for arbitrary angles, vs.
  ≈ 1.1e-16 today. (See task 1 for two alternative candidates that
  also break factorization but with different hierarchy semantics.)

- The query effect remains the exact inverse of the prepare effect
  (gate order reversed, angle signs negated, CNOTs self-inverse) —
  the same invariant the spec already requires.

- Re-derive the four analytic tier bands for the new encoding and
  update the example's leading paragraph + tier table + ASCII
  heatmap to match. The 12-concept (α, β, γ) triples may need
  adjustment to land cleanly within the new bands; task 1 includes
  the angle-design pass.

**Compiler helper update in
`q_orca/compiler/concept_gram_mps.py`:**

- The current helper accepts effect strings matching the strict
  `Ry; CNOT; Ry; CNOT; Ry` staircase pattern. The new encoding may
  break that pattern check (e.g., it has identical structure but
  the angle-binding for the second and third Ry slots becomes a
  sum rather than a single bound argument). Two sub-options, picked
  in task 2:
    - **2a (preferred).** Generalize the effect-shape detector to
      accept "Ry(qs[k], <angle-expression>)" where the angle
      expression is a linear combination of the action's angle
      parameters. Generalize the per-call-site evaluator to
      substitute the bound arguments into the linear combination
      before contracting. This lets the helper handle the
      cross-coupled encoding without further hardcoding.
    - **2b (fallback).** Keep the helper hardcoded to the
      strict-staircase shape and add a sibling helper
      `compute_concept_gram_mps_xcoupled` for the cross-coupled
      pattern. More files, less reuse.

- Either way, retain the existing `MpsGramConfigurationError`
  shape; the error catalog grows by at most one entry
  (UNRECOGNIZED_ANGLE_EXPRESSION or similar) under 2a.

**Test re-pinning:**

- `tests/test_examples.py::test_larql_polysemantic_hierarchical_pipeline`
  — re-pin the four-tier band assertions to the new (re-derived)
  bands. Add an assertion that the Gram **differs** from the
  same-angle product-state Gram by at least 0.05 on at least one
  off-diagonal entry, so a future encoding regression that silently
  re-introduces factorization is caught.
- `tests/test_compiler.py::TestComputeConceptGramMps` — extend to
  cover the generalized angle-expression input (under 2a) or the
  new sibling helper (under 2b).

**Demo update — `demos/larql_polysemantic_hierarchical/demo.py`:**

- §3 (analytic Gram heatmap) and §6 (rung-0 vs. rung-1 recap)
  re-pinned to the new bands.
- §6 narrative reworded: drop "the CNOT staircase entangles
  adjacent qubits, lifting the block diagonal of rung-0 into a
  graded two-level hierarchy" (which is true of the new encoding
  but *was* false of the old one). New wording grounds the
  hierarchy in the cross-coupled angle structure, with the bond-2
  register as a prerequisite for the structure but not its sole
  cause.

**Documentation and design corrections:**

- `README.md` "Hierarchical polysemy" section (~lines 591-606):
  reword so the rung-1 → graded-hierarchy claim accurately
  describes the new encoding, and explicitly note that the
  particular Ry-CNOT-Ry-CNOT-Ry-on-vacuum staircase factorizes —
  this is the surprising mathematical fact this change documents.
- `openspec/changes/add-mps-concept-encoding/design.md` (the
  archived design) — add a short post-mortem section pointing at
  this change. Do **not** rewrite the archived design; archived
  changes are a record. The post-mortem footnote is what links the
  archived claim to the corrected version.
- `docs/research/polysemantic-encoding-beyond-product-states.md` —
  insert a "Caveat: Schmidt rank > 1 ≠ non-factorized overlap" box
  near the factorization formula (lines 124-128), citing the
  Ry-CNOT staircase as the canonical counter-example. Update the
  rung-1 entry to reflect that *some* bond-2 encodings still
  factorize, and the rung-1 example uses a cross-coupled variant
  that doesn't.

**Tech-debt cross-reference:**

- Mark §5.6 in `openspec/changes/tech-debt-backlog/tasks.md`
  (verifier blind spot: exhaustive syndrome coverage) with a
  cross-link to a new tech-debt item: "verifier blind spot — Gram
  factorization vs. encoding entanglement." A future verifier rule
  could flag any encoding whose Gram matches the same-angle
  product-state Gram, surfacing this class of bug at verify time.

## Capabilities

### New Capabilities
None directly — this change rectifies the existing rung-1 example
to actually demonstrate non-factorized overlap, which the
language-spec requirement already calls for in spirit. The new
behavior the verifier could check is filed as tech-debt, not
shipped here.

### Modified Capabilities

- `language`: the **MPS Concept Encoding Spec** requirement (added
  by `add-mps-concept-encoding`) is sharpened. Today it requires
  "MPS (bond-dim-2) concept encoding" via the strict staircase
  shape; the modification requires that the encoding's Gram matrix
  **differ measurably from the same-angle product-state Gram**, so
  the spec rules out the silently-factorizing-staircase failure
  mode. The strict-staircase shape is no longer the canonical
  requirement; the canonical requirement becomes "a bond-2 MPS
  encoding whose Gram is non-factorized." The strict staircase
  remains a permitted shape for *future* examples that document the
  factorization explicitly as a teaching point.

- `compiler`: `compute_concept_gram_mps` either generalizes its
  effect-shape detector to accept linear-combination angle
  expressions (option 2a, preferred) or grows a sibling helper
  (option 2b). The currently-shipped public API
  (`compute_concept_gram_mps(machine, ...)`) remains backward-
  compatible; under 2a it handles strictly more inputs.

## Impact

- `examples/larql-polysemantic-hierarchical.q.orca.md` — rewrite
  the encoding section + tier table + heatmap. ~80 lines changed
  (the structural skeleton stays).
- `q_orca/compiler/concept_gram_mps.py` — under 2a, generalize the
  effect-shape detector and per-call-site evaluator. ~50 lines
  changed; under 2b, ~120 lines added in a sibling file. 2a
  preferred.
- `tests/test_examples.py` — re-pin the pipeline test bands; add
  a non-factorization assertion. ~30 lines.
- `tests/test_compiler.py` — extend `TestComputeConceptGramMps` to
  cover the generalized input shape. ~40 lines.
- `demos/larql_polysemantic_hierarchical/demo.py` — re-pin §3 and
  reword §6. ~30 lines.
- `README.md` — reword the "Hierarchical polysemy" section. ~15
  lines.
- `docs/research/polysemantic-encoding-beyond-product-states.md` —
  insert a caveat box; reword rung-1 entry. ~25 lines.
- `openspec/changes/add-mps-concept-encoding/design.md` — append a
  post-mortem footnote pointing at this change. ~10 lines.
- `openspec/changes/tech-debt-backlog/tasks.md` — add a verifier-
  blind-spot tech-debt entry under §5. ~12 lines.
- No new runtime dependency. No grammar changes. No verifier rule
  changes (the new check is filed as tech-debt for a follow-up
  change to add).

## Non-Goals

- **No retroactive rewrite of the archived
  `add-mps-concept-encoding` change.** The archived proposal,
  design, and tasks documents stay unchanged as a historical
  record; the post-mortem footnote in the archived design.md is
  the only edit to archived content, and it's purely a forward-
  link.
- **No new verifier rule** that flags Gram factorization at verify
  time. That rule would be the principled fix for the class of
  bug this change patches; it's filed as tech-debt §5.7 (added by
  this change) and gated behind a separate, focused proposal once
  there's a second example whose factorization status is non-
  obvious.
- **No re-architecture of the rung ladder.** The
  `polysemantic-encoding-beyond-product-states.md` rung structure
  (rung 0 = product, rung 1 = MPS, rung 2 = HEA, rung 3 =
  stabilizer) stays. The caveat note clarifies that rung
  membership is about the encoding *manifold*, not automatically
  about whether the Gram is factorized — those two properties came
  apart for the shipped staircase.
- **No second hierarchical example.** This change fixes the
  shipped one in place. A second variant exploring brick-wall or
  tree CNOT topologies remains an open research question, scoped
  under future proposals as in the original change.
- **No change to `larql-polysemantic-clusters.q.orca.md`** (rung 0)
  or any other shipped example. The bug is localized to the
  hierarchical example and its surrounding docs.
