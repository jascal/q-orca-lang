## Why

The shipped `add-stabilizer-backend` change delivered the Clifford *verification*
fast path: `verify()` reads entanglement from the stabilizer tableau in
polynomial time. It deliberately deferred the **sampling** path — compiling a
machine to a runnable stabilizer *circuit* and drawing measurement shots — which
is what proves the compilation is semantically correct (the canonical
distribution-parity check the reviewer flagged as the right validation) and is
the gateway to randomized-benchmarking sweeps and decoder-benchmarking work.
This change implements that deferred sampling sub-feature on top of the shipped
`is_clifford` classifier and `StimBackend`.

## What Changes

- Add `compile_to_stim(machine) -> stim.Circuit` in `q_orca/compiler/stabilizer.py`:
  map each Clifford gate to its Stim primitive; `measure(qs[i]) -> bits[j]` to
  `MR` (when a `reset` effect follows the same qubit) or `M`; and
  classically-controlled Pauli feedforward (`if bits[j] == 1: X/Z(qs[k])`) to
  Stim's measurement-record-controlled `CX`/`CZ rec[-N]` instructions, tracking
  the bit→measurement-record index as measurements are emitted.
- Add an optional `AerSimulator(method="stabilizer")` compilation target
  (`compile_to_qiskit_stabilizer`) reusing the existing Qiskit compiler, as a
  secondary engine / fallback when Stim is absent but `qiskit-aer` is present.
- Add a **distribution-parity** validation: the Stim-sampled outcome
  distribution matches the QuTiP state-vector distribution within a Wilson-score
  statistical bound at `shots=10000` (seeded) — for Bell/GHZ terminal
  measurement and the `active-teleportation` feedforward circuit.
- Add two authored QEC examples that the shipped verify path already accepts and
  which exercise the sampling path: `examples/surface-code-3.q.orca.md`
  (distance-3 rotated surface code, ~17 physical qubits) and
  `examples/bit-flip-repeated.q.orca.md` (three syndrome rounds).

Out of scope (separate follow-ons): wiring the stabilizer sampler into the
`q-orca run` / `simulate` path, the Clifford+T magic-state extension, and Stim
detector-error-model export for decoder benchmarking.

## Capabilities

### New Capabilities
<!-- none — extends the existing compiler capability, matching the shipped backend work -->

### Modified Capabilities
- `compiler`: add the **Stabilizer Compilation Targets** requirement
  (`compile_to_stim` with `MR`/`M` + `rec[-N]` feedforward, and the
  Aer-stabilizer target) — the requirement deferred from `add-stabilizer-backend`
  — plus a **Stabilizer Sampling Distribution Equivalence** requirement pinning
  parity with the state-vector backend.

## Impact

- New code: `compile_to_stim` + `compile_to_qiskit_stabilizer` (+ a measurement/
  feedforward record tracker) in `q_orca/compiler/stabilizer.py`; a sampling
  helper that runs a compiled circuit and returns counts; two example files.
- New tests: `compile_to_stim` gate/measurement/feedforward mapping; the
  shots=10000 distribution-parity vs QuTiP; the two examples parse + verify +
  sample.
- New optional dependency surface is unchanged (`stim`, `qiskit-aer` already in
  the `stabilizer` / `quantum` extras).
- **Dependencies**: builds on shipped `add-stabilizer-backend` (the `is_clifford`
  classifier, `StimBackend`, and the `## assertion policy` backend selection).
  The **feedforward `rec[-N]` mapping is the highest-risk part** and is gated by
  the `active-teleportation` distribution-parity test (see design).
