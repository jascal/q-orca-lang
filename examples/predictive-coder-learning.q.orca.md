# machine PredictiveCoderLearning

> Full 3-qubit quantum predictive coder with a classical learning loop.
> Extends `predictive-coder-minimal` by driving the parametric-ansatz
> angle `theta_0` from the measured error bit on each iteration and
> terminating when `ctx.iteration >= max_iter`.
>
> The three rotation angles are stored as scalar fields `theta_0`,
> `theta_1`, `theta_2` because the current parser restricts angle
> expressions in rotation gates to bare context-field references.
>
> This is the machine spec from the research doc
> `docs/research/spec-quantum-predictive-coder.md` §Next concrete steps,
> implemented against the iterative runtime landed by
> `run-context-updates`.
>
> ⚠️ **No learning happens here — this is a structural skeleton, kept for
> teaching.** Two reasons: (1) the data register is `H|0> = |+>`, so the parity
> ancilla reads `P(bits[0]=1) = 1/2` *independently of* `theta_0` — there is no
> learning signal and `theta_0` would just random-walk; and (2) `gradient_step`
> has an empty effect (a no-op), so `theta_0` never changes at all. For a machine
> that actually learns — real signal, real update, model re-prepared each
> iteration, converging to `theta_0 = pi/2` — see
> `examples/predictive-coder-converging.q.orca.md` and the convergence benchmark
> in `q_orca/evaluation/qpc.py` (`add-qpc-convergence-benchmark`).

## context

| Field     | Type        | Default           |
|-----------|-------------|-------------------|
| qubits    | list<qubit> | [q0, q1, q2]      |
| bits      | list<bit>   | [b_err]           |
| theta_0   | float       | 0.5               |
| theta_1   | float       | 0.3               |
| theta_2   | float       | 0.7               |
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

> Model qubit q0 prepared by Ry·Rz·Rx(theta_0, theta_1, theta_2)|0⟩.
> On iterations > 0 this state is re-entered with a mutated `theta_0`.

## state |joined>

> Data register q1 prepared as H|0⟩ = |+⟩. Ancilla still |0⟩.

## state |error_extracted>

> Parity CNOTs have mapped (model XOR data) onto the ancilla in the Z
> basis.

## state |measured>

> Ancilla measured into bits[0]. The sign of the classical learning
> update now depends on this bit.

## state |model_updated>

> `gradient_step` has applied `theta_0 -= eta` (bit = 1) or
> `theta_0 += eta` (bit = 0) to the runtime context.

## state |converged> [final]

> Loop exited once `ctx.iteration >= max_iter`. The final context
> holds the learned `theta_0`.

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
| apply_ansatz      | (qs) -> qs   | Ry(qs[0], theta_0); Rz(qs[0], theta_1); Rx(qs[0], theta_2) |
| encode_datum      | (qs) -> qs   | H(qs[1])                                                     |
| parity_to_ancilla | (qs) -> qs   | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[2])                       |
| measure_ancilla   | (qs) -> qs   | measure(qs[2]) -> bits[0]                                    |
| gradient_step     | (ctx) -> ctx |                                                              |
| tick              | (ctx) -> ctx | iteration += 1                                               |

## verification rules

- unitarity: all gates preserve norm
- mid_circuit_coherence: ancilla q2 is not reused after measurement
