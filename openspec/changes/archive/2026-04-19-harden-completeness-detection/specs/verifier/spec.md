## MODIFIED Requirements

### Requirement: Completeness Check

Unless `VerifyOptions.skip_completeness` is set, the verifier SHALL
enforce that every `(state, event)` pair has at least one transition,
with an exception for "quantum preparation paths". A machine is
treated as a preparation path if it has at least one **measurement
event** AND more than half of its non-final states have exactly one
outgoing transition; in that case only the first-indexed event per
state is required.

An event is a **measurement event** if either:

1. Its name, lowercased, contains any of the substrings `measure`,
   `collapse`, or `readout`; OR
2. Some transition triggered by the event references an action whose
   `QActionSignature` carries a non-None `measurement` or
   `mid_circuit_measure` effect (i.e., the action's parsed effect is
   a measurement or a mid-circuit measurement).

Either signal alone is sufficient — the detector takes the union.

#### Scenario: Missing event handler

- **WHEN** a non-final state in a non-preparation machine fails to
  handle a declared event
- **THEN** the verifier emits `INCOMPLETE_EVENT_HANDLING` at error severity

#### Scenario: Measurement detected by event name

- **WHEN** a machine has an event named `collapse` with no action
  attached and more than half its non-final states have one outgoing
  transition
- **THEN** the machine is treated as a preparation path and the
  every-state-handles-every-event rule is relaxed

#### Scenario: Measurement detected by action effect

- **WHEN** a machine has an event named `read_error` whose transition
  action has a `mid_circuit_measure` effect (e.g.,
  `measure(qs[2]) -> bits[0]`) and more than half its non-final
  states have one outgoing transition
- **THEN** the machine is treated as a preparation path and the
  verifier does NOT emit `INCOMPLETE_EVENT_HANDLING` for unhandled
  events on non-terminal states

#### Scenario: No measurement signal at all

- **WHEN** a machine has no event whose name matches the measurement
  substrings AND no transition action with a measurement or
  mid-circuit-measurement effect
- **THEN** the machine is NOT treated as a preparation path and the
  standard every-state-handles-every-event rule applies
