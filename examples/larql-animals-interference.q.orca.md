# machine LarqlAnimalsInterference

Phase-knob interference companion to `larql-animals-hierarchy.q.orca.md`.
Same 4-concept structure (2 sub-clusters × 2 within-cluster siblings)
on a 3-qubit register, but here the within-cluster axis is collapsed
to a single γ value and the *phase knob* `Rz(qs[1], phi)` distinguishes
the two siblings of each cluster. This exercises the matcher extension
from `extend-mps-matcher-rz-phases`: the analytic Gram helper
`compute_concept_gram_mps` recognizes optional `Rz` rotations anywhere
in the staircase as 1-qubit interference knobs that preserve the
bond-2 MPS structure.

## Concept geometry

Each concept is prepared as the bond-2 MPS

    |c_i> = Ry(q0, α) CNOT(q0, q1) Ry(q1, α + β) Rz(q1, φ)
            CNOT(q1, q2) Ry(q2, β + γ) |000>

with α = γ = 0, β ∈ {-0.5, +0.5}, φ ∈ {0, π/2}:

| i | concept           | sub-cluster | (α, β, γ, φ)      |
|---|-------------------|-------------|--------------------|
| 0 | dog_at_rest       | dogs        | (0, -0.5, 0, 0)    |
| 1 | dog_in_motion     | dogs        | (0, -0.5, 0, π/2)  |
| 2 | bird_at_rest      | birds       | (0,  0.5, 0, 0)    |
| 3 | bird_in_motion    | birds       | (0,  0.5, 0, π/2)  |

The β axis carves the spatial sub-cluster (dogs vs birds, as before);
the φ axis is a *purely phase-driven* sibling distinction, with no
counterpart in rung-0 product states. The four off-diagonal Gram
entries fall in three ordered tiers:

| tier                            | members                                                      | analytic \|<c_i\|c_j>\|² |
|---------------------------------|--------------------------------------------------------------|--------------------------|
| same-cluster, φ-shifted         | (dog_at_rest, dog_in_motion), (bird_at_rest, bird_in_motion) | 0.8851                   |
| cross-cluster, φ-mismatched     | (dog_at_rest, bird_in_motion), (dog_in_motion, bird_at_rest) | 0.6816                   |
| cross-cluster, φ-matched        | (dog_at_rest, bird_at_rest), (dog_in_motion, bird_in_motion) | 0.5931                   |

Two observations worth highlighting:

- **The φ-matched cross-cluster pairs (0.5931) coincide with the
  φ-knob-off baseline.** This is exactly the rung-1 product-state
  cosine for `cos((β_dog - β_bird) / 2)² = cos(0.5)² ≈ 0.5931`. When
  φ matches across the pair, `Rz(q1, φ)` cancels in the inner product.
- **The same-cluster pairs (0.8851) and the φ-mismatched cross-cluster
  pairs (0.6816) are *both* phase-driven.** Without the `Rz`, all four
  off-diagonals would collapse to two values — siblings within a
  cluster would be identical, cross-cluster would be 0.5931.

The φ knob is therefore an *additional* interference axis on top of
the cross-coupled angle structure, not a replacement for it. Compare
with `larql-animals-hierarchy.q.orca.md`, which uses the γ axis (a
real-rotation knob via `Ry(q2, β + γ)`) to differentiate siblings —
that example produces four distinct off-diagonal values; this one
produces three. Stacking both knobs (real γ + phase φ) is the natural
follow-up and is left as an exercise.

## Note on the analytic helper convention

This example enumerates **4 call sites of `prepare_concept`** (rather
than the load-feature + 4-query pattern of `larql-animals-hierarchy.q.orca.md`).
Reason: `compute_concept_gram_mps` builds the concept states by
applying the named action's effect to `|000>`, and only the
preparation form `U_prep |000>` produces the intended `|c_i>` when an
`Rz` interference knob sits between `Ry` and `CNOT` segments. The
inverse-query form `U_prep^† |000>` would put the `Rz` ahead of the
qubit rotation that gives it bite, collapsing it to a global phase;
the helper would then return an unphysical "all-1.0" Gram on the
phi-only axis. The `larql-animals-hierarchy.q.orca.md` example can
use the inverse form because its pure-`Ry` cross-coupled staircase
keeps the Gram magnitude invariant under the prep / inverse swap;
once `Rz` enters the staircase that invariance breaks, and the prep
form becomes the canonical path.

## context
| Field    | Type        | Default            |
|----------|-------------|--------------------|
| qubits   | list<qubit> | [q0, q1, q2]       |

## events
- prepare_dog_at_rest
- prepare_dog_in_motion
- prepare_bird_at_rest
- prepare_bird_in_motion
- measure_done

## state idle [initial]
> 3-qubit concept register in `|000>`. No concept has been prepared.

## state prepared_dog_at_rest
> `|c_0> = prepare_concept(0, -0.5, 0, 0) |000>`. Dogs cluster, φ = 0.

## state prepared_dog_in_motion
> `|c_1> = prepare_concept(0, -0.5, 0, π/2) |000>`. Dogs cluster, φ = π/2.

## state prepared_bird_at_rest
> `|c_2> = prepare_concept(0, 0.5, 0, 0) |000>`. Birds cluster, φ = 0.

## state prepared_bird_in_motion
> `|c_3> = prepare_concept(0, 0.5, 0, π/2) |000>`. Birds cluster, φ = π/2.

## state done [final]
> Measurement collapsed the 3-qubit register to a classical bitstring.

## transitions
| Source                    | Event                   | Guard | Target                     | Action                                       |
|---------------------------|-------------------------|-------|----------------------------|----------------------------------------------|
| idle                      | prepare_dog_at_rest     |       | prepared_dog_at_rest       | prepare_concept(0.0, -0.5, 0.0, 0.0)         |
| idle                      | prepare_dog_in_motion   |       | prepared_dog_in_motion     | prepare_concept(0.0, -0.5, 0.0, 1.5707963)   |
| idle                      | prepare_bird_at_rest    |       | prepared_bird_at_rest      | prepare_concept(0.0,  0.5, 0.0, 0.0)         |
| idle                      | prepare_bird_in_motion  |       | prepared_bird_in_motion    | prepare_concept(0.0,  0.5, 0.0, 1.5707963)   |
| prepared_dog_at_rest      | measure_done            |       | done                       |                                              |
| prepared_dog_in_motion    | measure_done            |       | done                       |                                              |
| prepared_bird_at_rest     | measure_done            |       | done                       |                                              |
| prepared_bird_in_motion   | measure_done            |       | done                       |                                              |

## actions
| Name            | Signature                                                     | Effect                                                                                                            |
|-----------------|---------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| prepare_concept | (qs, a: angle, b: angle, c: angle, phi: angle) -> qs          | Ry(qs[0], a); CNOT(qs[0], qs[1]); Ry(qs[1], a + b); Rz(qs[1], phi); CNOT(qs[1], qs[2]); Ry(qs[2], b + c)          |

## verification rules
- unitarity: Ry, Rz, and CNOT preserve norm; every transition evolves the 3-qubit register unitarily from `|000>`
- mps_bond_2_with_phase_knob: each concept is prepared as a bond-2 MPS via the staircase with cross-coupled angles AND an `Rz(qs[1], phi)` phase rotation between the second `Ry` and the second `CNOT` — the matcher accepts optional `Rz` gates anywhere in the staircase as 1-qubit interference knobs that preserve χ = 2 (`Rz` is 1-qubit, Schmidt rank unchanged)
- phase_knob_overlap_tiers: three off-diagonal tiers — same-cluster φ-shift 0.8851 > cross-cluster φ-mismatched 0.6816 > cross-cluster φ-matched 0.5931 — strictly ordered; the matched-φ cross-cluster value coincides with the rung-1 product-state cosine `cos(0.5)² ≈ 0.5931` (the `Rz` factor cancels when φ agrees)
- measurement_collapse_allowed: `done` is the intended collapse sink — each prepared-concept branch ends in measurement
