## ADDED Requirements

### Requirement: Detector and Observable Emission

The compiler SHALL provide `compile_to_stim_with_detectors(machine)` returning a
`stim.Circuit` that, in addition to the Clifford gates, measurements, and noise
of `compile_to_stim`, emits a `DETECTOR` annotation for each **stabilizer**
measurement and an `OBSERVABLE_INCLUDE` annotation for the **logical** readout. A
measurement of a qubit whose declared role (via the shipped qubit-role tags) is
`ancilla` or `syndrome` is a stabilizer measurement; a measurement of a `data`
qubit contributes to the logical observable. For a stabilizer measured across
multiple rounds, the detector SHALL be the parity of that stabilizer's records in
consecutive rounds (so it is deterministic absent noise); for its first round the
detector is the single record. When the machine declares no `ancilla`/`syndrome`
roles, the compiler SHALL raise a structured error directing the user to tag the
syndrome qubits, rather than emit a circuit with no detectors.

#### Scenario: Stabilizer measurement becomes a detector

- **WHEN** a machine measures a qubit declared with role `ancilla`
- **THEN** the emitted Stim circuit contains a `DETECTOR` referencing that
  measurement's record

#### Scenario: Data measurement contributes to the observable

- **WHEN** a machine measures its `data` qubits at the end
- **THEN** the emitted Stim circuit contains an `OBSERVABLE_INCLUDE` over those
  data-measurement records

#### Scenario: Cross-round detector pairs consecutive rounds

- **WHEN** the same stabilizer qubit is measured in two consecutive rounds
- **THEN** the second round's `DETECTOR` references both that round's record and
  the previous round's record for that stabilizer

#### Scenario: Untagged machine is refused

- **WHEN** `compile_to_stim_with_detectors` is given a machine with no
  `ancilla`/`syndrome` roles
- **THEN** it raises a structured error directing the user to tag syndrome qubits
