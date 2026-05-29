# machine QPCTrainer

> Classical orchestrator for a quantum predictive coder: each training step
> delegates a shot-batched forward pass to the QForward child and reads back the
> measured-bit expectation as a float.

## context
| Field     | Type  | Default |
|-----------|-------|---------|
| iteration | int   | 0       |
| theta     | float | 0.5     |
| prob      | float | 0.0     |
| converged | bool  | false   |

## events
- advance

## state |idle> [initial]
> Ready to begin training.

## state |step> [invoke: QForward(theta=theta) shots=1024]
> Delegate one forward pass; read the measured-bit expectation back.
> returns: prob=prob_bits_0

## state |done> [final]
> Training complete.

## transitions
| Source  | Event   | Guard | Target  | Action |
|---------|---------|-------|---------|--------|
| |idle>  | advance |       | |step>  |        |
| |step>  | advance |       | |done>  |        |

## returns
| Name      | Type | Statistics |
|-----------|------|------------|
| converged | bool |            |

---

# machine QForward

> Single-qubit forward pass: prepare with an Ry(theta) rotation, then measure.

## context
| Field | Type  | Default |
|-------|-------|---------|
| theta | float | 0.5     |

## events
- prepare
- measure_out

## state |q0> [initial]
> Ground state.

## state |prepared>
> After the parameterized rotation.

## state |measured> [final]
> Measured into bits[0].

## transitions
| Source      | Event       | Guard | Target      | Action  |
|-------------|-------------|-------|-------------|---------|
| |q0>        | prepare     |       | |prepared>  | rotate  |
| |prepared>  | measure_out |       | |measured>  | meas    |

## actions
| Name   | Signature  | Effect                    |
|--------|------------|---------------------------|
| rotate | (qs) -> qs | Ry(qs[0], theta)          |
| meas   | (qs) -> qs | measure(qs[0]) -> bits[0] |

## returns
| Name    | Type | Statistics             |
|---------|------|------------------------|
| bits[0] | bit  | expectation, histogram |
