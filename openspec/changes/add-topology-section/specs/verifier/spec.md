## ADDED Requirements

### Requirement: Topology Consistency

The verifier SHALL validate a `## topology` section's internal consistency, emitting at error severity: `TOPOLOGY_UNKNOWN_DEVICE` when `### device` names a device not in the shipped registry; `TOPOLOGY_INCONSISTENT` when an inline `### coupling_map` is given alongside a `### device` and its edges are not a subgraph of the device map; and `TOPOLOGY_INSUFFICIENT_QUBITS` when the declared logical-qubit count exceeds the physical-qubit count with no `### mapping` resolving them.

When `### mapping` is absent and the device has more physical qubits than the machine has logical qubits, the verifier SHALL accept with a `TOPOLOGY_IDENTITY_MAPPING_NARROW` warning (the identity mapping is assumed).

#### Scenario: Unknown device rejected

- **WHEN** `### device` names `ibm_nonesuch`
- **THEN** the verifier emits `TOPOLOGY_UNKNOWN_DEVICE`

#### Scenario: Inline edges not a subgraph of the named device

- **WHEN** a section gives `### device ibm_brisbane` and an inline `### coupling_map` edge absent from the heavy-hex graph
- **THEN** the verifier emits `TOPOLOGY_INCONSISTENT`

#### Scenario: Identity mapping on a wide device warns

- **WHEN** a 4-logical-qubit machine targets a 156-physical-qubit device with no `### mapping`
- **THEN** the verifier accepts with `TOPOLOGY_IDENTITY_MAPPING_NARROW`

### Requirement: Two-Qubit Adjacency

The verifier SHALL walk every two-qubit gate in the machine's action effects, resolve its qubit targets through the logical-to-physical mapping, and assert that the resulting physical pair is an edge of the declared coupling map — emitting `TOPOLOGY_NON_ADJACENT_GATE` at error severity otherwise, with the offending gate's location and a suggestion to insert a SWAP or re-map. The walk SHALL recurse into `invoke:` children using the parent's mapping. When both `TOPOLOGY_NON_ADJACENT_GATE` and a routed-CX `RESOURCE_BOUND_EXCEEDED` apply, topology is reported first.

#### Scenario: Adjacent two-qubit gate accepted

- **WHEN** a machine targets `device: linear_4` and applies `CNOT(qs[0], qs[1])`
- **THEN** the verifier emits no `TOPOLOGY_NON_ADJACENT_GATE`

#### Scenario: Non-adjacent two-qubit gate rejected

- **WHEN** a machine targets `device: linear_4` and applies `CNOT(qs[0], qs[2])`
- **THEN** the verifier emits `TOPOLOGY_NON_ADJACENT_GATE` with the gate location and a SWAP/re-map suggestion
