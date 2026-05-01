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
`Ry; CNOT; Ry; CNOT; Ry` staircase, which introduces correlations between
adjacent qubits and produces a *four-tier* hierarchical Gram matrix:
self / sub-cluster-mate / super-group-sibling / cross-group. The full
ladder is in `docs/research/polysemantic-encoding-beyond-product-states.md`.

## Concept geometry (12 concepts, 3-qubit register)

Each concept `c_i` is prepared as the bond-2 MPS

    |c_i> = Ry(q0, α_i) CNOT(q0, q1) Ry(q1, β_i) CNOT(q1, q2) Ry(q2, γ_i) |000>

on a 3-qubit register. The CNOT staircase introduces 1D locality: q0 is
the chain root, q1 is correlated with q0 only, and q2 is correlated with
q0 only through q1. This naturally maps onto a two-level hierarchy:

- **Super-group** index — encoded in `α` (the q0 rotation, chain root).
  Three super-groups at evenly-spaced cyclic angles `α ∈ {0, 2π/3, 4π/3}`.
  Cross-group concepts are well-separated because they differ on the
  chain root.
- **Sub-cluster** index — encoded in `β` (the q1 rotation). Two
  sub-clusters per super-group at offsets `β ∈ {-0.75, +0.75}`.
  Same-super-group, different-sub-cluster pairs share the chain root but
  diverge on the middle qubit.
- **Concept** index within sub-cluster — encoded in `γ` (the q2 rotation).
  Two concepts per sub-cluster at offsets `γ ∈ {-0.35, +0.35}`. Concepts
  within a sub-cluster share both the chain root and the middle qubit
  and differ only on the leaf.

The 12 concrete angle triples (with `α₂ = 2π/3 ≈ 2.094`, `α₃ = 4π/3 ≈ 4.189`):

| i  | concept     | super-group | sub-cluster | (α, β, γ)            |
|----|-------------|-------------|-------------|----------------------|
| 0  | dog         | animals     | mammals     | ( 0.000, -0.75, -0.35) |
| 1  | cat         | animals     | mammals     | ( 0.000, -0.75,  0.35) |
| 2  | robin       | animals     | birds       | ( 0.000,  0.75, -0.35) |
| 3  | eagle       | animals     | birds       | ( 0.000,  0.75,  0.35) |
| 4  | strawberry  | fruits      | berries     | ( 2.094, -0.75, -0.35) |
| 5  | blueberry   | fruits      | berries     | ( 2.094, -0.75,  0.35) |
| 6  | mango       | fruits      | tropical    | ( 2.094,  0.75, -0.35) |
| 7  | papaya      | fruits      | tropical    | ( 2.094,  0.75,  0.35) |
| 8  | car         | vehicles    | land        | ( 4.189, -0.75, -0.35) |
| 9  | bike        | vehicles    | land        | ( 4.189, -0.75,  0.35) |
| 10 | plane       | vehicles    | air         | ( 4.189,  0.75, -0.35) |
| 11 | drone       | vehicles    | air         | ( 4.189,  0.75,  0.35) |

### Gram matrix (analytic, four-tier hierarchy)

The CNOT-staircase MPS overlap is not a separable product over qubits
(unlike rung 0). Numerical contraction via
`compute_concept_gram_mps` produces this four-tier structure on the
off-diagonal of `|<c_i|c_j>|²`:

| tier                       | members                              | analytic |<c_i|c_j>|²     |
|----------------------------|--------------------------------------|----------------------------|
| self                       | i = j (12 entries)                   | 1.000                      |
| sub-cluster-mate           | same α, same β, different γ (6 pairs)| 0.882 (uniform)            |
| super-group-sibling        | same α, different β (12 pairs)       | 0.472 – 0.535              |
| cross-group                | different α (48 pairs)               | 0.118 – 0.250              |

Sketch (4-tier ASCII heatmap, `#` ≥ 0.7, `o` ∈ [0.3, 0.7), `.` ∈ [0.1, 0.3),
blank < 0.1):

```
        dog  cat  rob  eag | str  blu  man  pap | car  bik  pla  drn
dog  [   #    #    o    o  |  .    .    .    .  |  .    .    .    .   ]
cat  [   #    #    o    o  |  .    .    .    .  |  .    .    .    .   ]
rob  [   o    o    #    #  |  .    .    .    .  |  .    .    .    .   ]
eag  [   o    o    #    #  |  .    .    .    .  |  .    .    .    .   ]
str  [   .    .    .    .  |  #    #    o    o  |  .    .    .    .   ]
blu  [   .    .    .    .  |  #    #    o    o  |  .    .    .    .   ]
man  [   .    .    .    .  |  o    o    #    #  |  .    .    .    .   ]
pap  [   .    .    .    .  |  o    o    #    #  |  .    .    .    .   ]
car  [   .    .    .    .  |  .    .    .    .  |  #    #    o    o   ]
bik  [   .    .    .    .  |  .    .    .    .  |  #    #    o    o   ]
pla  [   .    .    .    .  |  .    .    .    .  |  o    o    #    #   ]
drn  [   .    .    .    .  |  .    .    .    .  |  o    o    #    #   ]
```

Each 4×4 super-group diagonal block resolves into two 2×2 sub-cluster
blocks (the `#` regions, sub-cluster-mates) sandwiched against the
2×2 super-group siblings (the `o` regions). Inter-group blocks fall
into the cross-group tier (`.` regions). `compute_concept_gram_mps` in
the compiler package produces this matrix exactly for this machine.

## Loaded feature |f> = |dog> (single-concept load)

To keep the polysemy column directly readable as a **row of the Gram
matrix**, this example loads a single concept — `|dog>` — as the
feature rather than a 4-way superposition. The polysemy column then
exposes the four-tier structure in the clearest form:

| Query concept    | Group     | Sub-cluster  | P(|000>) analytic | tier               |
|------------------|-----------|--------------|-------------------|--------------------|
| dog        (0)   | animals   | mammals      | 1.000             | self               |
| cat        (1)   | animals   | mammals      | 0.882             | sub-cluster-mate   |
| robin      (2)   | animals   | birds        | 0.535             | super-group-sib    |
| eagle      (3)   | animals   | birds        | 0.472             | super-group-sib    |
| strawberry (4)   | fruits    | berries      | 0.250             | cross-group        |
| blueberry  (5)   | fruits    | berries      | 0.221             | cross-group        |
| mango      (6)   | fruits    | tropical     | 0.134             | cross-group        |
| papaya     (7)   | fruits    | tropical     | 0.118             | cross-group        |
| car        (8)   | vehicles  | land         | 0.250             | cross-group        |
| bike       (9)   | vehicles  | land         | 0.221             | cross-group        |
| plane     (10)   | vehicles  | air          | 0.134             | cross-group        |
| drone     (11)   | vehicles  | air          | 0.118             | cross-group        |

Four ordered tiers — **1.0** (self) → **0.88** (sub-cluster-mate) → **~0.50**
(super-group sibling) → **~0.18** (cross-group). Compare against
`larql-polysemantic-clusters`'s flat 1.00 / 0.72 / ≲ 0.09 three-tier
structure: that example demonstrates the *block* polysemantic phenomenon
on the product manifold, this one lifts it to a *graded hierarchical*
phenomenon on the bond-2 MPS manifold.

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
> `|f> = |dog>` prepared via `prepare_concept(0.0, -0.75, -0.35)`.

## state queried_dog
> `query_concept(dog)` applied — self-query. `P(|000>) = 1.000`.

## state queried_cat
> `query_concept(cat)` applied — sub-cluster-mate (mammals). `P(|000>) ≈ 0.882`.

## state queried_robin
> `query_concept(robin)` applied — super-group sibling (animals/birds). `P(|000>) ≈ 0.535`.

## state queried_eagle
> `query_concept(eagle)` applied — super-group sibling (animals/birds). `P(|000>) ≈ 0.472`.

## state queried_strawberry
> `query_concept(strawberry)` applied — cross-group (fruits). `P(|000>) ≈ 0.250`.

## state queried_blueberry
> `query_concept(blueberry)` applied — cross-group (fruits). `P(|000>) ≈ 0.221`.

## state queried_mango
> `query_concept(mango)` applied — cross-group (fruits). `P(|000>) ≈ 0.134`.

## state queried_papaya
> `query_concept(papaya)` applied — cross-group (fruits). `P(|000>) ≈ 0.118`.

## state queried_car
> `query_concept(car)` applied — cross-group (vehicles). `P(|000>) ≈ 0.250`.

## state queried_bike
> `query_concept(bike)` applied — cross-group (vehicles). `P(|000>) ≈ 0.221`.

## state queried_plane
> `query_concept(plane)` applied — cross-group (vehicles). `P(|000>) ≈ 0.134`.

## state queried_drone
> `query_concept(drone)` applied — cross-group (vehicles). `P(|000>) ≈ 0.118`.

## state done [final]
> Measurement collapsed the 3-qubit register to a classical bitstring.

## transitions
| Source             | Event             | Guard | Target                | Action                                       |
|--------------------|-------------------|-------|-----------------------|----------------------------------------------|
| idle               | load_feature      |       | feature_loaded        | prepare_concept(0.0, -0.75, -0.35)           |
| feature_loaded     | query_dog         |       | queried_dog           | query_concept(0.0, -0.75, -0.35)             |
| feature_loaded     | query_cat         |       | queried_cat           | query_concept(0.0, -0.75, 0.35)              |
| feature_loaded     | query_robin       |       | queried_robin         | query_concept(0.0, 0.75, -0.35)              |
| feature_loaded     | query_eagle       |       | queried_eagle         | query_concept(0.0, 0.75, 0.35)               |
| feature_loaded     | query_strawberry  |       | queried_strawberry    | query_concept(2.094, -0.75, -0.35)           |
| feature_loaded     | query_blueberry   |       | queried_blueberry     | query_concept(2.094, -0.75, 0.35)            |
| feature_loaded     | query_mango       |       | queried_mango         | query_concept(2.094, 0.75, -0.35)            |
| feature_loaded     | query_papaya      |       | queried_papaya        | query_concept(2.094, 0.75, 0.35)             |
| feature_loaded     | query_car         |       | queried_car           | query_concept(4.189, -0.75, -0.35)           |
| feature_loaded     | query_bike        |       | queried_bike          | query_concept(4.189, -0.75, 0.35)            |
| feature_loaded     | query_plane       |       | queried_plane         | query_concept(4.189, 0.75, -0.35)            |
| feature_loaded     | query_drone       |       | queried_drone         | query_concept(4.189, 0.75, 0.35)             |
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
| Name            | Signature                                | Effect                                                                                  |
|-----------------|------------------------------------------|-----------------------------------------------------------------------------------------|
| prepare_concept | (qs, a: angle, b: angle, c: angle) -> qs | Ry(qs[0], a); CNOT(qs[0], qs[1]); Ry(qs[1], b); CNOT(qs[1], qs[2]); Ry(qs[2], c)        |
| query_concept   | (qs, a: angle, b: angle, c: angle) -> qs | Ry(qs[2], -c); CNOT(qs[1], qs[2]); Ry(qs[1], -b); CNOT(qs[0], qs[1]); Ry(qs[0], -a)     |

## verification rules
- unitarity: Ry and CNOT preserve norm; every transition evolves the 3-qubit register unitarily from `|000>`
- mps_bond_2_encoding: each concept is prepared as a bond-dimension-2 MPS via the `Ry; CNOT; Ry; CNOT; Ry` staircase — the minimal entangling pattern beyond rung 0
- hierarchical_overlap: four ordered tiers — self 1.000 / sub-cluster-mate 0.882 / super-group-sibling [0.472, 0.535] / cross-group [0.118, 0.250] — with strict ordering across tier boundaries
- no_cloning: the prepared feature is not duplicated; each query needs a fresh prepare+query sequence (the demo runs 12 independent circuits)
- measurement_collapse_allowed: `done` is the intended collapse sink — each branch ends in measurement; analytic `P(|000>)` per query (1.000 self, 0.882 sub-mate, 0.47–0.54 super-sib, 0.12–0.25 cross) is documented in the polysemy-scores table above
