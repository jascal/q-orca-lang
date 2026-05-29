# machine BellEntanglerAsserts

> Bell-pair preparation with runtime state-category assertions. Demonstrates
> `[assert: …]` annotations checked by the Stage-4b assertion verifier:
> superposition after the Hadamard, entanglement after the CNOT.

## context
| Field      | Type          | Default          |
|------------|---------------|------------------|
| qubits     | list<qubit>   | [q0, q1]         |
| outcome    | int           | -1               |

## events
- prepare_H
- entangle
- measure_done

## state |00> [initial]
> Ground state, no entanglement yet

## state |+0> = (|00> + |10>)/√2 [assert: superposition(qs[0])]
> After Hadamard on qubit 0 — qubit 0 is in a Z-basis superposition.

## state |ψ> = (|00> + |11>)/√2 [assert: entangled(qs[0], qs[1])]
> Bell state after Hadamard + CNOT — qubits 0 and 1 are entangled.

## state |00_collapsed> [final]
> Collapsed to |00> after measurement

## state |11_collapsed> [final]
> Collapsed to |11> after measurement

## transitions
| Source          | Event        | Guard                  | Target              | Action                  |
|-----------------|--------------|------------------------|---------------------|-------------------------|
| |00>            | prepare_H    |                        | |+0>                | apply_H_on_q0           |
| |+0>            | entangle     |                        | |ψ>                 | apply_CNOT_q0_to_q1     |
| |ψ>             | measure_done | prob_collapse('00')=0.5| |00_collapsed>       | set_outcome_0           |
| |ψ>             | measure_done | prob_collapse('11')=0.5| |11_collapsed>       | set_outcome_1           |

## guards
| Name                | Expression          |
|---------------------|---------------------|
| prob_collapse('00') | prob('00') ≈ 0.5    |
| prob_collapse('11') | prob('11') ≈ 0.5    |

## actions
| Name                | Signature                          | Effect                     |
|---------------------|------------------------------------|----------------------------|
| apply_H_on_q0       | (qs) -> qs                         | Hadamard(qs[0])            |
| apply_CNOT_q0_to_q1 | (qs) -> qs                         | CNOT(qs[0], qs[1])         |
| set_outcome_0       | (ctx) -> Context                   | ctx.outcome = 0            |
| set_outcome_1       | (ctx) -> Context                   | ctx.outcome = 1            |

## verification rules
- unitarity: all gates preserve norm
- entanglement: final state must have Schmidt rank >1 before measure
- completeness: all possible collapses covered (no missing branches)
- no_cloning: no copy ops allowed
- state_assertions: sample-check the superposition and entanglement claims at the annotated states

## assertion policy
| Setting           | Value | Notes                          |
|-------------------|-------|--------------------------------|
| shots_per_assert  | 256   | small for fast CI              |
| confidence        | 0.99  | Wilson-interval level          |
| on_failure        | error | fail verification on mismatch  |
