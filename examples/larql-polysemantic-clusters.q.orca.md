# machine LarqlPolysemanticClusters

Structured-overlap polysemantic concept-projection over 12 LARQL concepts
grouped into 3 semantic clusters of 4, using two multi-angle parametric
actions (`prepare_concept(a, b, c)` and `query_concept(a, b, c)`) to
stamp 13 call sites from two product-state templates.

This is the "phenomenon" companion to `larql-polysemantic-12.q.orca.md`
(the "mechanism" demo). The simpler 12-concept example uses the degenerate
uniform-overlap dictionary — every pair of concepts has identical Hadamard
overlap 1/2, so the polysemy table has exactly two tiers (3/4 vs. 1/3)
with no intra-structure. Sparse-autoencoder studies of real transformer
FFNs (Elhage et al., `2209.10652`) report a different empirical signature:
concepts sharing a semantic cluster report *higher* overlap than
cross-cluster concepts — a **block**-structured Gram matrix, not a
uniform one. This example encodes that block structure explicitly and
makes it directly visible in the polysemy column.

## Concept geometry (12 concepts, 3-qubit register)

Each concept `c_i` is prepared as a product state

    |c_i> = Ry(q0, α_i) Ry(q1, β_i) Ry(q2, γ_i) |000>

on a 3-qubit register (2³ = 8 dimensions, with 12 concepts packed
non-orthogonally — an over-complete dictionary). The 12 angle triples are
hand-picked so three clusters of 4 form around axis-aligned "center"
angles, with tetrahedral scatter around each center:

| Cluster  | Center          | Members                               |
|----------|-----------------|---------------------------------------|
| capitals | `(2.8, 0, 0)`   | Paris, Tokyo, London, Berlin          |
| fruits   | `(0, 2.8, 0)`   | apple, banana, cherry, durian         |
| vehicles | `(0, 0, 2.8)`   | car, boat, plane, rocket              |

Per-member scatter uses the tetrahedral offsets
`{(+s,+s,+s), (+s,-s,-s), (-s,+s,-s), (-s,-s,+s)}` with `s = 0.4`.

The concrete 12 angle triples:

| i  | concept | cluster  | (α, β, γ)          |
|----|---------|----------|--------------------|
| 0  | Paris   | capitals | ( 3.2,  0.4,  0.4) |
| 1  | Tokyo   | capitals | ( 3.2, -0.4, -0.4) |
| 2  | London  | capitals | ( 2.4,  0.4, -0.4) |
| 3  | Berlin  | capitals | ( 2.4, -0.4,  0.4) |
| 4  | apple   | fruits   | ( 0.4,  3.2,  0.4) |
| 5  | banana  | fruits   | ( 0.4,  2.4, -0.4) |
| 6  | cherry  | fruits   | (-0.4,  3.2, -0.4) |
| 7  | durian  | fruits   | (-0.4,  2.4,  0.4) |
| 8  | car     | vehicles | ( 0.4,  0.4,  3.2) |
| 9  | boat    | vehicles | ( 0.4, -0.4,  2.4) |
| 10 | plane   | vehicles | (-0.4,  0.4,  2.4) |
| 11 | rocket  | vehicles | (-0.4, -0.4,  3.2) |

### Gram matrix (analytic, block structure)

With `|<c_i | c_j>|² = ∏_k cos²((θ_{i,k} - θ_{j,k})/2)`:

- **intra-cluster** `|<c_i | c_j>|² = 0.720` (uniform across all 6 pairs
  per cluster × 3 clusters = 18 pairs).
- **inter-cluster** `|<c_i | c_j>|² ∈ [0.0008, 0.0852]` (all 48 cross
  pairs well below the intra tier; most are near-orthogonal).

Sketch (absolute-value tiers):

```
          cap0 cap1 cap2 cap3 | fru0 fru1 fru2 fru3 | veh0 veh1 veh2 veh3
cap0    [  1.0  0.7  0.7  0.7 |  ~0   ~0   ~0   ~0  |  ~0   ~0   ~0   ~0 ]
cap1    [  0.7  1.0  0.7  0.7 |  ~0   ~0   ~0   ~0  |  ~0   ~0   ~0   ~0 ]
cap2    [  0.7  0.7  1.0  0.7 |  ~0   ~0   ~0   ~0  |  ~0   ~0   ~0   ~0 ]
cap3    [  0.7  0.7  0.7  1.0 |  ~0   ~0   ~0   ~0  |  ~0   ~0   ~0   ~0 ]
fru0    [  ~0   ~0   ~0   ~0  |  1.0  0.7  0.7  0.7 |  ~0   ~0   ~0   ~0 ]
fru1    [  ~0   ~0   ~0   ~0  |  0.7  1.0  0.7  0.7 |  ~0   ~0   ~0   ~0 ]
fru2    [  ~0   ~0   ~0   ~0  |  0.7  0.7  1.0  0.7 |  ~0   ~0   ~0   ~0 ]
fru3    [  ~0   ~0   ~0   ~0  |  0.7  0.7  0.7  1.0 |  ~0   ~0   ~0   ~0 ]
veh0    [  ~0   ~0   ~0   ~0  |  ~0   ~0   ~0   ~0  |  1.0  0.7  0.7  0.7 ]
veh1    [  ~0   ~0   ~0   ~0  |  ~0   ~0   ~0   ~0  |  0.7  1.0  0.7  0.7 ]
veh2    [  ~0   ~0   ~0   ~0  |  ~0   ~0   ~0   ~0  |  0.7  0.7  1.0  0.7 ]
veh3    [  ~0   ~0   ~0   ~0  |  ~0   ~0   ~0   ~0  |  0.7  0.7  0.7  1.0 ]
```

The 4×4 intra-cluster diagonal blocks are uniform at 0.72; the 4×4
inter-cluster off-diagonal blocks are all ≪ 0.09. `compute_concept_gram`
in the compiler package produces this matrix exactly for this machine.

## Loaded feature |f> = |Paris> (single-concept load)

To keep the polysemy column directly readable as a **row of the Gram
matrix**, this example loads a single concept — `|Paris>` — as the
feature rather than a 4-way superposition. The polysemy column then
exposes the block structure in the clearest form:

| Query concept | Cluster  | P(|000>) analytic |
|---------------|----------|-------------------|
| Paris   (0)   | capitals | 1.000 (self)      |
| Tokyo   (1)   | capitals | 0.720             |
| London  (2)   | capitals | 0.720             |
| Berlin  (3)   | capitals | 0.720             |
| apple   (4)   | fruits   | 0.001             |
| banana  (5)   | fruits   | 0.007             |
| cherry  (6)   | fruits   | 0.001             |
| durian  (7)   | fruits   | 0.015             |
| car     (8)   | vehicles | 0.001             |
| boat    (9)   | vehicles | 0.007             |
| plane   (10)  | vehicles | 0.015             |
| rocket  (11)  | vehicles | 0.001             |

Three tiers: **1.0** (self), **0.72** (cluster-mates), **≲ 0.09**
(cross-cluster). Compare against `larql-polysemantic-12`'s flat 3/4 vs
1/3 two-tier structure with no intra-cluster signal: that example
demonstrates the parametric-action *mechanism*, this one demonstrates
the *clustered phenomenon*.

## Note on the multi-query circuit

As with `larql-polysemantic-12`, a single Qiskit circuit cannot simulate
all 12 queries together — each query's inverse-prepare + measure
destroys the feature state via measurement (no-cloning). The `.q.orca.md`
declares all 12 parametric call sites to publish the full signature
shape; `compile_to_qiskit` emits all 12 branches in BFS order. The
companion demo `demos/larql_polysemantic_clusters/demo.py` runs 12
independent prepare+query circuits to recover the polysemy column.

## context
| Field    | Type        | Default            |
|----------|-------------|--------------------|
| qubits   | list<qubit> | [q0, q1, q2]       |

## events
- load_feature
- query_paris
- query_tokyo
- query_london
- query_berlin
- query_apple
- query_banana
- query_cherry
- query_durian
- query_car
- query_boat
- query_plane
- query_rocket
- measure_done

## state idle [initial]
> 3-qubit concept register in `|000>`. No feature has been prepared.

## state feature_loaded
> `|f> = |Paris>` prepared via `prepare_concept(3.2, 0.4, 0.4)`.

## state queried_paris
> `query_concept(Paris)` applied — self-query. `P(|000>) = 1.000`.

## state queried_tokyo
> `query_concept(Tokyo)` applied — cluster-mate. `P(|000>) = 0.720`.

## state queried_london
> `query_concept(London)` applied — cluster-mate. `P(|000>) = 0.720`.

## state queried_berlin
> `query_concept(Berlin)` applied — cluster-mate. `P(|000>) = 0.720`.

## state queried_apple
> `query_concept(apple)` applied — cross-cluster. `P(|000>) ≲ 0.09`.

## state queried_banana
> `query_concept(banana)` applied — cross-cluster. `P(|000>) ≲ 0.09`.

## state queried_cherry
> `query_concept(cherry)` applied — cross-cluster. `P(|000>) ≲ 0.09`.

## state queried_durian
> `query_concept(durian)` applied — cross-cluster. `P(|000>) ≲ 0.09`.

## state queried_car
> `query_concept(car)` applied — cross-cluster. `P(|000>) ≲ 0.09`.

## state queried_boat
> `query_concept(boat)` applied — cross-cluster. `P(|000>) ≲ 0.09`.

## state queried_plane
> `query_concept(plane)` applied — cross-cluster. `P(|000>) ≲ 0.09`.

## state queried_rocket
> `query_concept(rocket)` applied — cross-cluster. `P(|000>) ≲ 0.09`.

## state done [final]
> Measurement collapsed the 3-qubit register to a classical bitstring.

## transitions
| Source          | Event         | Guard | Target           | Action                              |
|-----------------|---------------|-------|------------------|-------------------------------------|
| idle            | load_feature  |       | feature_loaded   | prepare_concept(3.2, 0.4, 0.4)      |
| feature_loaded  | query_paris   |       | queried_paris    | query_concept(3.2, 0.4, 0.4)    |
| feature_loaded  | query_tokyo   |       | queried_tokyo    | query_concept(3.2, -0.4, -0.4)  |
| feature_loaded  | query_london  |       | queried_london   | query_concept(2.4, 0.4, -0.4)   |
| feature_loaded  | query_berlin  |       | queried_berlin   | query_concept(2.4, -0.4, 0.4)   |
| feature_loaded  | query_apple   |       | queried_apple    | query_concept(0.4, 3.2, 0.4)    |
| feature_loaded  | query_banana  |       | queried_banana   | query_concept(0.4, 2.4, -0.4)   |
| feature_loaded  | query_cherry  |       | queried_cherry   | query_concept(-0.4, 3.2, -0.4)  |
| feature_loaded  | query_durian  |       | queried_durian   | query_concept(-0.4, 2.4, 0.4)   |
| feature_loaded  | query_car     |       | queried_car      | query_concept(0.4, 0.4, 3.2)    |
| feature_loaded  | query_boat    |       | queried_boat     | query_concept(0.4, -0.4, 2.4)   |
| feature_loaded  | query_plane   |       | queried_plane    | query_concept(-0.4, 0.4, 2.4)   |
| feature_loaded  | query_rocket  |       | queried_rocket   | query_concept(-0.4, -0.4, 3.2)  |
| queried_paris   | measure_done  |       | done             |                                     |
| queried_tokyo   | measure_done  |       | done             |                                     |
| queried_london  | measure_done  |       | done             |                                     |
| queried_berlin  | measure_done  |       | done             |                                     |
| queried_apple   | measure_done  |       | done             |                                     |
| queried_banana  | measure_done  |       | done             |                                     |
| queried_cherry  | measure_done  |       | done             |                                     |
| queried_durian  | measure_done  |       | done             |                                     |
| queried_car     | measure_done  |       | done             |                                     |
| queried_boat    | measure_done  |       | done             |                                     |
| queried_plane   | measure_done  |       | done             |                                     |
| queried_rocket  | measure_done  |       | done             |                                     |

## actions
| Name                | Signature                                  | Effect                                                           |
|---------------------|---------------------------------------------|------------------------------------------------------------------|
| prepare_concept     | (qs, a: angle, b: angle, c: angle) -> qs    | Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)                         |
| query_concept   | (qs, a: angle, b: angle, c: angle) -> qs    | Ry(qs[2], -c); Ry(qs[1], -b); Ry(qs[0], -a)                      |

## verification rules
- unitarity: Ry preserves norm; every transition evolves the 3-qubit register unitarily from `|000>`
- structured_non_orthogonality: intra-cluster `|<c_i|c_j>|² = 0.720` (uniform) and inter-cluster `|<c_i|c_j>|² < 0.10` — a block-structured Gram matrix, not a uniform cross-talk floor
- no_cloning: the prepared feature is not duplicated; each query needs a fresh prepare+query sequence (the demo runs 12 independent circuits)
- measurement_collapse_allowed: `done` is the intended collapse sink — each branch ends in measurement; analytic `P(|000>)` per query (1.000 self, 0.720 cluster-mate, ≲ 0.09 cross-cluster) is documented in the polysemy-scores table above
