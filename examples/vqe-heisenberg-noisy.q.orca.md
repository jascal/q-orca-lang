# machine VqeHeisenbergNoisy

> A two-qubit ansatz preparation annotated with a realistic, Kandala-shaped
> (`1704.05018`) NISQ noise model: asymmetric single- vs two-qubit gate
> depolarizing plus measurement readout error. Demonstrates the declarative
> `## noise_model` section (`add-noise-model-section`) — the verifier reads it,
> and the Qiskit Aer compiler builds the corresponding `NoiseModel` automatically.

## context

| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1]     |
| bits   | list<bit>   | [c0, c1]     |
| theta  | float       | 0.7853981634 |

## noise_model

| Channel       | Target              | Parameters                   |
|---------------|---------------------|------------------------------|
| depolarizing  | single_qubit_gates  | p=0.001                      |
| depolarizing  | two_qubit_gates     | p=0.012                      |
| readout_error | all_measurements    | p0given1=0.02, p1given0=0.04 |

## events

- prepare
- entangle
- read_out

## state |00> [initial]

> Two qubits in the ground state.

## state |ansatz>

> After the parameterized single-qubit rotation on q0.

## state |entangled>

> After the entangling CNOT — a Heisenberg-ansatz building block.

## state |measured> [final]

> Both qubits measured into the classical register.

## transitions

| Source       | Event     | Guard | Target       | Action     |
|--------------|-----------|-------|--------------|------------|
| |00>         | prepare   |       | |ansatz>     | rotate     |
| |ansatz>     | entangle  |       | |entangled>  | couple     |
| |entangled>  | read_out  |       | |measured>   | measure_q0 |

## actions

| Name       | Signature  | Effect                    |
|------------|------------|---------------------------|
| rotate     | (qs) -> qs | Ry(qs[0], theta)          |
| couple     | (qs) -> qs | CNOT(qs[0], qs[1])        |
| measure_q0 | (qs) -> qs | measure(qs[0]) -> bits[0] |

## verification rules

- unitarity: all gates preserve norm
