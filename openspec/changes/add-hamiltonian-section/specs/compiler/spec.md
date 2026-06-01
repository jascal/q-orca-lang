## ADDED Requirements

### Requirement: Qubit-Wise Commuting Measurement Grouping

The compiler SHALL expose a grouping routine (`q_orca/compiler/measurement_grouping.py`) that partitions a Hamiltonian's terms into qubit-wise-commuting groups: two terms share a group when their non-identity Pauli factors never disagree on any shared qubit, so the group can be measured in a single shared basis (Peruzzo et al. 2014). The grouping SHALL be deterministic for a given term order.

#### Scenario: Commuting terms share a group

- **WHEN** a Hamiltonian contains `Z @ q0` and `Z @ q1`
- **THEN** the grouper places them in a single group (both measured in the Z basis)

#### Scenario: Non-qubit-wise-commuting terms split

- **WHEN** a Hamiltonian on `[q0, q1]` contains `XX`, `YY`, and `ZZ`
- **THEN** the grouper produces three groups (distinct measurement bases)

### Requirement: Hamiltonian Measurement Circuit Emission

The Qiskit and QASM backends SHALL each build one measurement circuit per commuting group: the ansatz-prepared state followed by the per-qubit basis-rotation gates for that group (e.g. `H` before measuring `X`, `Sdg; H` before `Y`, identity for `Z`) and a terminal measurement of the group's qubits. The basis rotations are emitted from the Hamiltonian section, not hand-coded in an action effect.

#### Scenario: Single-Pauli Hamiltonian emits one circuit

- **WHEN** `## hamiltonian H` is `1.0 | Z | [q0]` and a measurement circuit is built for `H`
- **THEN** exactly one measurement circuit is emitted, measuring `q0` in the computational basis

#### Scenario: Commuting-group batching emits one circuit per group

- **WHEN** `## hamiltonian H` is `XX + YY + ZZ` on `[q0, q1]`
- **THEN** three measurement circuits are emitted, one per group, each with its group's basis-rotation prefix
