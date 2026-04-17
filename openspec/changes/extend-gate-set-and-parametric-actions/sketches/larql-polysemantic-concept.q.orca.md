# machine LarqlPolysemanticConcept

Concept-projection lookup over polysemantic LARQL features.

A LARQL gate vector is rarely "about one thing" — sparse-autoencoder studies
of transformer FFNs (Elhage et al., "Toy Models of Superposition") show single
neurons firing for multiple semantically distinct concepts, packed
non-orthogonally into a low-dimensional feature space because the model needs
to compress more concepts than it has dimensions. This machine models the
quantum analogue: encode a polysemantic feature as a unit *vector* in a small
concept register, then "ask" whether it represents a specific concept by
inverting that concept's preparation unitary and measuring |0...0>.

This is the dual of the Grover gate-KNN demo. There, log2(N) qubits each named
one of N orthogonal feature *indices*. Here, only 2 qubits hold the feature
amplitude, and the concepts are *directions* in that 4-dim Hilbert space —
which can comfortably accommodate more than 2 (non-orthogonal) concepts.

Concrete instance (2-qubit concept register):

  |Paris>  = H(qs[0]) |00> = (|00> + |01>) / sqrt(2)
  |Tokyo>  = H(qs[1]) |00> = (|00> + |10>) / sqrt(2)
  <Paris|Tokyo> = 1/2     (non-orthogonal — the "superposition" geometry)

Polysemantic feature with equal Paris/Tokyo loading:

  |f>  = (|Paris> + |Tokyo>) / sqrt(3)
       = (1 / sqrt(6)) (2|00> + |01> + |10>)

Querying Paris: apply H(qs[0]) = U_Paris†, then measure.

  P(|00>) = |<Paris|f>|^2 = 3/4 = 0.75       (the "Paris polysemy score")

Cross-talk floor. A *monosemantic* Paris-only feature (|f> = |Paris>) scores
P(|00>) = 1.0 on Paris and P(|00>) = 1/2 on Tokyo (precisely |<Paris|Tokyo>|^2).
The Tokyo branch can never read 0% on a Paris feature — that floor of 1/2 is
the same overcomplete-dictionary cross-talk that classical sparse autoencoders
see when they try to disentangle features from a layer with concept count >
hidden dim. The quantum representation *is* the geometry.

## context
| Field    | Type        | Default            |
|----------|-------------|--------------------|
| qubits   | list<qubit> | [q0, q1]           |
| concept  | int         | 0                  |
| score    | int         | 0                  |

## events
- load_feature
- query_paris
- query_tokyo
- measure_done

## state idle [initial]
> 2-qubit concept register in |00>. No feature has been amplitude-encoded.

## state feature_loaded
> Polysemantic feature |f> = (1/sqrt(6))(2|00> + |01> + |10>) prepared in the
> register. Note that the marginal P(|00>) directly is 4/6 — the *concept*
> content is hidden in cross-terms with non-orthogonal concept basis vectors.

## state projected_paris
> H(qs[0]) = U_Paris† has been applied. Now P(|00>) = |<Paris|f>|^2 = 3/4.
> The polysemantic feature has a 75% Paris loading.

## state projected_tokyo
> Alternative branch on a freshly-prepared |f>: H(qs[1]) = U_Tokyo†.
> P(|00>) = |<Tokyo|f>|^2 = 3/4 (symmetric with Paris).

## state hit_paris [final]
> Measured |00> after the Paris projection. The feature represents Paris
> with the polysemy score above. Aggregating over many shots reproduces the
> continuous score.

## state miss_paris [final]
> Non-|00> outcome after the Paris projection. A miss for this single shot.

## state hit_tokyo [final]
> Measured |00> after the Tokyo projection. The feature represents Tokyo.

## state miss_tokyo [final]
> Non-|00> outcome after the Tokyo projection.

## transitions
| Source           | Event         | Guard          | Target           | Action                |
|------------------|---------------|----------------|------------------|-----------------------|
| idle             | load_feature  |                | feature_loaded   | prepare_polysemantic  |
| feature_loaded   | query_paris   |                | projected_paris  | apply_paris_inverse   |
| feature_loaded   | query_tokyo   |                | projected_tokyo  | apply_tokyo_inverse   |
| projected_paris  | measure_done  | concept_fires  | hit_paris        | record_paris          |
| projected_paris  | measure_done  | !concept_fires | miss_paris       | record_miss           |
| projected_tokyo  | measure_done  | concept_fires  | hit_tokyo        | record_tokyo          |
| projected_tokyo  | measure_done  | !concept_fires | miss_tokyo       | record_miss           |

## guards
| Name          | Expression                              |
|---------------|-----------------------------------------|
| concept_fires | fidelity(register, |00>) ** 2 > 0.5     |

## actions
| Name                  | Signature    | Effect                                                                                              |
|-----------------------|--------------|-----------------------------------------------------------------------------------------------------|
| prepare_polysemantic  | (qs) -> qs   | Ry(0.8411)(qs[1]); X(qs[1]); CRy(0.9273)(qs[1], qs[0]); X(qs[1])                                    |
| apply_paris_inverse   | (qs) -> qs   | Hadamard(qs[0])                                                                                     |
| apply_tokyo_inverse   | (qs) -> qs   | Hadamard(qs[1])                                                                                     |
| record_paris          | (ctx) -> ctx | ctx.concept = 1; ctx.score = 75                                                                     |
| record_tokyo          | (ctx) -> ctx | ctx.concept = 2; ctx.score = 75                                                                     |
| record_miss           | (ctx) -> ctx | ctx.concept = 0; ctx.score = 0                                                                      |

## verification rules
- unitarity: Ry, CRy, Hadamard, X all preserve norm; the feature register is
  unitarily evolved through prep + projection
- non_orthogonality: the encoded concept vectors satisfy 0 < |<Paris|Tokyo>| < 1,
  so a monosemantic Paris feature still leaks 50% probability into the Tokyo
  query — cross-talk is intrinsic to the representation, not a defect
- completeness: both branches (concept hit, concept miss) are explicit terminal
  states for both queries
- no_cloning: |f> is not duplicated; querying both Paris and Tokyo requires two
  re-preparations from the classical description of the feature
