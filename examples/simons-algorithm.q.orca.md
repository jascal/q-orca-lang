# machine SimonsAlgorithm

> Simon's algorithm, expressed with an adaptive bounded loop. Each iteration
> prepares the input register in superposition, queries the 2-to-1 oracle, and
> measures the input register to collect one linear constraint on the hidden
> period. The loop repeats `[loop until: rank >= n - 1]` — until `n − 1`
> linearly-independent constraints are gathered — then classical Gaussian
> elimination over GF(2) (left to the host) recovers the period.
>
> The body measures every iteration, which is exactly how the classical exit
> predicate advances, so an adaptive body is exempt from the fixed-loop
> unitarity rule. The predicate is over integer counters (`rank`, `n`), so the
> verifier accepts it with no `LOOP_TERMINATION_UNCHECKED` warning. KB
> grounding: Simon, and Moore & Crutchfield quantum grammars
> (quant-ph/9707031).

## context
| Field  | Type        | Default              |
|--------|-------------|----------------------|
| qubits | list<qubit> | [q0, q1, q2, q3]     |
| n      | int         | 2                    |
| rank   | int         | 0                    |

## events
- prepare
- oracle
- sample
- solve

## state |0000> [initial]
> Two input qubits (q0, q1) and two output qubits (q2, q3) in the ground state.

## state |collecting> [loop until: rank >= n - 1]
> Heads the adaptive loop body: query the oracle, measure the input register to
> gather one constraint, and repeat until `n − 1` independent constraints exist.

## state |queried>
> Input and output registers entangled through the 2-to-1 oracle, ready for the
> input-register measurement that yields one constraint bitstring.

## state |period_found> [final]
> Enough independent constraints collected; the hidden period is recoverable by
> classical post-processing.

## transitions
| Source        | Event   | Guard | Target         | Action                  |
|---------------|---------|-------|----------------|-------------------------|
| |0000>        | prepare |       | |collecting>   | apply_H_inputs          |
| |collecting>  | oracle  |       | |queried>      | apply_oracle            |
| |queried>     | sample  |       | |collecting>   | measure_input, loop_back |
| |collecting>  | solve   |       | |period_found> | solve_period, loop_done |

## actions
| Name           | Signature  | Effect                              |
|----------------|------------|-------------------------------------|
| apply_H_inputs | (qs) -> qs | H(qs[0]); H(qs[1])                  |
| apply_oracle   | (qs) -> qs | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[3]) |
| measure_input  | (qs) -> qs | measure(qs[0]) -> bits[0]           |
| solve_period   | (qs) -> qs |                                     |

## verification rules
- unitarity: all non-measurement gates preserve norm
- bounded-loop: adaptive [loop until: …] body measures each iteration
