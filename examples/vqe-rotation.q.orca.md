# machine VqeRotation

## context
| Field   | Type        | Default              |
|---------|-------------|----------------------|
| qubits  | list<qubit> | [q0]                 |
| theta   | float       | 0.7853981633974483   |
| outcome | int         | -1                   |

## events
- rotate
- read_out
- collapse

## state |0> [initial]
> Single qubit ground state

## state |θ> = cos(π/8)|0> - i·sin(π/8)|1>
> Qubit after Rx(π/4) rotation — superposition

## state |measuring>
> Readout in progress

## state |0_result> [final]
> Measured outcome 0

## state |1_result> [final]
> Measured outcome 1

## transitions
| Source      | Event    | Guard               | Target      | Action     |
|-------------|----------|---------------------|-------------|------------|
| |0>         | rotate   |                     | |θ>         | rotate_q0  |
| |θ>         | read_out |                     | |measuring> | measure_q0 |
| |measuring> | collapse | prob_collapse('0')  | |0_result>  |            |
| |measuring> | collapse | prob_collapse('1')  | |1_result>  |            |

## guards
| Name               | Expression                  |
|--------------------|-----------------------------|
| prob_collapse('0') | prob_collapse('0') == 0.854 |
| prob_collapse('1') | prob_collapse('1') == 0.146 |

## actions
| Name       | Signature  | Effect          |
|------------|------------|-----------------|
| rotate_q0  | (qs) -> qs | Rx(qs[0], theta) |
| measure_q0 | (qs) -> qs | measure(qs[0])  |

## verification rules
- unitarity: all gates preserve norm
