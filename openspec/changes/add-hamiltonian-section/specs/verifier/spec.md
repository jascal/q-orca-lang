## ADDED Requirements

### Requirement: Hamiltonian Hermiticity

The verifier SHALL confirm that every coefficient in a `## hamiltonian` section evaluates to a real value, emitting `HAMILTONIAN_NON_HERMITIAN` at error severity for any coefficient that resolves to a complex value, with a location pointing at the offending row.

A weighted sum of Pauli strings is Hermitian iff all coefficients are real (each Pauli string is itself Hermitian), so a real-coefficient check is sufficient.

#### Scenario: Complex coefficient rejected

- **WHEN** a Hamiltonian term has coefficient `1.0 + 0.1j`
- **THEN** the verifier emits `HAMILTONIAN_NON_HERMITIAN` naming the offending row

#### Scenario: Real coefficients accepted

- **WHEN** every coefficient evaluates real (literal or via `evaluate_angle`)
- **THEN** no `HAMILTONIAN_NON_HERMITIAN` is emitted

### Requirement: Hamiltonian Pauli/Qubit Index Validity

The verifier SHALL confirm, for every Hamiltonian term, that the Pauli string length equals the `Qubits` list length and that every listed qubit index is within the machine's declared register, emitting `HAMILTONIAN_PAULI_OUT_OF_RANGE` at error severity otherwise.

#### Scenario: Length mismatch rejected

- **WHEN** a term pairs the Pauli string `XX` with a single-qubit list `[q0]`
- **THEN** the verifier emits `HAMILTONIAN_PAULI_OUT_OF_RANGE`

#### Scenario: Out-of-register index rejected

- **WHEN** a term references a qubit index not present in the declared `qubits` register
- **THEN** the verifier emits `HAMILTONIAN_PAULI_OUT_OF_RANGE`
