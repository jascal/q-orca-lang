# machine LarqlPolysemanticHierarchical

Hierarchical-overlap polysemantic concept-projection over 12 LARQL concepts
organized as a two-level hierarchy (3 super-groups × 2 sub-clusters × 2
concepts) on a 3-qubit register, using two CNOT-staircase parametric
actions (`prepare_concept(a, b, c)` and `query_concept(a, b, c)`) to
stamp 13 call sites from a single bond-2 MPS template.

This is the **rung-1** companion to `larql-polysemantic-clusters.q.orca.md`
(rung 0). The clusters example demonstrates *flat* block structure on the
product-state manifold — concept overlaps split into three uniform tiers
(self 1.0 / cluster-mate 0.72 / cross-cluster < 0.09). This example lifts
the encoding to a bond-dimension-2 matrix product state via a
`Ry; CNOT; Ry; CNOT; Ry` staircase with **cross-coupled angle
parameters** — the q1 and q2 rotations bind sums of two parameters
each, leaking each angle into more than one qubit's amplitude. The
staircase alone (with single-parameter Ry rotations on the `|000>`
vacuum) gives a Schmidt-rank-2 entangled state, but its Gram still
factorizes as `cos((α_i − α_j)/2)·cos((β_i − β_j)/2)·cos((γ_i − γ_j)/2)`
— mathematically identical to rung 0. The cross-coupling is what
breaks that factorization and produces a genuinely *four-tier*
hierarchical Gram matrix: self / sub-cluster-mate /
super-group-sibling / cross-group. The full ladder is in
`docs/research/polysemantic-encoding-beyond-product-states.md`; the
mathematical argument for why the bare staircase factorizes is in
`openspec/changes/fix-mps-encoding-non-factorizing/design.md` (until
that change is archived).

## Concept geometry (12 concepts, 3-qubit register)

Each concept `c_i` is prepared as the cross-coupled bond-2 MPS

    |c_i> = Ry(q0, α_i) CNOT(q0, q1) Ry(q1, α_i + β_i) CNOT(q1, q2) Ry(q2, β_i + γ_i) |000>

on a 3-qubit register. Each angle parameter has a "primary" qubit
(α → q0, β → q1, γ → q2) but `β` also leaks into the q2 rotation and
`α` also leaks into the q1 rotation through the linear-combination
angles `α + β` and `β + γ`. The CNOT staircase introduces 1D locality
*and* the cross-coupling makes the inner-product map non-factorized
across qubits — the four-tier Gram structure below depends on **both**
the chain entanglement and the angle leakage. The natural mapping
onto a two-level hierarchy is:

- **Super-group** index — encoded primarily in `α` (the q0 rotation).
  Three super-groups at evenly-spaced cyclic angles
  `α ∈ {0, 2π/3, 4π/3}`. Cross-group concepts are well-separated
  because they differ on the chain root.
- **Sub-cluster** index — encoded primarily in `β` (which drives the
  q1 rotation through `α + β` and contributes to the q2 rotation
  through `β + γ`). Two sub-clusters per super-group at offsets
  `β ∈ {-0.5, +0.5}`. Same-super-group, different-sub-cluster pairs
  share the chain root but diverge on the middle and leaf qubits.
- **Concept** index within sub-cluster — encoded in `γ` (the q2
  rotation through the `β + γ` term). Two concepts per sub-cluster at
  offsets `γ ∈ {-0.35, +0.35}`. Concepts within a sub-cluster share
  the chain root and the middle qubit and differ only on the leaf.

The 12 concrete angle triples (with `α₂ = 2π/3 ≈ 2.094`, `α₃ = 4π/3 ≈ 4.189`):

| i  | concept     | super-group | sub-cluster | (α, β, γ)            |
|----|-------------|-------------|-------------|----------------------|
| 0  | dog         | animals     | mammals     | ( 0.000, -0.50, -0.35) |
| 1  | cat         | animals     | mammals     | ( 0.000, -0.50,  0.35) |
| 2  | robin       | animals     | birds       | ( 0.000,  0.50, -0.35) |
| 3  | eagle       | animals     | birds       | ( 0.000,  0.50,  0.35) |
| 4  | strawberry  | fruits      | berries     | ( 2.094, -0.50, -0.35) |
| 5  | blueberry   | fruits      | berries     | ( 2.094, -0.50,  0.35) |
| 6  | mango       | fruits      | tropical    | ( 2.094,  0.50, -0.35) |
| 7  | papaya      | fruits      | tropical    | ( 2.094,  0.50,  0.35) |
| 8  | car         | vehicles    | land        | ( 4.189, -0.50, -0.35) |
| 9  | bike        | vehicles    | land        | ( 4.189, -0.50,  0.35) |
| 10 | plane       | vehicles    | air         | ( 4.189,  0.50, -0.35) |
| 11 | drone       | vehicles    | air         | ( 4.189,  0.50,  0.35) |

### Gram matrix (analytic, four-tier hierarchy)

The cross-coupled MPS overlap is not a separable product over qubits
(unlike rung 0 — and unlike the bare CNOT staircase, which despite
being entangled has a Gram identical to rung 0; see the design note
referenced above). Numerical contraction via `compute_concept_gram_mps`
produces this four-tier structure on the off-diagonal of
`|<c_i|c_j>|²`:

| tier                       | members                              | analytic |<c_i|c_j>|²     |
|----------------------------|--------------------------------------|----------------------------|
| self                       | i = j (12 entries)                   | 1.000                      |
| sub-cluster-mate           | same α, same β, different γ (6 pairs)| 0.882 (uniform)            |
| super-group-sibling        | same α, different β (12 pairs)       | 0.335, 0.593, 0.753        |
| cross-group                | different α (48 pairs)               | 0.000 – 0.178              |

(The super-sibling tier resolves into three discrete values per
super-group block: 0.753 when the cross-coupling adds constructively,
0.593 when γ is matched, and 0.335 when the cross-coupling adds
destructively. All three sit strictly between sub-cluster-mate and
cross-group; the tier ordering is preserved with margin.)

Sketch (4-tier ASCII heatmap, `#` ≥ 0.7, `o` ∈ [0.3, 0.7), `.` ∈ [0.05, 0.3),
blank < 0.05):

```
     dog cat rob eag |  str blu man pap |  car bik pla drn
dog [  #   #   o   o  |  .   .          |  .   .   .   .  ]
cat [  #   #   #   o  |  .   .          |  .   .   .   .  ]
rob [  o   #   #   #  |  .   .   .   .  |          .   .  ]
eag [  o   o   #   #  |  .   .   .   .  |          .   .  ]
str [  .   .   .   .  |  #   #   o   o  |  .   .          ]
blu [  .   .   .   .  |  #   #   #   o  |  .   .          ]
man [          .   .  |  o   #   #   #  |  .   .   .   .  ]
pap [          .   .  |  o   o   #   #  |  .   .   .   .  ]
car [  .   .          |  .   .   .   .  |  #   #   o   o  ]
bik [  .   .          |  .   .   .   .  |  #   #   #   o  ]
pla [  .   .   .   .  |          .   .  |  o   #   #   #  ]
drn [  .   .   .   .  |          .   .  |  o   o   #   #  ]
```

Each 4×4 super-group diagonal block resolves into a 2×2 sub-cluster
core (the `#` regions, sub-cluster-mates and the cross-coupling-
constructive super-sibling) and a banded super-sibling tail (the `o`
regions). Inter-group blocks fall into the cross-group tier (`.`
and blank regions). `compute_concept_gram_mps` in the compiler package
produces this matrix exactly for this machine.

## Loaded feature |f> = |dog> (single-concept load)

To keep the polysemy column directly readable as a **row of the Gram
matrix**, this example loads a single concept — `|dog>` — as the
feature rather than a 4-way superposition. The polysemy column then
exposes the four-tier structure in the clearest form:

| Query concept    | Group     | Sub-cluster  | P(|000>) analytic | tier               |
|------------------|-----------|--------------|-------------------|--------------------|
| dog        (0)   | animals   | mammals      | 1.000             | self               |
| cat        (1)   | animals   | mammals      | 0.882             | sub-cluster-mate   |
| robin      (2)   | animals   | birds        | 0.593             | super-group-sib    |
| eagle      (3)   | animals   | birds        | 0.335             | super-group-sib    |
| strawberry (4)   | fruits    | berries      | 0.063             | cross-group        |
| blueberry  (5)   | fruits    | berries      | 0.055             | cross-group        |
| mango      (6)   | fruits    | tropical     | 0.000             | cross-group        |
| papaya     (7)   | fruits    | tropical     | 0.000             | cross-group        |
| car        (8)   | vehicles  | land         | 0.063             | cross-group        |
| bike       (9)   | vehicles  | land         | 0.055             | cross-group        |
| plane     (10)   | vehicles  | air          | 0.140             | cross-group        |
| drone     (11)   | vehicles  | air          | 0.079             | cross-group        |

Four ordered tiers — **1.0** (self) → **0.88** (sub-cluster-mate) →
**0.34 – 0.59** (super-group sibling) → **≤ 0.14** (cross-group).
Compare against `larql-polysemantic-clusters`'s flat 1.00 / 0.72 /
≲ 0.09 three-tier structure: that example demonstrates the *block*
polysemantic phenomenon on the product manifold, this one lifts it to
a *graded hierarchical* phenomenon on the cross-coupled bond-2 MPS
manifold.

## Note on the multi-query circuit

As with `larql-polysemantic-clusters`, a single Qiskit circuit cannot
simulate all 12 queries together — each query's inverse-prepare +
measure destroys the feature state via measurement (no-cloning). The
`.q.orca.md` declares all 12 parametric call sites to publish the full
signature shape; `compile_to_qiskit` emits all 12 branches in BFS order.
The companion demo `demos/larql_polysemantic_hierarchical/demo.py` runs
12 independent prepare+query circuits to recover the polysemy column.

## context
| Field    | Type        | Default            |
|----------|-------------|--------------------|
| qubits   | list<qubit> | [q0, q1, q2]       |

## events
- load_feature
- query_dog
- query_cat
- query_robin
- query_eagle
- query_strawberry
- query_blueberry
- query_mango
- query_papaya
- query_car
- query_bike
- query_plane
- query_drone
- measure_done

## state idle [initial]
> 3-qubit concept register in `|000>`. No feature has been prepared.

## state feature_loaded
> `|f> = |dog>` prepared via `prepare_concept(0.0, -0.5, -0.35)`.

## state queried_dog
> `query_concept(dog)` applied — self-query. `P(|000>) = 1.000`.

## state queried_cat
> `query_concept(cat)` applied — sub-cluster-mate (mammals). `P(|000>) ≈ 0.882`.

## state queried_robin
> `query_concept(robin)` applied — super-group sibling (animals/birds). `P(|000>) ≈ 0.593`.

## state queried_eagle
> `query_concept(eagle)` applied — super-group sibling (animals/birds). `P(|000>) ≈ 0.335`.

## state queried_strawberry
> `query_concept(strawberry)` applied — cross-group (fruits). `P(|000>) ≈ 0.063`.

## state queried_blueberry
> `query_concept(blueberry)` applied — cross-group (fruits). `P(|000>) ≈ 0.055`.

## state queried_mango
> `query_concept(mango)` applied — cross-group (fruits). `P(|000>) ≈ 0.000`.

## state queried_papaya
> `query_concept(papaya)` applied — cross-group (fruits). `P(|000>) ≈ 0.000`.

## state queried_car
> `query_concept(car)` applied — cross-group (vehicles). `P(|000>) ≈ 0.063`.

## state queried_bike
> `query_concept(bike)` applied — cross-group (vehicles). `P(|000>) ≈ 0.055`.

## state queried_plane
> `query_concept(plane)` applied — cross-group (vehicles). `P(|000>) ≈ 0.140`.

## state queried_drone
> `query_concept(drone)` applied — cross-group (vehicles). `P(|000>) ≈ 0.079`.

## state done [final]
> Measurement collapsed the 3-qubit register to a classical bitstring.

## transitions
| Source             | Event             | Guard | Target                | Action                                       |
|--------------------|-------------------|-------|-----------------------|----------------------------------------------|
| idle               | load_feature      |       | feature_loaded        | prepare_concept(0.0, -0.5, -0.35)            |
| feature_loaded     | query_dog         |       | queried_dog           | query_concept(0.0, -0.5, -0.35)              |
| feature_loaded     | query_cat         |       | queried_cat           | query_concept(0.0, -0.5, 0.35)               |
| feature_loaded     | query_robin       |       | queried_robin         | query_concept(0.0, 0.5, -0.35)               |
| feature_loaded     | query_eagle       |       | queried_eagle         | query_concept(0.0, 0.5, 0.35)                |
| feature_loaded     | query_strawberry  |       | queried_strawberry    | query_concept(2.094, -0.5, -0.35)            |
| feature_loaded     | query_blueberry   |       | queried_blueberry     | query_concept(2.094, -0.5, 0.35)             |
| feature_loaded     | query_mango       |       | queried_mango         | query_concept(2.094, 0.5, -0.35)             |
| feature_loaded     | query_papaya      |       | queried_papaya        | query_concept(2.094, 0.5, 0.35)              |
| feature_loaded     | query_car         |       | queried_car           | query_concept(4.189, -0.5, -0.35)            |
| feature_loaded     | query_bike        |       | queried_bike          | query_concept(4.189, -0.5, 0.35)             |
| feature_loaded     | query_plane       |       | queried_plane         | query_concept(4.189, 0.5, -0.35)             |
| feature_loaded     | query_drone       |       | queried_drone         | query_concept(4.189, 0.5, 0.35)              |
| queried_dog        | measure_done      |       | done                  |                                              |
| queried_cat        | measure_done      |       | done                  |                                              |
| queried_robin      | measure_done      |       | done                  |                                              |
| queried_eagle      | measure_done      |       | done                  |                                              |
| queried_strawberry | measure_done      |       | done                  |                                              |
| queried_blueberry  | measure_done      |       | done                  |                                              |
| queried_mango      | measure_done      |       | done                  |                                              |
| queried_papaya     | measure_done      |       | done                  |                                              |
| queried_car        | measure_done      |       | done                  |                                              |
| queried_bike       | measure_done      |       | done                  |                                              |
| queried_plane      | measure_done      |       | done                  |                                              |
| queried_drone      | measure_done      |       | done                  |                                              |

## actions
| Name            | Signature                                | Effect                                                                                              |
|-----------------|------------------------------------------|-----------------------------------------------------------------------------------------------------|
| prepare_concept | (qs, a: angle, b: angle, c: angle) -> qs | Ry(qs[0], a); CNOT(qs[0], qs[1]); Ry(qs[1], a + b); CNOT(qs[1], qs[2]); Ry(qs[2], b + c)            |
| query_concept   | (qs, a: angle, b: angle, c: angle) -> qs | Ry(qs[2], -b - c); CNOT(qs[1], qs[2]); Ry(qs[1], -a - b); CNOT(qs[0], qs[1]); Ry(qs[0], -a)         |

## verification rules
- unitarity: Ry and CNOT preserve norm; every transition evolves the 3-qubit register unitarily from `|000>`
- mps_bond_2_cross_coupled_encoding: each concept is prepared as a bond-dimension-2 MPS via the `Ry; CNOT; Ry; CNOT; Ry` staircase with cross-coupled angle expressions (`a`, `a + b`, `b + c`) — the linear-combination angles produce a non-factorized Gram, distinguishing this rung from the bare staircase (whose Gram factorizes despite Schmidt rank 2)
- hierarchical_overlap: four ordered tiers — self 1.000 / sub-cluster-mate 0.882 / super-group-sibling {0.335, 0.593, 0.753} / cross-group [0.000, 0.178] — with strict ordering across tier boundaries
- non_factorized_gram: the encoding's `|<c_i|c_j>|²` differs by ≥ 0.05 on at least one off-diagonal entry from the same-angle product-state Gram `∏_k cos((θ_{i,k} − θ_{j,k})/2)²` — the cross-coupling makes the Gram structurally distinct from rung 0
- no_cloning: the prepared feature is not duplicated; each query needs a fresh prepare+query sequence (the demo runs 12 independent circuits)
- measurement_collapse_allowed: `done` is the intended collapse sink — each branch ends in measurement; analytic `P(|000>)` per query (1.000 self, 0.882 sub-mate, 0.34–0.59 super-sib, ≤ 0.14 cross) is documented in the polysemy-scores table above
