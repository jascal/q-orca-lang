# machine BitFlipSyndrome

> 5-qubit bit-flip syndrome circuit: 3 data qubits (q0–q2) + 2 ancilla (q3, q4).
> Measure two syndrome bits mid-circuit; apply X corrections conditioned on
> the syndrome results. This demonstrates mid-circuit measurement and classical
> feedforward in Q-Orca.

## context

| Field  | Type        | Default                                  |
|--------|-------------|------------------------------------------|
| qubits | list<qubit> | [q0:data, q1:data, q2:data, q3:ancilla, q4:ancilla] |
| bits   | list<bit>   | [b0, b1]                                 |

<!-- q3/q4 are tagged `ancilla`: the verifier now enforces ancilla reset between
     successive mid-circuit measurements automatically (no hand-added
     `mid_circuit_coherence` rule needed). q0-q2 carry the algorithmic payload. -->


## events

- entangle
- measure_s0
- measure_s1
- correct_q0
- correct_q1
- correct_q2

## state |init> [initial]

> Data qubits in |000⟩, ancilla in |00⟩

## state |entangled> [assert: classical(qs[0..2])]

> Ancilla qubits coupled to data for syndrome extraction. On the no-error
> path the data register stays in the definite codeword |000⟩, so the data
> qubits are classical (not in superposition) at this point.

## state |s0_measured>

> First syndrome bit captured: bits[0] = measure(q3)

## state |s1_measured> [assert: classical(qs[3..4])]

> Second syndrome bit captured: bits[1] = measure(q4). Both ancilla qubits
> have been measured, so they sit in a definite classical Z-basis state.

## state |q0_corrected>

> X correction applied to q0 only when syndrome (1, 0) — error on q0

## state |q1_corrected>

> X correction applied to q1 only when syndrome (1, 1) — error on q1

## state |corrected> [final]

> All four syndrome patterns mapped to the correct correction;
> logical qubit restored. (0,0) → no error, (1,0) → q0,
> (1,1) → q1, (0,1) → q2.

## transitions

| Source          | Event      | Guard | Target          | Action        |
|-----------------|------------|-------|-----------------|---------------|
| |init>          | entangle   |       | |entangled>     | entangle_data |
| |entangled>     | measure_s0 |       | |s0_measured>   | measure_s0    |
| |s0_measured>   | measure_s1 |       | |s1_measured>   | measure_s1    |
| |s1_measured>   | correct_q0 |       | |q0_corrected>  | correct_q0    |
| |q0_corrected>  | correct_q1 |       | |q1_corrected>  | correct_q1    |
| |q1_corrected>  | correct_q2 |       | |corrected>     | correct_q2    |

## actions

| Name          | Signature      | Effect                                                       |
|---------------|----------------|--------------------------------------------------------------|
| entangle_data | (qs) -> qs     | CNOT(qs[0], qs[3]); CNOT(qs[1], qs[3]); CNOT(qs[1], qs[4]); CNOT(qs[2], qs[4]) |
| measure_s0    | (qs) -> qs     | measure(qs[3]) -> bits[0]                                    |
| measure_s1    | (qs) -> qs     | measure(qs[4]) -> bits[1]                                    |
| correct_q0    | (qs) -> qs     | if bits[0] == 1 and bits[1] == 0: X(qs[0])                   |
| correct_q1    | (qs) -> qs     | if bits[0] == 1 and bits[1] == 1: X(qs[1])                   |
| correct_q2    | (qs) -> qs     | if bits[0] == 0 and bits[1] == 1: X(qs[2])                   |

## verification rules

- mid_circuit_coherence: ancilla qubits q3 and q4 are not reused after measurement
- feedforward_completeness: every syndrome measurement drives a correction gate
- state_assertions: sample-check the data-codeword and syndrome-ancilla state categories

## assertion policy

| Setting          | Value | Notes             |
|------------------|-------|-------------------|
| shots_per_assert | 256   | small for fast CI |
