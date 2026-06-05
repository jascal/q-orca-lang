## ADDED Requirements

### Requirement: Stabilizer Compilation Targets

The compiler SHALL compile a Clifford machine to a runnable stabilizer circuit on
two targets. The primary target is a Stim circuit (`compile_to_stim`) that maps
each Clifford gate to its Stim primitive (reusing the v1 gate mapping, including
`π/2` rotations), maps `measure(qs[i]) -> bits[j]` to a Stim `M` measurement, and
maps a single-clause classically-controlled Pauli feedforward
(`if bits[j] == 1: X/Y/Z(qs[k])`) to Stim's measurement-record-controlled
`CX`/`CY`/`CZ rec[-N]` instruction, where `N` is the relative offset of
`bits[j]`'s measurement record at the point the correction is emitted. The
secondary target is an `AerSimulator(method="stabilizer")` circuit
(`compile_to_qiskit_stabilizer`) reusing the existing Qiskit compilation. The
compiler SHALL maintain a `bit-index → measurement-record-position` map so that
each feedforward correction references the record of the bit it names.

> **Note:** measure-and-reset (`MR`) is not emitted — q-orca has no `reset`
> syntax, so every measurement compiles to `M`. `MR` arrives with reset syntax;
> the compiler's measurement emission is the single point that would change.

#### Scenario: Clifford gate sequence maps to Stim primitives

- **WHEN** `compile_to_stim` is given a machine applying `H(qs[0])` then
  `CNOT(qs[0], qs[1])`
- **THEN** the emitted Stim circuit contains the corresponding `H` and `CX`
  instructions on those qubits

#### Scenario: Mid-circuit measurement maps to M

- **WHEN** an action measures `measure(qs[0]) -> bits[0]`
- **THEN** the emitted Stim circuit uses an `M` instruction for `qs[0]` and
  records the `bits[0] → record` mapping

#### Scenario: Feedforward references the correct measurement record

- **WHEN** `bits[0]` is measured first, `bits[1]` second, and the machine
  declares `if bits[0] == 1: Z(qs[2])`
- **THEN** the emitted Stim circuit applies a `CZ rec[-2] 2` instruction (the
  record of `bits[0]`, not the most recent record)

### Requirement: Stabilizer Compilation Diagnostics

`compile_to_stim` SHALL fail fast with a clear, structured error rather than
emit a silently-wrong circuit when given a construct it cannot represent: a
non-Clifford gate (it MUST reuse the `is_clifford` classifier and refuse a
non-Clifford machine before emitting), a feedforward correction whose gate is
not a Pauli (`X`/`Y`/`Z`), or a feedforward condition that is not the supported
`bits[j] == 0|1` form. Each error SHALL name the offending construct and its
source location.

#### Scenario: Non-Clifford machine refused before emission

- **WHEN** `compile_to_stim` is given a machine containing a `T` gate
- **THEN** it raises a structured error naming the non-Clifford gate, and emits
  no circuit

#### Scenario: Non-Pauli feedforward correction refused

- **WHEN** a feedforward effect applies a non-Pauli correction (e.g.
  `if bits[0] == 1: H(qs[2])`)
- **THEN** `compile_to_stim` raises a structured error naming the unsupported
  correction gate

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
