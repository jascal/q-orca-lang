# machine QForward

> Single-qubit variational forward pass. Prepare the qubit with a parameterized
> `Ry(theta)` rotation, then measure it into `bits[0]`. Invoked over the
> cross-tool bridge by a classical Orca orchestrator: with `shots=N` it reports
> the measured-bit expectation `prob_bits_0 = P(measure 1) = sin^2(theta/2)`
> back across the tool boundary.

## context
| Field | Type  | Default |
|-------|-------|---------|
| theta | float | 0.5     |

## events
- prepare
- measure_out

## state |q0> [initial]
> Ground state |0>.

## state |prepared>
> After the parameterized Ry(theta) rotation — a superposition.

## state |measured> [final]
> Collapsed; outcome recorded in bits[0].

## transitions
| Source      | Event       | Guard | Target      | Action |
|-------------|-------------|-------|-------------|--------|
| |q0>        | prepare     |       | |prepared>  | rotate |
| |prepared>  | measure_out |       | |measured>  | meas   |

## actions
| Name   | Signature  | Effect                    |
|--------|------------|---------------------------|
| rotate | (qs) -> qs | Ry(qs[0], theta)          |
| meas   | (qs) -> qs | measure(qs[0]) -> bits[0] |

## returns
| Name    | Type | Statistics             |
|---------|------|------------------------|
| bits[0] | bit  | expectation, histogram |
