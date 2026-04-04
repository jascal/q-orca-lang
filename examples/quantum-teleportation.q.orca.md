# machine QuantumTeleportation

## context
| Field       | Type          | Default |
|-------------|---------------|---------|
| qubits      | list<qubit>   |         |
| alice_bit   | int           | -1      |
| bob_bit     | int           | -1      |

## events
- prepare
- entangle
- alice_measure
- bob_correct

## state |ψ00>
> Initial state: qubit to teleport in |ψ>, ancillas in |00>

## state |ψΦ+> = |ψ> ⊗ (|00> + |11>)/√2
> After creating Bell pair between q1 and q2

## state |bell_measured>
> After Alice measures her two qubits in Bell basis

## state |teleported> [final]
> Bob has recovered |ψ> on his qubit after corrections

## transitions
| Source         | Event          | Guard | Target          | Action            |
|----------------|----------------|-------|-----------------|-------------------|
| |ψ00>          | prepare        |       | |ψ00>           | apply_H_on_q1     |
| |ψ00>          | entangle       |       | |ψΦ+>           | apply_CNOT_q1_q2  |
| |ψΦ+>          | alice_measure  |       | |bell_measured>  | alice_bell_measure |
| |bell_measured> | bob_correct    |       | |teleported>     | bob_apply_correction |

## guards
| Name | Expression |
|------|------------|

## actions
| Name                 | Signature         | Effect              |
|----------------------|-------------------|----------------------|
| apply_H_on_q1        | (qs) -> qs        | Hadamard(qs[1])      |
| apply_CNOT_q1_q2     | (qs) -> qs        | CNOT(qs[1], qs[2])   |
| alice_bell_measure   | (qs) -> qs        | measure(qs[0,1])     |
| bob_apply_correction | (qs, bits) -> qs  | conditional_XZ       |

## effects
| Name              | Input                | Output          |
|-------------------|----------------------|-----------------|
| bell_measurement  | 2-qubit state        | 2 classical bits|
| correction        | classical bits       | corrected qubit |

## verification rules
- unitarity: all gates preserve norm
- no-cloning: teleportation moves state, does not copy it
