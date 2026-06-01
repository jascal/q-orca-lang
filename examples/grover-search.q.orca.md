# machine GroverSearch

> Grover's search over an `N`-item space, expressed with a bounded loop.
> Uniform superposition, then `ceil(pi/4 * sqrt(N))` repetitions of the
> oracle + diffuser as a single `[loop …]`-annotated body, then measurement.
> The loop body is unitary (no measurement), so the verifier checks it once;
> the compiler emits one QASM 3 `for` block instead of unrolling the iterate
> step. KB grounding: Grover, quant-ph/9602019.

## context
| Field  | Type        | Default        |
|--------|-------------|----------------|
| qubits | list<qubit> | [q0, q1, q2]   |
| N      | int         | 8              |

## events
- prepare
- enter
- iterate
- measure

## state |000> [initial]
> Computational ground state of the 3-qubit search register.

## state |uniform>
> Equal superposition over all `N` items after Hadamards on every qubit.

## state |amplifying> [loop ceil(pi/4 * sqrt(N))]
> Heads the loop body: the oracle + diffuser iterate runs
> `ceil(pi/4 * sqrt(N))` times, concentrating amplitude on the marked item.

## state |measured> [final]
> Amplitude is concentrated on the marked item; the register is read out.

## transitions
| Source       | Event   | Guard | Target       | Action                    |
|--------------|---------|-------|--------------|---------------------------|
| |000>        | prepare |       | |uniform>    | apply_H_all               |
| |uniform>    | enter   |       | |amplifying> | begin_search              |
| |amplifying> | iterate |       | |amplifying> | grover_iterate, loop_back |
| |amplifying> | measure |       | |measured>   | read_out, loop_done       |

## actions
| Name           | Signature  | Effect                                                                 |
|----------------|------------|------------------------------------------------------------------------|
| apply_H_all    | (qs) -> qs | H(qs[0]); H(qs[1]); H(qs[2])                                           |
| begin_search   | (qs) -> qs |                                                                        |
| grover_iterate | (qs) -> qs | CZ(qs[0], qs[1]); H(qs[0]); H(qs[1]); H(qs[2]); X(qs[0]); X(qs[1]); X(qs[2]); H(qs[2]); CZ(qs[0], qs[1]); H(qs[2]); X(qs[0]); X(qs[1]); X(qs[2]); H(qs[0]); H(qs[1]); H(qs[2]) |
| read_out       | (qs) -> qs |                                                                        |

## verification rules
- unitarity: all gates preserve norm
- bounded-loop: the [loop …] body is unitary and runs a fixed number of times
- measurement_collapse_allowed: |measured> is the intended collapse sink — reading out the marked item after `ceil(pi/4 * sqrt(N))` iterations is the terminal step
