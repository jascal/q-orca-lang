# machine ActiveTeleportation

> Standard 3-qubit active (deterministic) quantum teleportation.
> Alice holds q0 (state to teleport) and q1 (her Bell pair qubit).
> Bob holds q2 (his Bell pair qubit).
> Mid-circuit Bell measurement on q0+q1 feeds forward X and Z corrections to q2.

## context

| Field  | Type        | Default       |
|--------|-------------|---------------|
| qubits | list<qubit> | [q0, q1, q2] |
| bits   | list<bit>   | [b0, b1]      |

## events

- create_bell_pair
- encode_alice
- measure_alice_x
- measure_alice_z
- correct_x
- correct_z

## state |init> [initial]

> q0 in arbitrary state |ψ⟩; q1 and q2 in |00⟩

## state |bell_ready>

> Bell pair prepared between q1 and q2: (|00⟩ + |11⟩)/√2

## state |alice_encoded>

> Alice applied CNOT(q0,q1) and H(q0) to entangle her qubit with the channel

## state |measured>

> Mid-circuit Bell measurement complete: b0 = measure(q0), b1 = measure(q1)

## state |teleported> [final]

> Bob's qubit q2 holds |ψ⟩ after X and Z feedforward corrections

## transitions

| Source          | Event             | Guard | Target           | Action        |
|-----------------|-------------------|-------|------------------|---------------|
| |init>          | create_bell_pair  |       | |bell_ready>     | make_bell     |
| |bell_ready>    | encode_alice      |       | |alice_encoded>  | encode_alice  |
| |alice_encoded> | measure_alice_x   |       | |measured>       | meas_q0       |
| |measured>      | measure_alice_z   |       | |measured>       | meas_q1       |
| |measured>      | correct_x         |       | |measured>       | feedfwd_x     |
| |measured>      | correct_z         |       | |teleported>     | feedfwd_z     |

## actions

| Name         | Signature      | Effect                             |
|--------------|----------------|------------------------------------|
| make_bell    | (qs) -> qs     | Hadamard(qs[1]); CNOT(qs[1], qs[2]) |
| encode_alice | (qs) -> qs     | CNOT(qs[0], qs[1]); Hadamard(qs[0]) |
| meas_q0      | (qs) -> qs     | measure(qs[0]) -> bits[0]          |
| meas_q1      | (qs) -> qs     | measure(qs[1]) -> bits[1]          |
| feedfwd_x    | (qs) -> qs     | if bits[1] == 1: X(qs[2])         |
| feedfwd_z    | (qs) -> qs     | if bits[0] == 1: Z(qs[2])         |

## verification rules

- mid_circuit_coherence: q0 and q1 are not reused after mid-circuit measurement
- feedforward_completeness: both measured bits drive correction gates on Bob's qubit
