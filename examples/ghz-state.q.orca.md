# machine GHZState

## context
| Field      | Type          | Default |
|------------|---------------|---------|
| qubits     | list<qubit>   |         |
| outcome    | int           | -1      |

## events
- init
- entangle_q1
- entangle_q2
- measure_done

## state |000>
> Three-qubit ground state

## state |+00> = (|0> + |1>)|00>/√2
> After Hadamard on first qubit

## state |Φ00_10> = (|000> + |100>)/√2
> Partially entangled after first CNOT

## state |GHZ> = (|000> + |111>)/√2
> Greenberger-Horne-Zeilinger state — maximally entangled

## state |000_result> [final]
> Collapsed to all zeros

## state |111_result> [final]
> Collapsed to all ones

## transitions
| Source       | Event         | Guard                  | Target        | Action            |
|--------------|---------------|------------------------|---------------|-------------------|
| |000>        | init          |                        | |+00>         | apply_H_q0        |
| |+00>        | entangle_q1   |                        | |Φ00_10>      | apply_CNOT_q0_q1  |
| |Φ00_10>     | entangle_q2   |                        | |GHZ>         | apply_CNOT_q0_q2  |
| |GHZ>        | measure_done  | prob_collapse('000')=0.5| |000_result>  | set_outcome_0    |
| |GHZ>        | measure_done  | prob_collapse('111')=0.5| |111_result>  | set_outcome_1    |

## guards
| Name                  | Expression                           |
|-----------------------|--------------------------------------|
| prob_collapse('000')  | fidelity(|GHZ>, |000>) ** 2 ≈ 0.5   |
| prob_collapse('111')  | fidelity(|GHZ>, |111>) ** 2 ≈ 0.5   |

## actions
| Name              | Signature     | Effect              |
|-------------------|---------------|----------------------|
| apply_H_q0        | (qs) -> qs    | Hadamard(qs[0])      |
| apply_CNOT_q0_q1  | (qs) -> qs    | CNOT(qs[0], qs[1])   |
| apply_CNOT_q0_q2  | (qs) -> qs    | CNOT(qs[0], qs[2])   |
| set_outcome_0     | (ctx) -> ctx  | ctx.outcome = 0      |
| set_outcome_1     | (ctx) -> ctx  | ctx.outcome = 1      |

## effects
| Name     | Input         | Output         |
|----------|---------------|----------------|
| collapse | state vector  | classical bits |

## verification rules
- unitarity: all gates preserve norm
- entanglement: GHZ state must have Schmidt rank >1
- completeness: all collapse branches covered
- no-cloning: no copy ops allowed
