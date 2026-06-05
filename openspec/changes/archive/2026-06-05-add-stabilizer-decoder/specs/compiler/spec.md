## ADDED Requirements

### Requirement: Detector and Observable Emission

The compiler SHALL provide `compile_to_stim_with_detectors(machine)` returning a
`stim.Circuit` that, in addition to the Clifford gates, measurements, and noise
of `compile_to_stim`, emits a `DETECTOR` annotation for each **stabilizer**
measurement and an `OBSERVABLE_INCLUDE` annotation for the **logical** readout. A
measurement of a qubit whose declared role (via the shipped qubit-role tags) is
`ancilla` or `syndrome` is a stabilizer measurement; a measurement of a `data`
qubit contributes to the logical observable. In v1 (single-round / code-capacity
decoding) each stabilizer is measured once, so its detector is that single
measurement record (deterministic absent noise). (Multi-round cross-round
detectors require `reset` between rounds, which q-orca lacks; they are deferred
to a reset-syntax change.) When the machine declares no `ancilla`/`syndrome`
roles, when no stabilizer measurements are present, or when the data readout does
not cover a logical operator, the compiler SHALL raise a structured, actionable
error naming the offending qubit(s) and the fix (e.g. "add roles: ancilla/syndrome
to your stabilizer qubits") — rather than emit a circuit with no detectors or a
degenerate observable.

#### Scenario: Stabilizer measurement becomes a detector

- **WHEN** a machine measures a qubit declared with role `ancilla`
- **THEN** the emitted Stim circuit contains a `DETECTOR` referencing that
  measurement's record

#### Scenario: Data measurement contributes to the observable

- **WHEN** a machine measures its `data` qubits at the end
- **THEN** the emitted Stim circuit contains an `OBSERVABLE_INCLUDE` over those
  data-measurement records

#### Scenario: Untagged machine is refused

- **WHEN** `compile_to_stim_with_detectors` is given a machine with no
  `ancilla`/`syndrome` roles
- **THEN** it raises a structured error directing the user to tag syndrome qubits
