## ADDED Requirements

### Requirement: Reset Execution

The iterative runtime SHALL execute a `reset(qs[i])` effect by re-initialising
qubit `i` to |0⟩ (collapsing it if it carried amplitude), so that subsequent
operations on `i` act on a fresh |0⟩. A reset on a just-measured qubit clears it
for reuse; a reset on an unmeasured qubit forces it to |0⟩.

#### Scenario: Reset re-initialises a flipped qubit

- **WHEN** qubit 0 is set to |1⟩ and then `reset(qs[0])` runs
- **THEN** a subsequent measurement of qubit 0 yields 0

#### Scenario: Reset clears a measured ancilla for reuse

- **WHEN** an ancilla is measured, reset, and re-entered into a second
  syndrome-extraction round
- **THEN** the second round's extraction acts on the ancilla in |0⟩
