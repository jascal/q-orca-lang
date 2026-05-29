# machine PrepareBellPair

> Reusable Bell-pair preparation primitive.

## context
| Field | Type | Default |
|-------|------|---------|
| seed  | int  | 0       |

## events
- run

## state |q0> [initial]
## state |bell> [final]

## transitions
| Source | Event | Guard | Target | Action     |
|--------|-------|-------|--------|------------|
| |q0>   | run   |       | |bell> | make_bell  |

## actions
| Name      | Signature  | Effect                            |
|-----------|------------|-----------------------------------|
| make_bell | (qs) -> qs | Hadamard(qs[0]); CNOT(qs[0], qs[1]) |
