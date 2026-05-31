# machine PredictiveCoderConverging

> Convergence-benchmark variant of the quantum predictive coder. Unlike
> `predictive-coder-learning` (a structural skeleton whose data register is
> `H|0> = |+>`, making the parity error `P(bits[0]=1) = 1/2` independent of the
> model parameter, and whose `gradient_step` is a no-op), this machine has a real
> learning signal and a real update, and it re-prepares the model each iteration:
>
> - The data register `q1` is left in `|0>` (no `H`), so the parity ancilla reads
>   `P(bits[0]=1) = P(q0=1) = sin^2(theta_0/2)` — a genuine function of the model
>   parameter `theta_0`.
> - `theta_1 = theta_2 = 0` (Rz/Rx collapse to identity), so the objective is the
>   clean closed form `p(theta_0) = sin^2(theta_0/2)`.
> - `gradient_step` actually mutates `theta_0`: `-= eta` on a measured 1, `+= eta`
>   on a measured 0. Zero expected drift is at `p = 1/2`, i.e. `theta_0* = pi/2`.
> - The loop re-enters through `|ready>`, so `apply_ansatz` re-runs every iteration
>   with the updated `theta_0` (the model is re-prepared, not measured stale).
>
> The angle is a bare scalar field `theta_0` (not a `list<float>` element) so it can
> be both a rotation-gate angle (`Ry(qs[0], theta_0)`) and the target of a
> context-update mutation (`theta_0 -= eta`). Mutating a scalar float in a context
> update is enabled by the verifier relaxation shipped alongside this example.
>
> Drives the convergence harness in `q_orca/evaluation/qpc.py`. The small
> `max_iter` default keeps `q-orca run` quick; the harness overrides
> `theta_0` / `eta` / `max_iter` per benchmark configuration.

## context

| Field     | Type        | Default      |
|-----------|-------------|--------------|
| qubits    | list<qubit> | [q0, q1, q2] |
| bits      | list<bit>   | [b_err]      |
| theta_0   | float       | 0.5          |
| theta_1   | float       | 0.0          |
| theta_2   | float       | 0.0          |
| eta       | float       | 0.15         |
| iteration | int         | 0            |
| max_iter  | int         | 8            |

## events

- begin
- prepare_prior
- encode_data
- compute_error
- measure_error
- gradient_step
- loop_back
- finalize

## state |init> [initial]

> Three qubits in |000⟩. q0 is the model register, q1 is the data
> register (held in |0⟩), q2 is the error ancilla.

## state |ready>

> Loop re-entry point. Re-entered each iteration so the model is freshly
> prepared from the current theta_0.

## state |prior_ready>

> Model qubit q0 prepared by Ry(theta_0)|0⟩ (Rz·Rx are identity at
> theta_1 = theta_2 = 0).

## state |joined>

> Data register q1 left in |0⟩ — the fixed computational-basis datum.

## state |error_extracted>

> Parity CNOTs map (model XOR data) = q0 onto the ancilla in the Z basis.

## state |measured>

> Ancilla measured into bits[0]. P(bits[0]=1) = sin^2(theta_0/2).

## state |model_updated>

> gradient_step has applied theta_0 -= eta (bit = 1) or theta_0 += eta
> (bit = 0) to the runtime context.

## state |converged> [final]

> Loop exited once ctx.iteration >= max_iter. The final context holds the
> learned theta_0, which sits within an O(eta) band around pi/2.

## guards

| Name     | Expression                |
|----------|---------------------------|
| continue | ctx.iteration < max_iter  |
| done     | ctx.iteration >= max_iter |

## transitions

| Source             | Event          | Guard    | Target             | Action            |
|--------------------|----------------|----------|--------------------|-------------------|
| |init>             | begin          |          | |ready>            |                   |
| |ready>            | prepare_prior  |          | |prior_ready>      | apply_ansatz      |
| |prior_ready>      | encode_data    |          | |joined>           | encode_datum      |
| |joined>           | compute_error  |          | |error_extracted>  | parity_to_ancilla |
| |error_extracted>  | measure_error  |          | |measured>         | measure_ancilla   |
| |measured>         | gradient_step  |          | |model_updated>    | gradient_step     |
| |model_updated>    | loop_back      | continue | |ready>            | tick              |
| |model_updated>    | finalize       | done     | |converged>        |                   |

## actions

| Name              | Signature    | Effect                                                       |
|-------------------|--------------|--------------------------------------------------------------|
| apply_ansatz      | (qs) -> qs   | Ry(qs[0], theta_0); Rz(qs[0], theta_1); Rx(qs[0], theta_2)   |
| encode_datum      | (qs) -> qs   |                                                              |
| parity_to_ancilla | (qs) -> qs   | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[2])                       |
| measure_ancilla   | (qs) -> qs   | measure(qs[2]) -> bits[0]                                    |
| gradient_step     | (ctx) -> ctx | if bits[0] == 1: theta_0 -= eta else: theta_0 += eta         |
| tick              | (ctx) -> ctx | iteration += 1                                               |

## verification rules

- unitarity: all gates preserve norm
- mid_circuit_coherence: ancilla q2 is not reused after measurement
