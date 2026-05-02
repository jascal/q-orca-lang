# Design: Fix MPS Encoding Factorization

## Context

The just-archived `add-mps-concept-encoding` change (PR #46) shipped
the rung-1 hierarchical-polysemy example with this preparation:

    |c⟩ = Ry(q0, α) · CNOT(q0, q1) · Ry(q1, β) · CNOT(q1, q2)
        · Ry(q2, γ) · |000⟩

This state has Schmidt rank 2 across both bipartitions (q0 | q1q2 and
q0q1 | q2), so it is genuinely entangled and is a valid bond-2 MPS.
The shipped framing — example leading paragraph, design.md §1, demo
§6 narrative, README "Hierarchical polysemy" section, and the
research note's claim that "the moment you leave [product states],
that factorization dies" — all assert that the entanglement is what
*produces* the four-tier Gram structure, in contrast with rung 0
(product-state) which is locked to a single tier per coordinate.

That assertion is mathematically false for this particular staircase.
Numerical contraction on the example's exact 12 angles **and** on
arbitrary random angles produces

    max |gram_mps[i,j] − gram_prod_state[i,j]| ≈ 1.1e-16

— machine epsilon — where `gram_prod_state` is the Gram of the
product-state encoding `Ry(q0, α) · Ry(q1, β) · Ry(q2, γ) · |000⟩`
with the same angles. Concretely:

    ⟨c_i | c_j⟩ = cos((α_i − α_j)/2)
                · cos((β_i − β_j)/2)
                · cos((γ_i − γ_j)/2)

— the rung-0 closed form. The shipped four-tier signature comes
entirely from the angle design (cyclic α at 2π/3 spacing → cos²(π/3)
= 0.25 cross-group floor; β = ±0.75 → super-sib ≈ 0.535; γ = ±0.35 →
sub-mate ≈ 0.882), not from the bond-2 lift. A plain product-state
encoding with the same 12 (α, β, γ) triples reproduces the exact
same four-tier signature.

## Why this particular staircase factorizes

The `|0…0⟩` vacuum is a CNOT eigenstate (well, conditional eigenstate
through the chain): each `CNOT(qs[k], qs[k+1])` applied right after a
`Ry(qs[k], _)` produces a state whose inner product with another
same-shape state simplifies. For a 2-qubit cell:

    ⟨0| Ry(q0, α') † · CNOT · Ry(q1, β') † · Ry(q1, β) · CNOT · Ry(q0, α) |0⟩

cancels the inner CNOT pair (CNOT² = I) and the outer
`Ry(q1, −β')·Ry(q1, β) = Ry(q1, β−β')` decouples into a product over
q0 and q1 because the conditional structure of CNOT only matters
when the control qubit's amplitudes differ between the two states —
and they don't, after the outer Ry's recombine. The argument extends
inductively along the chain. The result is the factorized closed
form above.

Schmidt rank > 1 says the **single state** is non-product. The Gram
entry ⟨c_i | c_j⟩ asks something different: does the **inner-product
functional** factorize over qubits? For this staircase, yes — even
though each individual state is entangled.

The conceptual lesson, recorded in the research-note caveat box that
this change adds:

> Schmidt rank > 1 (the encoding manifold is genuinely non-product)
> is **not** the same condition as the inner-product map being
> non-factorized. Whether the Gram factorizes depends on the
> *interference structure* of how the encoding maps angles to
> amplitudes, not on whether the resulting states are entangled.

Once you see this, the fix is structural: the encoding has to mix
each angle parameter into more than one qubit's amplitude, so that
the `cos((θ_i − θ_j)/2)` factorization cannot form on a per-qubit
basis. CNOTs alone don't do that — Ry rotations on multiple qubits
sharing the same angle parameter do.

## Alternatives considered

Three encoding variants were numerically validated as breaking
factorization while preserving Schmidt rank 2 and the (qs, α, β, γ)
parametric-action signature. For each, the metric is

    diff := max_{i,j} | |gram_new[i,j]|² − |gram_prod[i,j]|² |

over 1000 randomly-sampled angle triples per concept (12 concepts),
where `gram_prod` is the product-state encoding `Ry(q0,α)·Ry(q1,β)·
Ry(q2,γ)·|000⟩`. A diff at machine-epsilon means the new encoding
factorizes; a diff well above 1e-3 means it does not.

### Alternative A (recommended): cross-coupled-by-sum

    |c⟩ = Ry(q0, α)
        · CNOT(q0, q1)
        · Ry(q1, α + β)
        · CNOT(q1, q2)
        · Ry(q2, β + γ)
        · |000⟩

Each angle still has a "primary" qubit (α → q0, β → q1, γ → q2) but
α also influences q1 and β also influences q2. The chain-locality
intuition that motivated the q0/q1/q2 → super/sub/concept mapping
in the archived design.md still holds approximately: q0 is dominated
by α (the only angle that touches it), q2 is dominated by γ-via-β
(through both the β+γ rotation and the q1-via-CNOT correlation),
and q1 sits in the middle.

- **diff: ≈ 0.32** (well above the 1e-3 floor)
- Preserves the (qs, α, β, γ) parametric signature exactly.
- Preserves the staircase gate sequence — only the angle expressions
  bound to the second and third Ry change.
- Compiler helper update (option 2a) is local: extend the
  effect-shape detector from "Ry(qs[k], <bound-param>)" to
  "Ry(qs[k], <linear combination of bound params>)". The CNOT
  pattern is unchanged.
- The four-tier hierarchy targeted by the archived design needs a
  fresh angle-design pass (task 1), but the same partition shape (3
  super-groups × 2 sub-clusters × 2 concepts) is reachable.

### Alternative B: brick-wall topology

    |c⟩ = Ry(q0, α) · Ry(q1, β) · Ry(q2, γ)
        · CNOT(q0, q1) · CNOT(q1, q2) · CNOT(q0, q1)
        · |000⟩

Same number of CNOTs (three, instead of two) and a different
adjacency pattern. Numerically:

- **diff: ≈ 0.52** — strongest factorization break of the three.
- Compiler helper update is non-local: the staircase-shape detector
  is the wrong abstraction; brick-wall would need a separate
  detector or a fully-general MPS evaluator.
- The four-tier hierarchy mapping onto super/sub/concept becomes
  *less* clean: q0–q1–q0 brick layering means q0 and q2 are
  symmetric, undermining the "α = super-group, γ = concept" reading.

Rejected as primary because the helper rewrite is much larger and
the conceptual hierarchy becomes muddier. Filed in the research
note's "open questions" as a future-rung-1 variant proposal once a
second hierarchical example is needed (e.g., for benchmarking
topology-vs.-tier-shape tradeoffs).

### Alternative C: γ-cross-coupled (minimal extension of the bug fix)

    |c⟩ = Ry(q0, α) · CNOT(q0, q1) · Ry(q1, β) · CNOT(q1, q2)
        · Ry(q2, β + γ) · |000⟩

Same as the shipped staircase except that the final Ry's angle
becomes `β + γ` instead of just `γ`. The conceptual change is
minimal — only γ's angle parameter is "leaked" into a different
qubit (via the β term), and only on q2.

- **diff: ≈ 0.25** — clearly above the factorization floor but
  smaller than A.
- Compiler helper update under option 2a is the same as for A
  (linear-combination angle expressions); no extra work.
- The four-tier hierarchy mapping is the cleanest of the three: α
  → super-group (touches only q0), β → sub-cluster (touches q1
  and q2), γ → concept (touches only q2 via the leaked term).

Rejected as primary because the cross-coupling is asymmetric —
α stays "pure" on q0 while γ is impure on q2 — which produces a
slight tier-asymmetry the demo would have to caveat. A is more
symmetric: the asymmetry between α / β / γ comes only from chain
position, not from differential cross-coupling. C is the **fallback**
if the angle-design pass for A turns out to give un-clean tier
bands; the helper change is identical so the cost of switching
from A to C late is one effect string.

## Recommended primary path

Alternative A: cross-coupled-by-sum. Rationale:

1. **Symmetric cross-coupling**: each angle parameter (α, β, γ)
   reaches exactly one chain neighbour through a sum, giving a
   chain-symmetric structure that maps cleanly onto super/sub/concept
   via chain position alone.
2. **Lowest framing churn**: the gate sequence is unchanged, the
   parametric-action signature is unchanged, only the second and
   third Ry's angle expressions become sums rather than single bound
   args.
3. **Compiler helper rewrite is small**: option 2a (generalize the
   effect-shape detector to accept linear-combination angle
   expressions) is the right shape for any future cross-coupled
   variant; the rewrite cost is ~50 lines and the public API is
   unchanged.
4. **Clear non-factorization**: diff ≈ 0.32 is large enough that the
   non-factorization assertion in the test (≥ 0.05 on at least one
   off-diagonal) is satisfied with broad margin, and broad enough to
   stay satisfied under any reasonable angle-design tweak in task 1.

## Tier band design (re-derived for the new encoding)

The archived design.md §3 derived tier bands from the factorized
formula. With cross-coupled angles, that closed form no longer
applies; tier bands have to be measured numerically over an angle
trial-design.

Target structure (same as the archived target, since the goal of the
example is unchanged):

| tier | definition | target `\|⟨c_i\|c_j⟩\|²` band |
|---|---|---|
| self | `i = j` | 1.0 |
| sub-cluster-mate | same α, same β, different γ | 0.85 – 0.90 |
| super-group-sibling | same α, different β | 0.45 – 0.60 |
| cross-group | different α | < 0.25 |

The cross-group band loosens slightly from `< 0.15` to `< 0.25`
because the cross-coupling pushes some cross-group pairs above the
clean cyclic-α floor. The "four ordered tiers with strict inter-tier
separation" guarantee — which is what the pipeline test actually
asserts — still holds with comfortable gaps under any angle design
that puts α on a 3-cyclic group, β at ±0.75, and γ at ±0.35. The
exact post-task-1 numerical bands replace these targets in the
shipped example, demo, and test.

## Compiler helper update: option 2a vs option 2b

### Option 2a (recommended): generalize the effect-shape detector

`q_orca/compiler/concept_gram_mps.py` today uses a single-segment
regex `_RY_SEGMENT_RE` that matches `Ry(qs[k], <var>)` where `<var>`
is a single bound parameter name. The `_parse_staircase_effect`
helper walks segments and, on each Ry segment, asserts that the
captured `<var>` matches the expected positional angle parameter.

The change:

1. Generalize `_RY_SEGMENT_RE` (or replace it with a small helper)
   to capture the entire angle expression as a string, not just a
   single identifier. Whitespace-tolerant `(...)`, `+`, `-`, and
   identifier tokens.
2. Replace the equality check between the captured identifier and
   the expected positional parameter with a *linear-combination*
   parser: parse the angle expression into a list of `(coefficient,
   parameter_name)` pairs (e.g., `α + β` → `[(1, "α"), (1, "β")]`).
   At call-site evaluation, substitute the bound argument values and
   evaluate the linear combination to a float.
3. Surface a new structured error `MpsGramConfigurationError(kind=
   "unrecognized_angle_expression")` when the angle expression is
   neither a bound parameter nor a linear combination of them.

The CNOT pattern matcher and the staircase walker are unchanged.
Public API is unchanged.

Cost: ~50 lines changed, two new error-path tests in
`TestComputeConceptGramMps`.

### Option 2b (fallback): sibling helper

Keep `compute_concept_gram_mps` hardcoded to the strict
single-bound-param staircase shape. Add a sibling
`compute_concept_gram_mps_xcoupled(machine, ...)` that handles the
cross-coupled pattern (and only the cross-coupled pattern).

Cost: ~120 lines added in a sibling file, near-total duplication of
the staircase walker, the call-site enumeration logic, and the
inner-product computation. Two helpers to test, document, and
maintain.

Rejected as primary because option 2a is the natural generalization
the helper *should have shipped with*. The single-bound-param
restriction was an over-fit to the broken example.

## Naming

- Change ID: `fix-mps-encoding-non-factorizing`. Names what the
  change fixes (the factorization bug) and the property the new
  encoding satisfies (non-factorized Gram).
- Encoding: no new name. The recommended encoding is still a
  bond-2 MPS via CNOT-staircase; the only change is that two of the
  three Ry angles become linear combinations of two parameters
  instead of single parameters. Calling it "cross-coupled MPS" is
  fine in the demo narrative but isn't a new technical term.

## Post-mortem entry in archived design

Per OpenSpec convention, archived changes are immutable history.
The archived `add-mps-concept-encoding/design.md` gets a single
short post-mortem section appended (8–10 lines) at the end:

```
## Post-mortem (added 2026-05-01)

The staircase encoding shipped in this change has Schmidt rank 2
but its Gram still factorizes as
⟨c_i | c_j⟩ = ∏_k cos((θ_{i,k} − θ_{j,k})/2). The four-tier
signature emerges from the angle design, not the entanglement.
The example, helper, demo, and docs are corrected in the
follow-up change `fix-mps-encoding-non-factorizing`.
```

This is the only edit to archived content. The rest of the
post-mortem narrative (the math of why the staircase factorizes,
the alternatives considered, the recommended fix) lives in this
change's design.md and stays here, because *this* change is the
record of the fix.

## Open questions

- **Should the test assert exact tier bands or just tier ordering
  + non-factorization?** The archived test asserts both (bands
  within numerical tolerance + ordering). With the cross-coupled
  encoding, exact bands are angle-design-dependent and the tier-A
  → C choice may shift them. Initial plan (task 1.4): fix bands at
  the post-task-1 numerical values and assert them exactly with
  `1e-6` tolerance, parallel to the archived test. If the angle
  design produces noisy bands, fall back to ordering + per-tier
  spread checks. Decide during task 1.

- **Should the helper still call out the strict-staircase shape
  in its error messages?** The strict staircase is no longer the
  required shape for the canonical example, but it remains a
  *valid* shape for future examples that want to document
  factorization explicitly. Initial plan: helper accepts both
  shapes (single-param Ry and linear-combination Ry); the spec
  delta clarifies which one the canonical example uses. Error
  messages reference the more general "linear combination of bound
  angle parameters" shape.

- **Should we add a verifier rule that flags Gram factorization
  matching same-angle product-state Gram?** The principled fix for
  the class of bug this change patches. Filed as tech-debt §5.7
  (added by this change), gated behind a separate proposal once a
  second concrete example exists where the factorization status
  is non-obvious. Out of scope for this change.
