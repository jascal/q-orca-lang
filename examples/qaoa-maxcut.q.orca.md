# machine QAOAMaxCut

## context
| Field     | Type        | Default |
|-----------|-------------|---------|
| qubits    | list<qubit> | [q0, q1, q2] |
| gamma     | float       | 0.5    |
| beta      | float       | 0.25   |
| depth     | int         | 1      |

## events
- init
- apply_cost
- apply_mixer
- readout

## state |000> [initial]
> All qubits in |0> — ground state before ansatz

## state |+++ > = (|000> + |001> + |010> + |011> + |100> + |101> + |110> + |111>)/√8
> Equal superposition after Hadamard layer

## state |cost_applied>
> After QAOA cost unitary: RZZ gates encode MaxCut edge weights

## state |mixed>
> After QAOA mixer unitary: Rx gates rotate each qubit

## state |measured> [final]
> Measurement outcome encodes a MaxCut bitstring

## transitions
| Source          | Event        | Guard | Target          | Action           |
|-----------------|--------------|-------|-----------------|------------------|
| |000>           | init         |       | |+++ >          | hadamard_layer   |
| |+++ >          | apply_cost   |       | |cost_applied>  | cost_unitary     |
| |cost_applied>  | apply_mixer  |       | |mixed>         | mixer_unitary    |
| |mixed>         | readout      |       | |measured>      |                  |

## actions
| Name            | Signature     | Effect                                                                      |
|-----------------|---------------|-----------------------------------------------------------------------------|
| hadamard_layer  | (qs) -> qs    | Hadamard(qs[0]); Hadamard(qs[1]); Hadamard(qs[2])                           |
| cost_unitary    | (qs) -> qs    | RZZ(qs[0], qs[1], gamma); RZZ(qs[1], qs[2], gamma); RZZ(qs[0], qs[2], gamma) |
| mixer_unitary   | (qs) -> qs    | Rx(qs[0], beta); Rx(qs[1], beta); Rx(qs[2], beta)                          |

## verification rules
- unitarity: all gates preserve norm
- resource_bounds: NISQ-fit budget for the per-layer prep circuit

## resources
| Metric         | Basis      |
|----------------|------------|
| gate_count     | logical    |
| depth          | logical    |
| cx_count       | u3+cx      |
| logical_qubits | -          |

## invariants
- gate_count <= 9
- depth <= 5
- cx_count <= 6
- logical_qubits == 3
