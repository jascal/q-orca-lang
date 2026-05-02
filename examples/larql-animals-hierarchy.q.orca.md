# machine LarqlAnimalsHierarchy

Minimal **rung-1** hierarchical-polysemy example: 4 concepts organized as
a single super-group "Animals" with two sub-clusters of two concepts
each (Dogs: Poodle, Husky; Birds: Eagle, Hawk) on a 3-qubit register.

This is a deliberately minimal sibling of `larql-polysemantic-hierarchical.q.orca.md`,
intended as a teaching / proposer-validation example: it uses the same
**cross-coupled bond-2 MPS** encoding (`Ry; CNOT; Ry; CNOT; Ry` staircase
with linear-combination angles `a + b` and `b + c`), but exercises only
*one* super-group's worth of the angle space. Because the super-group
α-axis is collapsed to a single value, all 4 concepts fall in the same
super-group block and the off-diagonal Gram exposes the two-level
hierarchy a single block resolves into:

| tier                            | members                                   | analytic |<c_i&#124;c_j>|² |
|---------------------------------|-------------------------------------------|----------------------|
| self                            | i = j (4 entries)                         | 1.000                |
| sub-cluster-mate                | (Poodle, Husky), (Eagle, Hawk) — same β   | 0.882                |
| cross-cluster (γ-matched)       | (Poodle, Eagle), (Husky, Hawk) — diff β, same γ | 0.593          |
| cross-cluster (anti-γ const.)   | (Husky, Eagle) — diff β, opposite γ, constructive | 0.753        |
| cross-cluster (anti-γ destr.)   | (Poodle, Hawk)  — diff β, opposite γ, destructive | 0.335        |

The four off-diagonal values fall in strict order
**0.882 > 0.753 > 0.593 > 0.335**, with the sub-cluster-mate tier the
highest and the cross-cluster anti-γ destructive pair the lowest. The
graded sub-structure inside the cross-cluster tier (0.335 / 0.593 /
0.753) is what the cross-coupled-by-sum encoding contributes — under
the bare `Ry · CNOT · Ry · CNOT · Ry` staircase (without linear-
combination angles), all four cross-cluster pairs would collapse to
the single product-state value 0.593 and the hierarchy would lose its
graded structure entirely. The mathematical argument for why the bare
staircase factorizes is in the archived
`fix-mps-encoding-non-factorizing/design.md`.

## Concept geometry

Each concept is prepared as the cross-coupled bond-2 MPS

    |c_i> = Ry(q0, α_i) CNOT(q0, q1) Ry(q1, α_i + β_i) CNOT(q1, q2) Ry(q2, β_i + γ_i) |000>

with α fixed at 0 (single super-group), β ∈ {-0.5, +0.5} (sub-cluster),
γ ∈ {-0.35, +0.35} (concept within sub-cluster):

| i | concept     | sub-cluster | (α, β, γ)             |
|---|-------------|-------------|-----------------------|
| 0 | dog_poodle  | dogs        | (0.0, -0.5, -0.35)    |
| 1 | dog_husky   | dogs        | (0.0, -0.5,  0.35)    |
| 2 | bird_eagle  | birds       | (0.0,  0.5, -0.35)    |
| 3 | bird_hawk   | birds       | (0.0,  0.5,  0.35)    |

### Gram-matrix sketch (4×4 ASCII heatmap)

`#` ≥ 0.7, `o` ∈ [0.3, 0.7), `.` ∈ [0.05, 0.3), blank < 0.05:

```
            poodle  husky  eagle  hawk
poodle    [   #      #      o      o   ]
husky     [   #      #      #      o   ]
eagle     [   o      #      #      #   ]
hawk      [   o      o      #      #   ]
```

## Loaded feature |f> = |dog_poodle>

The machine loads `|dog_poodle>` once, then the 4 query branches
reveal the polysemy column (the row of the Gram matrix indexed by
poodle):

| Query concept   | Sub-cluster | P(|000>) analytic | tier                    |
|-----------------|-------------|-------------------|-------------------------|
| dog_poodle      | dogs        | 1.000             | self                    |
| dog_husky       | dogs        | 0.882             | sub-cluster-mate        |
| bird_eagle      | birds       | 0.593             | cross-cluster, γ-match  |
| bird_hawk       | birds       | 0.335             | cross-cluster, anti-γ   |

Four ordered values — **1.000 > 0.882 > 0.593 > 0.335** — across one
super-group block. Compare the full 12-concept variant
(`larql-polysemantic-hierarchical.q.orca.md`), which extends this to
three super-groups and exposes the additional cross-group tier
(`< 0.18`) sitting strictly below this block.

## Note on the multi-query circuit

A single Qiskit circuit cannot simulate all 4 queries together — each
query's inverse-prepare + measure destroys the feature state via
measurement (no-cloning). The `.q.orca.md` declares all 4 query
parametric call sites to publish the full signature shape; `compile_to_qiskit`
emits all 4 branches in BFS order. To recover the polysemy column
empirically, run 4 independent prepare+query circuits (mirroring the
strategy of `demos/larql_polysemantic_hierarchical/demo.py`).

## Notes for the proposer (researcher follow-ups)

The original sketch this example is derived from added per-concept
`Rz(qs[1], phi_dog)` / `Rz(qs[0], phi_cross)` gates as a "tunable
interference knob" between the two `CNOT`s of the staircase. Two
points worth carrying back:

- **Compiler matcher.** The current `q_orca.compute_concept_gram_mps`
  helper recognizes only `Ry · CNOT · Ry · CNOT · Ry` staircases.
  Inserting `Rz` gates between the second `Ry` and the second `CNOT`
  causes the matcher to raise `MpsGramConfigurationError("non_staircase_effect")`.
  Adding optional 1-qubit phase gates between `Ry` segments is a
  small, well-defined extension to the matcher (and would not change
  bond dimension — `Rz` is 1-qubit, χ stays at 2).
- **Phase magnitudes vs. claimed tiers.** The sketch's `phi_dog = 0.3`
  and `phi_cross = π/2` would, with shared `(a, b, c) = (0.4, 1.1, 0.7)`
  across all 4 concepts, produce intra-cluster overlaps very close to
  1 (a 0.3-radian Rz on a single qubit barely tilts the Gram) and
  cross-cluster overlaps that depend on what fraction of `qs[0]` sits
  in `|1>` after `Ry(qs[0], 0.4)` (about 4%) — the cross-cluster tier
  would land near 0.96, not the claimed 0.35-0.55. The cross-coupled
  angle structure used here (varying `(α, β, γ)` per concept) is the
  reliable mechanism for the claimed tier separations; the phase-knob
  axis is best framed as an *additional* interference dimension to
  layer on top, not a replacement for the angle differentiation.

## context
| Field    | Type        | Default            |
|----------|-------------|--------------------|
| qubits   | list<qubit> | [q0, q1, q2]       |

## events
- load_feature
- query_dog_poodle
- query_dog_husky
- query_bird_eagle
- query_bird_hawk
- measure_done

## state idle [initial]
> 3-qubit concept register in `|000>`. No feature has been prepared.

## state feature_loaded
> `|f> = |dog_poodle>` prepared via `prepare_concept(0.0, -0.5, -0.35)`.

## state queried_dog_poodle
> `query_concept(dog_poodle)` applied — self-query. `P(|000>) = 1.000`.

## state queried_dog_husky
> `query_concept(dog_husky)` applied — sub-cluster-mate. `P(|000>) ≈ 0.882`.

## state queried_bird_eagle
> `query_concept(bird_eagle)` applied — cross-cluster, γ-matched. `P(|000>) ≈ 0.593`.

## state queried_bird_hawk
> `query_concept(bird_hawk)` applied — cross-cluster, anti-γ destructive. `P(|000>) ≈ 0.335`.

## state done [final]
> Measurement collapsed the 3-qubit register to a classical bitstring.

## transitions
| Source              | Event             | Guard | Target                 | Action                                    |
|---------------------|-------------------|-------|------------------------|-------------------------------------------|
| idle                | load_feature      |       | feature_loaded         | prepare_concept(0.0, -0.5, -0.35)         |
| feature_loaded      | query_dog_poodle  |       | queried_dog_poodle     | query_concept(0.0, -0.5, -0.35)           |
| feature_loaded      | query_dog_husky   |       | queried_dog_husky      | query_concept(0.0, -0.5, 0.35)            |
| feature_loaded      | query_bird_eagle  |       | queried_bird_eagle     | query_concept(0.0, 0.5, -0.35)            |
| feature_loaded      | query_bird_hawk   |       | queried_bird_hawk      | query_concept(0.0, 0.5, 0.35)             |
| queried_dog_poodle  | measure_done      |       | done                   |                                           |
| queried_dog_husky   | measure_done      |       | done                   |                                           |
| queried_bird_eagle  | measure_done      |       | done                   |                                           |
| queried_bird_hawk   | measure_done      |       | done                   |                                           |

## actions
| Name            | Signature                                | Effect                                                                                              |
|-----------------|------------------------------------------|-----------------------------------------------------------------------------------------------------|
| prepare_concept | (qs, a: angle, b: angle, c: angle) -> qs | Ry(qs[0], a); CNOT(qs[0], qs[1]); Ry(qs[1], a + b); CNOT(qs[1], qs[2]); Ry(qs[2], b + c)            |
| query_concept   | (qs, a: angle, b: angle, c: angle) -> qs | Ry(qs[2], -b - c); CNOT(qs[1], qs[2]); Ry(qs[1], -a - b); CNOT(qs[0], qs[1]); Ry(qs[0], -a)         |

## verification rules
- unitarity: Ry and CNOT preserve norm; every transition evolves the 3-qubit register unitarily from `|000>`
- mps_bond_2_cross_coupled_encoding: each concept is prepared as a bond-dimension-2 MPS via the `Ry; CNOT; Ry; CNOT; Ry` staircase with cross-coupled angle expressions (`a`, `a + b`, `b + c`) — the linear-combination angles produce a non-factorized Gram, distinguishing this rung from the bare staircase (whose Gram factorizes despite Schmidt rank 2)
- hierarchical_overlap: four ordered off-diagonal values — sub-cluster-mate 0.882 > cross-cluster anti-γ constructive 0.753 > cross-cluster γ-matched 0.593 > cross-cluster anti-γ destructive 0.335 — strictly ordered with no ties at the tier boundaries
- non_factorized_gram: the encoding's `|<c_i|c_j>|²` differs by ≥ 0.05 on at least one off-diagonal entry from the same-angle product-state Gram `∏_k cos((θ_{i,k} − θ_{j,k})/2)²` — the cross-coupling makes the Gram structurally distinct from rung 0
- no_cloning: the prepared feature is not duplicated; each query needs a fresh prepare+query sequence
- measurement_collapse_allowed: `done` is the intended collapse sink — each branch ends in measurement; analytic `P(|000>)` per query (1.000 self, 0.882 sub-mate, 0.593 / 0.335 cross-cluster) is documented in the polysemy-scores table above
