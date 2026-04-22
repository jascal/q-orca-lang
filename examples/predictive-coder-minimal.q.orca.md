# machine PredictiveCoderMinimal

> Minimal 3-qubit quantum predictive coder: one model qubit (parametric
> ansatz), one data qubit (target state), and one error ancilla. Extracts a
> single-shot Z-basis parity error signal from (model XOR data) onto the
> ancilla, then measures the ancilla as a classical error bit.
>
> This is the unitary skeleton only — the learning loop that would update
> `theta_*` from the measured error requires a classical-context-update
> primitive that is not yet a shipped q-orca feature (see
> `docs/research/spec-quantum-predictive-coder.md`).

## context

| Field   | Type        | Default      |
|---------|-------------|--------------|
| qubits  | list<qubit> | [q0, q1, q2] |
| bits    | list<bit>   | [b_err]      |
| theta_0 | float       | 0.5          |
| theta_1 | float       | 0.3          |
| theta_2 | float       | 0.7          |

## events

- prepare_prior
- encode_data
- compute_error
- measure_error

## state |init> [initial]

> Three qubits in |000⟩. q0 is the model register, q1 is the data register,
> q2 is the error ancilla. theta_* hold the parametric-ansatz angles.

## state |prior_ready>

> Model register q0 prepared by Ry·Rz·Rx(theta_0, theta_1, theta_2)|0⟩.
> This is the machine's "prior belief" over Z-basis outcomes.

## state |joined>

> Data register q1 prepared as H|0⟩ = |+⟩ (the target distribution for
> this minimal demo). Model and data registers are independent; ancilla
> still in |0⟩.

## state |error_extracted>

> Parity CNOTs have mapped (model XOR data) onto the ancilla in the Z
> basis. If model and data measurement outcomes would agree, ancilla is
> |0⟩; if they would differ, ancilla is |1⟩.

## state |bit_read> [final]

> Ancilla measured into bits[0]. bits[0] == 0 means the model's Z-basis
> prediction matched the data's Z-basis outcome (no error); bits[0] == 1
> means the model's prediction disagreed (error signal present).

## transitions

| Source             | Event          | Guard | Target             | Action              |
|--------------------|----------------|-------|--------------------|---------------------|
| |init>             | prepare_prior  |       | |prior_ready>      | apply_ansatz        |
| |prior_ready>      | encode_data    |       | |joined>           | encode_datum        |
| |joined>           | compute_error  |       | |error_extracted>  | parity_to_ancilla   |
| |error_extracted>  | measure_error     |       | |bit_read>         | measure_ancilla     |

## actions

| Name              | Signature  | Effect                                              |
|-------------------|------------|-----------------------------------------------------|
| apply_ansatz      | (qs) -> qs | Ry(qs[0], theta_0); Rz(qs[0], theta_1); Rx(qs[0], theta_2) |
| encode_datum      | (qs) -> qs | H(qs[1])                                            |
| parity_to_ancilla | (qs) -> qs | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[2])              |
| measure_ancilla   | (qs) -> qs | measure(qs[2]) -> bits[0]                           |

## verification rules

- unitarity: all gates preserve norm
- mid_circuit_coherence: ancilla q2 is not reused after measurement
