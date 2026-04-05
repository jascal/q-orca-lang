# machine QuantumTeleportation

## context
| Field    | Type          | Default   |
|----------|---------------|-----------|
| qubits   | list<qubit>   | [q0, q1, q2] |
| outcome  | int           | -1       |

## events
- prepare
- alice_measure
- bob_correct

## state |ψ00>
> Initial state: qubit to teleport in |0>, ancillas in |00>

## state |ψΦ+>
> After creating Bell pair between q1 and q2: |ψ> ⊗ (|00> + |11>)/√2

## state |bell_Φ+>
> Bell measurement result: Φ+ = (|00> + |11>)/√2 — Bob applies Identity

## state |bell_Φ->
> Bell measurement result: Φ- = (|00> - |11>)/√2 — Bob applies Z

## state |bell_Ψ+>
> Bell measurement result: Ψ+ = (|01> + |10>)/√2 — Bob applies X

## state |bell_Ψ->
> Bell measurement result: Ψ- = (|01> - |10>)/√2 — Bob applies XZ

## state |teleported> [final]
> |ψ> successfully teleported to q2

## transitions
| Source     | Event          | Guard                        | Target        | Action                  |
|------------|----------------|------------------------------|---------------|-------------------------|
| |ψ00>      | prepare        |                              | |ψΦ+>         | apply_H_CNOT            |
| |ψΦ+>      | alice_measure  | alice_Φ+                     | |bell_Φ+>     | set_outcome_0           |
| |ψΦ+>      | alice_measure  | alice_Φ-                     | |bell_Φ->     | set_outcome_1           |
| |ψΦ+>      | alice_measure  | alice_Ψ+                     | |bell_Ψ+>     | set_outcome_2           |
| |ψΦ+>      | alice_measure  | alice_Ψ-                     | |bell_Ψ->     | set_outcome_3           |
| |bell_Φ+>  | bob_correct    |                              | |teleported>   | apply_I                 |
| |bell_Φ->  | bob_correct    |                              | |teleported>   | apply_Z                 |
| |bell_Ψ+>  | bob_correct    |                              | |teleported>   | apply_X                 |
| |bell_Ψ->  | bob_correct    |                              | |teleported>   | apply_XZ                |

## guards
| Name       | Expression                                        |
|------------|---------------------------------------------------|
| alice_Φ+   | fidelity(|ψΦ+>, |Φ+>) ** 2 ≈ 0.25                |
| alice_Φ-   | fidelity(|ψΦ+>, |Φ->) ** 2 ≈ 0.25                |
| alice_Ψ+   | fidelity(|ψΦ+>, |Ψ+>) ** 2 ≈ 0.25                |
| alice_Ψ-   | fidelity(|ψΦ+>, |Ψ->) ** 2 ≈ 0.25                |

## actions
| Name       | Signature      | Effect           |
|------------|----------------|------------------|
| apply_H_CNOT | (qs) -> qs   | Hadamard(qs[1]); CNOT(qs[1], qs[2]) |
| set_outcome_0 | (ctx) -> ctx | ctx.outcome = 0  |
| set_outcome_1 | (ctx) -> ctx | ctx.outcome = 1  |
| set_outcome_2 | (ctx) -> ctx | ctx.outcome = 2  |
| set_outcome_3 | (ctx) -> ctx | ctx.outcome = 3  |
| apply_I    | (qs) -> qs     |                  |
| apply_Z    | (qs) -> qs     | Z(qs[0])         |
| apply_X    | (qs) -> qs     | X(qs[0])         |
| apply_XZ   | (qs) -> qs     | X(qs[0]); Z(qs[0]) |

## effects
| Name             | Input             | Output             |
|------------------|-------------------|--------------------|
| bell_measurement | 2-qubit entangled | 2 classical bits   |
| correction       | classical bits     | corrected qubit     |

## verification rules
- unitarity: all gates preserve norm
- entanglement: Bell pair (q1, q2) maintains Schmidt rank > 1 before measure
- completeness: all four Bell outcomes lead to teleported state
- no-cloning: teleportation moves state, does not copy it
