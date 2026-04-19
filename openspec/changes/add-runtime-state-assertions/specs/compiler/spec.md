## ADDED Requirements

### Requirement: Assertion Metadata Pass-Through

The compiler SHALL carry per-state assertion annotations through to the
emitted artifact as out-of-band metadata. No assertion SHALL produce a
new instruction, gate, or measurement in any backend's emitted output —
real-device execution MUST be unaffected by the presence or absence of
`[assert: …]` annotations.

The Qiskit backend (`compile_to_qiskit`) SHALL attach an
`assertion_probe: list[QAssertion]` field to its existing per-state
metadata block at the point in the gate sequence corresponding to the
named state. The Stage 4b verifier consumes this field via
`q_orca.verifier.assertions.check_state_assertions`.

The QASM backend (`compile_to_qasm`) SHALL emit, immediately before the
gate sequence for the next transition out of an annotated state, one
comment line per assertion of the form:

```
// assert: <category>(<qubit-slice>[, <qubit-slice>]*) @ state <state-name>
```

QASM comment emission SHALL preserve the source order of assertions
within a single state. Comment lines SHALL be the only QASM artifact
produced by `[assert: …]` annotations.

The Mermaid backend (`compile_to_mermaid`) MAY annotate a state node's
description with a brief `assert:` summary but SHALL NOT introduce new
state nodes, transitions, or labels for assertions.

#### Scenario: Qiskit backend attaches assertion probe metadata

- **WHEN** a machine has a state declared
  `[assert: entangled(qs[0], qs[1])]` and `compile_to_qiskit` is called
- **THEN** the Qiskit script's per-state metadata for that state
  includes `assertion_probe` with one `QAssertion` whose
  `category="entangled"` and `targets=[QubitSlice(0), QubitSlice(1)]`

#### Scenario: Qiskit backend emits no new gates for assertions

- **WHEN** a Bell-pair machine with no assertions and the same machine
  with `[assert: entangled(qs[0], qs[1])]` are both compiled by
  `compile_to_qiskit`
- **THEN** the two scripts are identical except for the
  `assertion_probe` metadata field — the gate sequence
  (`qc.h(0); qc.cx(0, 1)`) is byte-identical

#### Scenario: QASM backend emits comment line per assertion

- **WHEN** a machine has a state `|encoded>` declared
  `[assert: superposition(qs[0..2]); entangled(qs[0], qs[1])]` and
  `compile_to_qasm` is called
- **THEN** the emitted QASM contains the lines
  `// assert: superposition(q[0..2]) @ state encoded` and
  `// assert: entangled(q[0], q[1]) @ state encoded` in source order,
  positioned before the gate sequence for the next outgoing transition

#### Scenario: QASM backend emits no instructions for assertions

- **WHEN** a machine with assertions is compiled by `compile_to_qasm`
  and the output is parsed by an OpenQASM 3.0 lint tool
- **THEN** the only assertion-related lines are comments and the
  instruction count matches the same machine compiled with assertions
  removed

#### Scenario: Mermaid backend renders without new states

- **WHEN** a machine with assertions is compiled by `compile_to_mermaid`
- **THEN** the emitted Mermaid diagram has the same node count and
  transition count as the same machine compiled with assertions
  removed
