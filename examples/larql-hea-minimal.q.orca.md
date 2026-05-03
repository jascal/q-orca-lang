# machine LarqlHeaMinimal

> Rung-2 hardware-efficient ansatz (HEA) example. Three concepts on
> a 3-qubit register, prepared by a depth-3 ring-entangler HEA with
> rotation set `(Ry, Rz)`. The `## encoding` and `## theta` sections
> declare the ansatz shape and per-concept parameter tensors
> explicitly, rather than relying on effect-string pattern detection
> as the rung-1 `larql-polysemantic-hierarchical` example does.
>
> Concepts `a` and `b` share a sub-cluster (small, near-identical
> rotations); `c` is the cross-cluster outsider (large rotations
> centered around 1 rad). Analytic `|<c_i | c_j>|²` from
> `compute_concept_gram_hea`:
>
> ```
>      a       b       c
> a [ 1.0000  0.9999  0.3837 ]
> b [ 0.9999  1.0000  0.3832 ]
> c [ 0.3837  0.3832  1.0000 ]
> ```
>
> Tier separation:
> - sub-cluster (a–b): 0.9999
> - cross max (a–c, b–c): 0.3837
> - sub→cross gap: 0.6162  (well above the Stage 4b consistency
>   tolerance `HEA_TIER_TOLERANCE = 0.025`).
>
> The example compiles via the standard parse → verify path. QASM /
> Qiskit emit for HEA-encoded machines is out of scope for
> `add-rung2-hea-encoding`; the analytic Gram is built directly via
> `compute_concept_gram_hea`.
>
> **Pairing convention** — `compute_concept_gram_hea` pairs the
> `query_concept` call sites in the `## transitions` table with the
> rows of `## theta` *positionally, in declaration order*. Call site
> `i` is built from `theta.rows[i]`. The `concept` column in the
> theta block is a human-readable label only — it is **not** matched
> against transition events. Reordering the theta rows without also
> reordering the matching transitions silently changes the produced
> Gram, so keep the two tables aligned by row order.

## context
| Field  | Type        | Default          |
|--------|-------------|------------------|
| qubits | list<qubit> | [q0, q1, q2]     |

## events
- prep_a
- prep_b
- prep_c

## state idle [initial]
> Ground state of the 3-qubit register, before any concept preparation.

## state queried_a [final]
> Register holds concept `a` — sub-cluster member.

## state queried_b [final]
> Register holds concept `b` — sub-cluster member, near-identical to `a`.

## state queried_c [final]
> Register holds concept `c` — cross-cluster outsider.

## transitions
| Source | Event  | Guard | Target      | Action        |
|--------|--------|-------|-------------|---------------|
| idle   | prep_a |       | queried_a   | query_concept |
| idle   | prep_b |       | queried_b   | query_concept |
| idle   | prep_c |       | queried_c   | query_concept |

## actions
| Name          | Signature   |
|---------------|-------------|
| query_concept | (qs) -> qs  |

## encoding
| key       | value  |
|-----------|--------|
| kind      | hea    |
| depth     | 3      |
| entangler | ring   |
| rotations | Ry, Rz |

## theta
| concept | tensor |
|---------|--------|
| a | [[[0.0457, -0.156, 0.1126], [0.1411, -0.2927, -0.1953], [0.0192, -0.0474, -0.0025]], [[-0.128, 0.1319, 0.1167], [0.0099, 0.1691, 0.0701], [-0.1289, 0.0553, -0.1438]]] |
| b | [[[0.0371, -0.1427, 0.1124], [0.1371, -0.2968, -0.2004], [0.0205, -0.0395, -0.0065]], [[-0.1315, 0.1363, 0.117], [0.0191, 0.1578, 0.0783], [-0.1294, 0.0523, -0.1584]]] |
| c | [[[1.2682, 1.0909, 1.0102], [0.8841, 1.1853, 0.9248], [0.7295, 0.9307, 0.6622]], [[1.1194, 0.9863, 1.2396], [0.9105, 1.0324, 1.1632], [1.243, 0.9765, 0.9332]]] |
