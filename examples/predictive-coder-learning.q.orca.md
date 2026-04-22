# machine PredictiveCoderLearning

> Full 3-qubit quantum predictive coder with a classical learning loop.
> Extends `predictive-coder-minimal` by driving the parametric-ansatz
> angle `theta_0` from the measured error bit on each iteration and
> terminating when `ctx.iteration >= max_iter`.
>
> This is the machine spec from the research doc
> `docs/research/spec-quantum-predictive-coder.md` §Next concrete steps,
> implemented against the iterative runtime landed by
> `run-context-updates`.

## context

| Field     | Type        | Default           |
|-----------|-------------|-------------------|
| qubits    | list<qubit> | [q0, q1, q2]      |
| bits      | list<bit>   | [b_err]           |
| theta     | list<float> | [0.5, 0.3, 0.7]   |
| eta       | float       | 0.05              |
| iteration | int         | 0                 |
| max_iter  | int         | 3                 |

## events

- prepare_prior
- encode_data
- compute_error
- measure_error
- gradient_step
- loop_back
- finalize

## state |init> [initial]

> Three qubits in |000⟩. q0 is the model register, q1 is the data
> register, q2 is the error ancilla.

## state |prior_ready>

> Model qubit q0 prepared by Ry·Rz·Rx(theta[0], theta[1], theta[2])|0⟩.
> On iterations > 0 this state is re-entered with a mutated `theta[0]`.

## state |joined>

> Data register q1 prepared as H|0⟩ = |+⟩. Ancilla still |0⟩.

## state |error_extracted>

> Parity CNOTs have mapped (model XOR data) onto the ancilla in the Z
> basis.

## state |measured>

> Ancilla measured into bits[0]. The sign of the classical learning
> update now depends on this bit.

## state |model_updated>

> `gradient_step` has applied `theta[0] -= eta` (bit = 1) or
> `theta[0] += eta` (bit = 0) to the runtime context.

## state |converged> [final]

> Loop exited once `ctx.iteration >= max_iter`. The final context
> holds the learned `theta[0]`.

## guards

| Name     | Expression                |
|----------|---------------------------|
| continue | ctx.iteration < max_iter  |
| done     | ctx.iteration >= max_iter |

## transitions

| Source             | Event          | Guard    | Target             | Action             |
|--------------------|----------------|----------|--------------------|--------------------|
| |init>             | prepare_prior  |          | |prior_ready>      | apply_ansatz       |
| |prior_ready>      | encode_data    |          | |joined>           | encode_datum       |
| |joined>           | compute_error  |          | |error_extracted>  | parity_to_ancilla  |
| |error_extracted>  | measure_error  |          | |measured>         | measure_ancilla    |
| |measured>         | gradient_step  |          | |model_updated>    | gradient_step      |
| |model_updated>    | loop_back      | continue | |prior_ready>      | tick               |
| |model_updated>    | finalize       | done     | |converged>        |                    |

## actions

| Name              | Signature    | Effect                                                       |
|-------------------|--------------|--------------------------------------------------------------|
| apply_ansatz      | (qs) -> qs   | Ry(qs[0], theta[0]); Rz(qs[0], theta[1]); Rx(qs[0], theta[2]) |
| encode_datum      | (qs) -> qs   | H(qs[1])                                                     |
| parity_to_ancilla | (qs) -> qs   | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[2])                       |
| measure_ancilla   | (qs) -> qs   | measure(qs[2]) -> bits[0]                                    |
| gradient_step     | (ctx) -> ctx | if bits[0] == 1: theta[0] -= eta else: theta[0] += eta       |
| tick              | (ctx) -> ctx | iteration += 1                                               |

## verification rules

- unitarity: all gates preserve norm
- mid_circuit_coherence: ancilla q2 is not reused after measurement
