## ADDED Requirements

### Requirement: Clifford Classification

The compiler SHALL provide a Clifford classifier that walks a machine's
flattened gate effects and reports whether the circuit is Clifford-only.
A circuit is Clifford when every gate is drawn from `{H, S, Sdg, X, Y, Z,
CX, CY, CZ, SWAP}`, a Pauli measurement, or a classically-controlled
Pauli correction; and every parametric rotation `Rx/Ry/Rz(θ)` has an
angle that simplifies (via the shipped angle evaluator) to a multiple of
`π/2` (i.e. `{0, π/2, π, 3π/2}`). The classifier SHALL return the list of
offending gates (with source spans) when the circuit is not Clifford.
Gate-name membership SHALL be derived from the canonical `KNOWN_UNITARY_GATES`
set so that a newly added gate is treated as non-Clifford until it is
explicitly classified.

When the stabilizer backend is forced (`backend: stabilizer` or `stim`)
on a machine the classifier rejects, the compiler SHALL raise
`NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND` naming the first offending gate
and its source location. The error is fatal unless
`stabilizer_fallback: state-vector` is declared, in which case the
compiler SHALL emit a warning and select the state-vector path.

#### Scenario: All-Clifford machine classified as Clifford

- **WHEN** a machine's effects use only `H`, `CNOT`, and Pauli measurement
- **THEN** the classifier returns Clifford with an empty offending-gate list

#### Scenario: Arbitrary-angle rotation classified as non-Clifford

- **WHEN** a machine applies `Rz(theta)` with `theta` outside `{0, π/2, π, 3π/2}`
- **THEN** the classifier returns non-Clifford and includes that `Rz` gate
  in the offending-gate list

#### Scenario: Clifford-angle rotation accepted

- **WHEN** a machine applies `Rz(π/2)` (equivalently `S`) and `Rx(π)`
  (equivalently `X`)
- **THEN** the classifier returns Clifford

#### Scenario: Forcing stabilizer on a non-Clifford machine is fatal

- **WHEN** a machine declares `backend: stabilizer`, has no
  `stabilizer_fallback`, and contains a `CCX` gate
- **THEN** the compiler raises `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND`
  naming the `CCX` gate and its location

#### Scenario: Declared fallback downgrades the force error to a warning

- **WHEN** a machine declares `backend: stabilizer` and
  `stabilizer_fallback: state-vector` and contains a `CCX` gate
- **THEN** the compiler emits a warning and selects the state-vector path

### Requirement: Stabilizer Compilation Targets

The compiler SHALL compile a Clifford machine to a stabilizer-simulable
circuit on two targets: a Stim circuit (`compile_to_stim`) mapping each
Clifford gate to its Stim primitive, mid-circuit `measure` to `MR`
(measure-reset, when a `reset` effect follows the measurement) or `M`
otherwise, and classically-controlled Pauli corrections to Stim's
`rec[-1]`-targeted instructions; and an `AerSimulator(method="stabilizer")`
circuit reusing the existing Qiskit compilation, switching only the
simulator method. Both targets SHALL preserve circuit semantics so that
the sampled outcome distribution matches the state-vector backend within
statistical tolerance.

#### Scenario: Clifford gate sequence maps to Stim primitives

- **WHEN** `compile_to_stim` is given a machine applying `H` then `CNOT`
- **THEN** the emitted Stim circuit contains the corresponding `H` and
  `CX` instructions

#### Scenario: Mid-circuit measure-and-reset maps to MR

- **WHEN** a machine measures an ancilla and a `reset` effect follows on
  the same qubit
- **THEN** the emitted Stim circuit uses an `MR` instruction for that qubit

#### Scenario: Stabilizer distribution matches state-vector

- **WHEN** `active-teleportation` is verified on both the stabilizer and
  the QuTiP backend at `shots=10000`
- **THEN** the two outcome distributions agree within the statistical
  tolerance
