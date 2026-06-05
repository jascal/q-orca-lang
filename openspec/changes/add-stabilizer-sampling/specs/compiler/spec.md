## ADDED Requirements

### Requirement: Stabilizer Compilation Targets

The compiler SHALL compile a Clifford machine to a runnable stabilizer circuit on
two targets. The primary target is a Stim circuit (`compile_to_stim`) that maps
each Clifford gate to its Stim primitive (reusing the v1 gate mapping, including
`π/2` rotations), maps `measure(qs[i]) -> bits[j]` to `MR` when a `reset` effect
follows the same qubit in the action stream and to `M` otherwise, and maps a
classically-controlled Pauli feedforward (`if bits[j] == 1: X/Z(qs[k])`) to
Stim's measurement-record-controlled `CX`/`CZ rec[-N]` instruction, where `N` is
the relative offset of `bits[j]`'s measurement record at the point the
correction is emitted. The secondary target is an
`AerSimulator(method="stabilizer")` circuit (`compile_to_qiskit_stabilizer`)
reusing the existing Qiskit compilation. The compiler SHALL maintain a
`bit-index → measurement-record-position` map so that each feedforward
correction references the record of the bit it names.

#### Scenario: Clifford gate sequence maps to Stim primitives

- **WHEN** `compile_to_stim` is given a machine applying `H(qs[0])` then
  `CNOT(qs[0], qs[1])`
- **THEN** the emitted Stim circuit contains the corresponding `H` and `CX`
  instructions on those qubits

#### Scenario: Mid-circuit measure-and-reset maps to MR

- **WHEN** an action measures `qs[0]` and a `reset(qs[0])` effect follows on the
  same qubit
- **THEN** the emitted Stim circuit uses an `MR` instruction for that qubit

#### Scenario: Measurement without a following reset maps to M

- **WHEN** an action measures `qs[0]` with no subsequent `reset` on `qs[0]`
- **THEN** the emitted Stim circuit uses an `M` instruction for that qubit

#### Scenario: Feedforward references the correct measurement record

- **WHEN** `bits[0]` is measured first, `bits[1]` second, and the machine
  declares `if bits[0] == 1: Z(qs[2])`
- **THEN** the emitted Stim circuit applies a `CZ rec[-2] 2` instruction (the
  record of `bits[0]`, not the most recent record)

### Requirement: Stabilizer Sampling Distribution Equivalence

The Stim-sampled measurement-outcome distribution of a Clifford machine SHALL
match the state-vector backend's distribution within a statistical bound at a
fixed shot count and seed, including circuits with mid-circuit measurement and
classical feedforward.

#### Scenario: Terminal-measurement distribution matches state-vector

- **WHEN** a Bell or GHZ machine is sampled on the Stim target and on the QuTiP
  state-vector path at `shots=10000` with a fixed seed
- **THEN** every outcome's frequency agrees within a Wilson-score interval

#### Scenario: Feedforward distribution matches state-vector

- **WHEN** `active-teleportation` (two measured bits feeding forward to two
  distinct corrections) is sampled on the Stim target and on the QuTiP path at
  `shots=10000`
- **THEN** the teleported-qubit outcome distributions agree within the bound
