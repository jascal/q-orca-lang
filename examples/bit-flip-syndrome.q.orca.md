# machine BitFlipSyndrome

> 5-qubit bit-flip syndrome circuit: 3 data qubits (q0–q2) + 2 ancilla (q3, q4).
> Measure two syndrome bits mid-circuit; apply X corrections conditioned on
> the syndrome results. This demonstrates mid-circuit measurement and classical
> feedforward in Q-Orca.

## context

| Field  | Type        | Default               |
|--------|-------------|-----------------------|
| qubits | list<qubit> | [q0, q1, q2, q3, q4] |
| bits   | list<bit>   | [b0, b1]              |

## events

- entangle
- measure_s0
- measure_s1
- correct_q0
- correct_q2

## state |init> [initial]

> Data qubits in |000⟩, ancilla in |00⟩

## state |entangled>

> Ancilla qubits entangled with data for syndrome extraction

## state |s0_measured>

> First syndrome bit captured: bits[0] = measure(q3)

## state |s1_measured>

> Second syndrome bit captured: bits[1] = measure(q4)

## state |q0_corrected>

> X correction applied to q0 if bits[0] == 1

## state |corrected> [final]

> Both corrections applied; logical qubit restored

## transitions

| Source          | Event      | Guard | Target          | Action        |
|-----------------|------------|-------|-----------------|---------------|
| |init>          | entangle   |       | |entangled>     | entangle_data |
| |entangled>     | measure_s0 |       | |s0_measured>   | measure_s0    |
| |s0_measured>   | measure_s1 |       | |s1_measured>   | measure_s1    |
| |s1_measured>   | correct_q0 |       | |q0_corrected>  | correct_q0    |
| |q0_corrected>  | correct_q2 |       | |corrected>     | correct_q2    |

## actions

| Name          | Signature      | Effect                                                       |
|---------------|----------------|--------------------------------------------------------------|
| entangle_data | (qs) -> qs     | CNOT(qs[0], qs[3]); CNOT(qs[1], qs[3]); CNOT(qs[1], qs[4]); CNOT(qs[2], qs[4]) |
| measure_s0    | (qs) -> qs     | measure(qs[3]) -> bits[0]                                    |
| measure_s1    | (qs) -> qs     | measure(qs[4]) -> bits[1]                                    |
| correct_q0    | (qs) -> qs     | if bits[0] == 1: X(qs[0])                                   |
| correct_q2    | (qs) -> qs     | if bits[1] == 1: X(qs[2])                                   |

## verification rules

- mid_circuit_coherence: ancilla qubits q3 and q4 are not reused after measurement
- feedforward_completeness: every syndrome measurement drives a correction gate
