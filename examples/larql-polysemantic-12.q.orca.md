# machine LarqlPolysemantic12

Concept-projection lookup over 12 non-orthogonal LARQL features, using a single
parametric action to stamp out all 12 query call sites from one template.

This is the direct generalization of the 2-concept polysemantic sketch in
`openspec/changes/extend-gate-set-and-parametric-actions/sketches/`. The
motivation is the same — sparse-autoencoder studies of transformer FFNs
(Elhage et al., "Toy Models of Superposition") show single neurons firing for
multiple semantically distinct concepts, packed non-orthogonally into a
low-dimensional feature space. We model the quantum analogue: encode each
concept as a unit vector via a single-qubit rotation, prepare a polysemantic
feature that linearly combines a few concepts, then "ask" whether the feature
loads a given concept by inverting that concept's preparation unitary and
measuring `|0^12>`.

## Concept geometry (12 concepts, 12-qubit register)

Concept `c ∈ {0, ..., 11}` is defined by the preparation unitary
`U_c = Hadamard(qs[c])`, acting on the 12-qubit product ground state `|0^12>`:

    |concept_c> = Hadamard(qs[c]) |0^12>
               = |0>^c ⊗ (|0>+|1>)/√2 ⊗ |0>^(11-c)

The concept vectors are non-orthogonal. For distinct `i ≠ j`:

    <concept_i | concept_j> = 1/2

so the 12×12 Gram matrix is `G = I + (J-I)/2`, i.e. ones on the diagonal and
1/2 off-diagonal. This is the "overcomplete dictionary" cross-talk floor that
classical sparse autoencoders see when feature count exceeds hidden dim —
querying a concept not in the feature still gets 1/3 probability of `|0^12>`
(derivation below).

## Polysemantic feature (loading concepts 0 and 1)

The feature |f> loads concepts 0 ("Paris") and 1 ("Tokyo") with equal
amplitude:

    |f>  =  (|concept_0> + |concept_1>) / N,     N = √(2 + 2·<c0|c1>) = √3
         =  (1/√6) (2·|0^12> + |q0=1 only> + |q1=1 only>)

Preparing |f> factors through (q0, q1) — the other ten qubits stay in |0>.
On the 2-qubit subspace, the prepared state is

    (2|00> + |01> + |10>) / √6

which the prep action below realizes with `Ry(q1, 0.8411)` + `X(q1)` +
`CRy(q1, q0, 0.9273)` + `X(q1)`. The angles are `2·arctan(1/√5) ≈ 0.8411`
and `2·arctan(1/2) ≈ 0.9273`.

## Polysemy scores (analytic predictions)

Querying concept `c` on |f> means: apply `U_c† = Hadamard(qs[c])`, then measure.
The polysemy score is `P(|0^12>) = |<concept_c | f>|^2`:

| Query concept c | <concept_c | f>                 | P(|0^12>) |
|-----------------|----------------------------------|-----------|
| c = 0 (in)      | (1 + <c0|c1>) / √3 = √3/2        | 3/4       |
| c = 1 (in)      | (<c1|c0> + 1) / √3 = √3/2        | 3/4       |
| c = 2..11 (out) | (<cX|c0> + <cX|c1>) / √3 = 1/√3  | 1/3       |

So the demo should see ≈ 75% on concepts 0, 1 and ≈ 33.3% on concepts 2..11.
The 1/3 floor is the cross-talk — a direct consequence of pairwise overlap 1/2
between concept vectors, independent of which concepts the feature loads.

## Note on the single-circuit simulation

Querying all 12 concepts sequentially in one circuit does not reproduce the
per-concept polysemy scores, because each query destroys |f> via measurement
(no-cloning). The `.q.orca.md` below branches 12 queries off `feature_loaded`
to declare the full 12-call-site shape the parametric action expands to, and
`compile_to_qiskit` emits a well-formed script covering every branch. The
companion demo (`demos/larql_polysemantic_12/demo.py`) runs 12 independent
single-query simulations to recover the table above.

## context
| Field    | Type        | Default                                                      |
|----------|-------------|--------------------------------------------------------------|
| qubits   | list<qubit> | [q0, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, q11]           |

## events
- load_feature
- measure_done
- query_c0
- query_c1
- query_c2
- query_c3
- query_c4
- query_c5
- query_c6
- query_c7
- query_c8
- query_c9
- query_c10
- query_c11

## state idle [initial]
> 12-qubit concept register in `|0^12>`. No feature has been amplitude-encoded.

## state feature_loaded
> Polysemantic feature `|f> = (|concept_0> + |concept_1>)/√3` is prepared on
> (q0, q1); q2..q11 remain in `|0>`. The marginal `P(|0^12>)` is 4/6 ≈ 66.7% —
> the concept content is hidden in cross-terms with the non-orthogonal concept
> basis.

## state queried_c0
> `Hadamard(q0)` applied — projection onto concept 0 (Paris). `P(|0^12>) = 3/4`.

## state queried_c1
> `Hadamard(q1)` applied — projection onto concept 1 (Tokyo). `P(|0^12>) = 3/4`.

## state queried_c2
> `Hadamard(q2)` applied — projection onto concept 2 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c3
> `Hadamard(q3)` applied — projection onto concept 3 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c4
> `Hadamard(q4)` applied — projection onto concept 4 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c5
> `Hadamard(q5)` applied — projection onto concept 5 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c6
> `Hadamard(q6)` applied — projection onto concept 6 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c7
> `Hadamard(q7)` applied — projection onto concept 7 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c8
> `Hadamard(q8)` applied — projection onto concept 8 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c9
> `Hadamard(q9)` applied — projection onto concept 9 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c10
> `Hadamard(q10)` applied — projection onto concept 10 (cross-talk). `P(|0^12>) = 1/3`.

## state queried_c11
> `Hadamard(q11)` applied — projection onto concept 11 (cross-talk). `P(|0^12>) = 1/3`.

## state done [final]
> Measurement collapsed the register to a classical 12-bit string. Decoding
> `|0^12>` vs other outcomes gives the per-concept polysemy score in the demo.

## transitions
| Source         | Event        | Guard                              | Target        | Action                 |
|----------------|--------------|------------------------------------|---------------|------------------------|
| idle           | load_feature |                                    | feature_loaded| prepare_polysemantic   |
| feature_loaded | query_c0     |                                    | queried_c0    | query_concept(0)       |
| feature_loaded | query_c1     |                                    | queried_c1    | query_concept(1)       |
| feature_loaded | query_c2     |                                    | queried_c2    | query_concept(2)       |
| feature_loaded | query_c3     |                                    | queried_c3    | query_concept(3)       |
| feature_loaded | query_c4     |                                    | queried_c4    | query_concept(4)       |
| feature_loaded | query_c5     |                                    | queried_c5    | query_concept(5)       |
| feature_loaded | query_c6     |                                    | queried_c6    | query_concept(6)       |
| feature_loaded | query_c7     |                                    | queried_c7    | query_concept(7)       |
| feature_loaded | query_c8     |                                    | queried_c8    | query_concept(8)       |
| feature_loaded | query_c9     |                                    | queried_c9    | query_concept(9)       |
| feature_loaded | query_c10    |                                    | queried_c10   | query_concept(10)      |
| feature_loaded | query_c11    |                                    | queried_c11   | query_concept(11)      |
| queried_c0     | measure_done | prob_collapse('0'*12)=0.75         | done          |                        |
| queried_c1     | measure_done | prob_collapse('0'*12)=0.75         | done          |                        |
| queried_c2     | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c3     | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c4     | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c5     | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c6     | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c7     | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c8     | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c9     | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c10    | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |
| queried_c11    | measure_done | prob_collapse('0'*12)=0.333        | done          |                        |

## guards
| Name                  | Expression                                                              |
|-----------------------|-------------------------------------------------------------------------|
| prob_collapse('0'*12) | P(|0^12>) per query; 0.75 for in-feature concepts (c0, c1), 1/3 for     |
|                       | cross-talk concepts (c2..c11). Guards annotate the expected marked      |
|                       | outcome only; the "any other outcome" branch is implicit in `done`.     |

## actions
| Name                 | Signature          | Effect                                                              |
|----------------------|--------------------|---------------------------------------------------------------------|
| prepare_polysemantic | (qs) -> qs         | Ry(qs[1], 0.8411); X(qs[1]); CRy(qs[1], qs[0], 0.9273); X(qs[1])    |
| query_concept        | (qs, c: int) -> qs | Hadamard(qs[c])                                                     |

## verification rules
- unitarity: Ry, X, CRy, and Hadamard all preserve norm; every transition
  evolves the 12-qubit register unitarily from `|0^12>`
- non_orthogonality: `|<concept_i | concept_j>| = 1/2 for i ≠ j`, so every
  off-diagonal Gram entry sits on the cross-talk floor
- no_cloning: |f> is not duplicated; the 12 queries each require a fresh
  preparation from the classical description of the feature (the demo
  reifies this by running 12 independent circuits)
