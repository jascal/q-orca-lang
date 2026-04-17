# machine LarqlGateKnnGrover

Grover-amplified gate-KNN lookup, the per-layer kernel of LARQL inference.

In LARQL, every transformer layer holds N FFN feature gate vectors (~10K
in Gemma 3 4B). The classical gate_knn() does N inner products to find the
top match. This machine models the quantum replacement: amplitude-encode
the residual stream as a query, mark gate vectors above a threshold via a
phase oracle, and amplify the marked indices with Grover diffusion.
Theoretical speedup O(N) -> O(sqrt(N)).

This instance uses 4 index qubits (N=16 features) with the marked feature
at index 10 = bitstring 1010 = the (France, capital, Paris) edge in the
LARQL frame. The optimal Grover iteration count for N=16, M=1 is
floor(pi/4 * sqrt(16)) = 3, after which P(target) > 96%.

## context
| Field    | Type        | Default              |
|----------|-------------|----------------------|
| qubits   | list<qubit> | [q0, q1, q2, q3]     |
| outcome  | int         | -1                   |

## events
- load_query
- oracle_mark
- diffuse
- measure_done

## state idle [initial]
> All 4 index qubits in |0>. Classical residual stream query has not yet been
> amplitude-encoded. In LARQL terms: this is the moment before gate_knn() is
> called for the current layer.

## state uniform
> Index register in equal superposition over N=16 feature indices, each with
> amplitude 1/4 = 1/sqrt(N). The oracle now sees all 16 candidate gate
> vectors at once.

## state marked_iter1
> Phase oracle U_f has flipped the amplitude of |1010> (feature index 10, the
> France->Paris gate vector). Marked-state probability still 1/16 -- only the
> phase carries information.

## state amplified_iter1
> First Grover diffusion. P(|1010>) ~ 47%.

## state marked_iter2
> Oracle 2 has flipped |1010> again (re-marked relative to the new mean).

## state amplified_iter2
> Second diffusion. P(|1010>) ~ 91%.

## state marked_iter3
> Oracle 3 -- final marking before convergence.

## state amplified_iter3
> Third diffusion. P(|1010>) > 96%. Optimal stopping point for N=16, M=1.

## state hit_france_paris [final]
> Measurement collapsed to |1010> = feature index 10. The KNN query recovered
> the France->Paris edge in 3 oracle calls vs 16 classical inner products.

## state hit_other [final]
> Measurement collapsed to a non-marked index (probability < 4% on a clean
> simulator). Branch exists for completeness on noisy hardware.

## transitions
| Source            | Event        | Guard         | Target            | Action             |
|-------------------|--------------|---------------|-------------------|--------------------|
| idle              | load_query   |               | uniform           | apply_hadamards    |
| uniform           | oracle_mark  |               | marked_iter1      | apply_phase_oracle |
| marked_iter1      | diffuse      |               | amplified_iter1   | apply_diffusion    |
| amplified_iter1   | oracle_mark  |               | marked_iter2      | apply_phase_oracle |
| marked_iter2      | diffuse      |               | amplified_iter2   | apply_diffusion    |
| amplified_iter2   | oracle_mark  |               | marked_iter3      | apply_phase_oracle |
| marked_iter3      | diffuse      |               | amplified_iter3   | apply_diffusion    |
| amplified_iter3   | measure_done | prob_target   | hit_france_paris  | record_target      |
| amplified_iter3   | measure_done | !prob_target  | hit_other         | record_other       |

## guards
| Name        | Expression                                    |
|-------------|-----------------------------------------------|
| prob_target | fidelity(amplified_iter3, |1010>) ** 2 > 0.96 |

## actions
| Name               | Signature    | Effect                                                                                                                                                                                                                                                                                                              |
|--------------------|--------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| apply_hadamards    | (qs) -> qs   | Hadamard(qs[0]); Hadamard(qs[1]); Hadamard(qs[2]); Hadamard(qs[3])                                                                                                                                                                                                                                                  |
| apply_phase_oracle | (qs) -> qs   | X(qs[0]); X(qs[2]); MCZ(qs[0], qs[1], qs[2], qs[3]); X(qs[0]); X(qs[2])                                                                                                                                                                                                                                             |
| apply_diffusion    | (qs) -> qs   | Hadamard(qs[0]); Hadamard(qs[1]); Hadamard(qs[2]); Hadamard(qs[3]); X(qs[0]); X(qs[1]); X(qs[2]); X(qs[3]); MCZ(qs[0], qs[1], qs[2], qs[3]); X(qs[0]); X(qs[1]); X(qs[2]); X(qs[3]); Hadamard(qs[0]); Hadamard(qs[1]); Hadamard(qs[2]); Hadamard(qs[3])                                                              |
| record_target      | (ctx) -> ctx | ctx.outcome = 10                                                                                                                                                                                                                                                                                                    |
| record_other       | (ctx) -> ctx | ctx.outcome = -1                                                                                                                                                                                                                                                                                                    |

## verification rules
- unitarity: Hadamard, X, and MCZ are all unitary; the index-register norm is preserved at every step
- completeness: both measurement branches (target hit, target miss) have explicit transitions
- no_cloning: the query register's amplitudes are read coherently by the oracle and never duplicated into a second register
