# machine VqeRotation

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]    |

## events
- rotate
- measure

## state |0> [initial]
> Single qubit ground state

## state |θ> = cos(π/8)|0> - i·sin(π/8)|1>
> Qubit after Rx(π/4) rotation — ready for measurement

## state |measured> [final]
> Post-measurement outcome

## transitions
| Source | Event   | Guard | Target     | Action    |
|--------|---------|-------|------------|-----------|
| |0>    | rotate  |       | |θ>        | rotate_q0 |
| |θ>   | measure |       | |measured> | measure_q0 |

## actions
| Name       | Signature  | Effect          |
|------------|------------|-----------------|
| rotate_q0  | (qs) -> qs | Rx(qs[0], pi/4) |
| measure_q0 | (qs) -> qs | measure(qs[0])  |

## verification rules
- unitarity: all gates preserve norm
