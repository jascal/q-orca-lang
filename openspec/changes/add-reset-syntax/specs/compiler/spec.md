## ADDED Requirements

### Requirement: Reset Compilation and MR Coalescing

The Clifford classifier SHALL treat `reset` as a stabilizer-compatible operation
(not a non-Clifford gate), so a machine that resets reaches the stabilizer
fast path. `compile_to_stim` SHALL emit Stim `R i` for `reset(qs[i])`, and SHALL
emit `MR i` (measure-and-reset, a single instruction advancing one measurement
record) when a `measure(qs[i]) -> bits[j]` is immediately followed — on the same
qubit, with no intervening operation on it — by `reset(qs[i])`. The `bit → record`
map and `rec[-N]` feedforward indexing SHALL be unchanged by the `M`→`MR` swap.

#### Scenario: Reset machine is Clifford and emits R

- **WHEN** a Clifford machine contains `reset(qs[0])`
- **THEN** `is_clifford` returns true and `compile_to_stim` emits `R 0`

#### Scenario: Measure-then-reset coalesces to MR

- **WHEN** an ancilla is measured and then reset on the same qubit with nothing
  between
- **THEN** `compile_to_stim` emits a single `MR` for that qubit (not `M` then `R`)

### Requirement: Multi-Round Detector Emission

`compile_to_stim_with_detectors` SHALL support multi-round (circuit-level)
decoding once reset re-initialises an ancilla between rounds. For a stabilizer
measured in more than one round, the first round SHALL emit a single-record
`DETECTOR` and each subsequent round SHALL emit a **cross-round** `DETECTOR` over
that round's record and the same stabilizer's previous-round record (the parity
of consecutive rounds, deterministic absent noise). The round structure is
recovered from the unrolled `[loop N]` body.

#### Scenario: Second round emits a cross-round detector

- **WHEN** a stabilizer ancilla is measured (and reset) in two consecutive rounds
- **THEN** the second round's `DETECTOR` references both that round's record and
  the previous round's record for that stabilizer

#### Scenario: Multi-round repetition code decodes correctly

- **WHEN** a multi-round (ancilla-reset) repetition code is compiled with detectors
  and decoded
- **THEN** the circuit carries cross-round detectors, the detector error model is
  well-formed, and the logical error rate is sane (no decoder error)

> The quantitative *improves-with-rounds* benefit appears only under the full
> phenomenological noise model (noisy logical readout + per-round data noise);
> emitting the cross-round detectors correctly is the compiler's job and is what
> this requirement pins. Tuning a phenomenological example to exhibit the
> threshold trend is a follow-on.
