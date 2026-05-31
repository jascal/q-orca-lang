# machine VqeOrchestrator

> Classical Orca orchestrator for a hybrid quantum-classical optimization loop.
> It tunes the rotation angle `theta` of a quantum circuit so that the measured
> probability of outcome 1 hits a target. Each iteration delegates one
> shot-batched forward pass to the `QForward` quantum machine **in q-orca**, over
> the cross-tool bridge (protocol 1.0): the orchestrator never sees a qubit, only
> the classical statistic `prob` bound back from the child's `prob_bits_0`.
>
> The optimization loop — measure, evaluate, step, repeat — is expressed entirely
> as Orca state and transitions. The host language supplies only the numeric
> `gradient_step` action body and the convergence flag it sets.

## context
| Field     | Type  | Default |
|-----------|-------|---------|
| theta     | float | 0.30    |
| prob      | float | 0.0     |
| target    | float | 0.5     |
| iteration | int   | 0       |
| converged | bool  | false   |

## events
- begin
- next
- MEASURED

## state idle [initial]
> Ready to optimize. The starting angle is far from the target.

## state measuring
> Delegate one forward pass to the quantum child over the bridge. `prob` is bound
> back from the child's measured-bit expectation `prob_bits_0`.
- invoke: QForward input: { theta: ctx.theta } shots: 4096 returns: { prob: prob_bits_0 }
- on_done: MEASURED

## state evaluate
> Classical step: update `theta` from the measured error and decide whether the
> loop has converged. Handled by the `gradient_step` action.

## state done [final]
> Converged (or hit the iteration cap). `theta` now drives the circuit to the
> target measurement probability.

## transitions
| Source    | Event    | Guard         | Target    | Action        |
|-----------|----------|---------------|-----------|---------------|
| idle      | begin    |               | measuring |               |
| measuring | MEASURED |               | evaluate  | gradient_step |
| evaluate  | next     | is_converged  | done      |               |
| evaluate  | next     | not_converged | measuring |               |

## guards
| Name          | Expression            |
|---------------|-----------------------|
| is_converged  | ctx.converged == true |
| not_converged | ctx.converged == false |

## actions
| Name          | Signature             |
|---------------|-----------------------|
| gradient_step | (ctx, event) -> Context |
