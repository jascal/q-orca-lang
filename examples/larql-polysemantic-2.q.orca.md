# machine LarqlPolysemantic2

Concept-projection lookup over 2 non-orthogonal LARQL features (Paris, Tokyo),
using a single parametric action to stamp out both query call sites.

This is the minimum-interesting polysemy machine: 2-qubit concept register,
2 concepts that overlap at 1/2, parametric `query_concept(c: int)`. It is
the structural sibling of `larql-polysemantic-12.q.orca.md` — same parametric
action template, same cross-talk mechanism, smaller number of call sites so
the whole circuit fits on one screen.

The motivation is the toy-models-of-superposition picture of FFN neurons
firing for multiple concepts packed into a low-dim feature space (Elhage
et al.). Each concept is a unit vector in the register's Hilbert space;
queries apply the inverse of that concept's preparation and measure `|00>`.

## Concept geometry

Concept `c ∈ {0, 1}` is defined by `U_c = Hadamard(qs[c])`:

    |concept_0> = Hadamard(qs[0]) |00> = (|00> + |01>) / √2    ("Paris")
    |concept_1> = Hadamard(qs[1]) |00> = (|00> + |10>) / √2    ("Tokyo")
    <concept_0 | concept_1> = 1/2                            (non-orthogonal)

## Polysemantic feature

|f> loads both concepts with equal amplitude:

    |f>  =  (|concept_0> + |concept_1>) / √3
         =  (1/√6) (2|00> + |01> + |10>)

Prep realizes (2|00> + |01> + |10>)/√6 on (q0, q1) via
`Ry(q1, 0.8411); X(q1); CRy(q1, q0, 0.9273); X(q1)`.
Angles are `2·arctan(1/√5) ≈ 0.8411` and `2·arctan(1/2) ≈ 0.9273`.

## Polysemy scores (analytic)

| Query concept c | P(|00>) |
|-----------------|---------|
| c = 0 (Paris)   | 3/4     |
| c = 1 (Tokyo)   | 3/4     |

Both "in" — symmetric loading makes both scores equal. A monosemantic
Paris-only feature (|f> = |concept_0>) would instead score 1.0 on Paris
and 1/2 on Tokyo (the pairwise overlap squared). That 1/2 floor is the
cross-talk sparse autoencoders see when concept count exceeds hidden dim.

## context
| Field  | Type        | Default  |
|--------|-------------|----------|
| qubits | list<qubit> | [q0, q1] |

## events
- load_feature
- measure_done
- query_c0
- query_c1

## state idle [initial]
> 2-qubit concept register in `|00>`. No feature has been amplitude-encoded.

## state feature_loaded
> Polysemantic feature `|f> = (|concept_0> + |concept_1>)/√3` prepared on
> (q0, q1). Marginal `P(|00>)` is 4/6 ≈ 66.7%.

## state queried_c0
> `Hadamard(q0)` applied — projection onto concept 0 (Paris).
> `P(|00>) = 3/4`.

## state queried_c1
> `Hadamard(q1)` applied — projection onto concept 1 (Tokyo).
> `P(|00>) = 3/4`.

## state done [final]
> Measurement collapsed the register to a classical 2-bit string. Decoding
> `|00>` vs other outcomes gives the polysemy score for the queried concept.

## transitions
| Source         | Event        | Guard                        | Target        | Action                |
|----------------|--------------|------------------------------|---------------|-----------------------|
| idle           | load_feature |                              | feature_loaded| prepare_polysemantic  |
| feature_loaded | query_c0     |                              | queried_c0    | query_concept(0)      |
| feature_loaded | query_c1     |                              | queried_c1    | query_concept(1)      |
| queried_c0     | measure_done | prob_collapse('00')=0.75     | done          |                       |
| queried_c1     | measure_done | prob_collapse('00')=0.75     | done          |                       |

## guards
| Name                | Expression                                                          |
|---------------------|---------------------------------------------------------------------|
| prob_collapse('00') | P(|00>) = 3/4 per query (symmetric loading of both concepts into    |
|                     | the feature); guards annotate the expected marked outcome only.     |

## actions
| Name                 | Signature          | Effect                                                              |
|----------------------|--------------------|---------------------------------------------------------------------|
| prepare_polysemantic | (qs) -> qs         | Ry(qs[1], 0.8411); X(qs[1]); CRy(qs[1], qs[0], 0.9273); X(qs[1])    |
| query_concept        | (qs, c: int) -> qs | Hadamard(qs[c])                                                     |

## verification rules
- unitarity: Ry, X, CRy, and Hadamard all preserve norm
- non_orthogonality: `|<concept_0 | concept_1>| = 1/2`
- no_cloning: |f> is not duplicated; each query needs a fresh preparation
