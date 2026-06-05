# machine BitFlipCode

> Distance-3 bit-flip repetition code, one syndrome round — **code-capacity
> decoding**. The logical qubit `|0_L> = |000>` is the all-zero codeword. A
> `## noise_model` injects independent `X` (bit-flip) errors on the three data
> qubits; two ancilla measure the `Z₀Z₁` and `Z₁Z₂` stabilizers; and the data
> are read out. The single-shot syndrome is decoded by minimum-weight perfect
> matching (`q_orca.evaluation.qec.logical_error_rate`) — corrections are
> classical post-processing, not in-circuit feedforward.

## context

| Field  | Type        | Default                                              |
|--------|-------------|------------------------------------------------------|
| qubits | list<qubit> | [q0:data, q1:data, q2:data, q3:ancilla, q4:ancilla]  |
| bits   | list<bit>   | [s0, s1, m0, m1, m2]                                  |

## noise_model

| Channel  | Target        | Parameters |
|----------|---------------|------------|
| bit_flip | qs[role:data] | p=0.05     |

## events

- extract
- read_s0
- read_s1
- read_d0
- read_d1
- read_d2

## state |encoded> [initial]

> Logical |0_L> = |000> — the all-zero state is already a codeword, so no
> encoding gates are needed.

## state |extracted>

> Syndrome coupled into the ancilla: a0 holds Z₀Z₁, a1 holds Z₁Z₂.

## state |s0_read>
## state |syndrome>
## state |d0_read>
## state |d1_read>
## state |measured> [final]

## transitions

| Source        | Event   | Guard | Target        | Action           |
|---------------|---------|-------|---------------|------------------|
| |encoded>     | extract | | |extracted>   | extract_syndrome |
| |extracted>   | read_s0 | | |s0_read>     | meas_s0          |
| |s0_read>     | read_s1 | | |syndrome>    | meas_s1          |
| |syndrome>    | read_d0 | | |d0_read>     | meas_d0          |
| |d0_read>     | read_d1 | | |d1_read>     | meas_d1          |
| |d1_read>     | read_d2 | | |measured>    | meas_d2          |

## actions

| Name             | Signature  | Effect                                                                |
|------------------|------------|-----------------------------------------------------------------------|
| extract_syndrome | (qs) -> qs | CNOT(qs[0], qs[3]); CNOT(qs[1], qs[3]); CNOT(qs[1], qs[4]); CNOT(qs[2], qs[4]) |
| meas_s0          | (qs) -> qs | measure(qs[3]) -> bits[0]                                             |
| meas_s1          | (qs) -> qs | measure(qs[4]) -> bits[1]                                             |
| meas_d0          | (qs) -> qs | measure(qs[0]) -> bits[2]                                             |
| meas_d1          | (qs) -> qs | measure(qs[1]) -> bits[3]                                             |
| meas_d2          | (qs) -> qs | measure(qs[2]) -> bits[4]                                             |

## verification rules

- unitarity: all non-measurement gates preserve norm
