## ADDED Requirements

### Requirement: Topology-Aware Transpilation

When a `## topology` section is present, the Qiskit backend SHALL pass the declared coupling map and the logical-to-physical layout into `transpile()` (as `coupling_map=` and `initial_layout=`), so the emitted circuit is routed for the target connectivity. The QASM backend SHALL emit a `// device: <name>` (and mapping) comment header, since QASM 3 has no standard device annotation.

#### Scenario: Coupling map reaches transpile

- **WHEN** a machine declares `## topology device: linear_4` and is compiled to Qiskit
- **THEN** the generated transpile call passes a `coupling_map` for `linear_4` and the section's `initial_layout`

#### Scenario: QASM records the device header

- **WHEN** a machine with `## topology device: ibm_brisbane` is compiled to QASM
- **THEN** the output contains a `// device: ibm_brisbane` comment header

### Requirement: Routed Resource Estimation

The resource estimator SHALL add a `cx_count_routed` metric: the CX count after re-transpiling under the declared coupling map (vs the existing fully-connected `cx_count`). The cached estimate SHALL be invalidated when the topology changes.

#### Scenario: Routed CX count exceeds fully-connected

- **WHEN** a machine with two-qubit gates between non-adjacent logical qubits is estimated under a `linear_N` device
- **THEN** `cx_count_routed` exceeds `cx_count` by the SWAP-routing overhead

### Requirement: Topology Report Sub-Command

`q-orca topology-report <file>` SHALL print, for the machine, the routed CX count, depth, and SWAP overhead under each of: the declared topology, all-to-all (best case), and `linear_N` (worst case). `q-orca run --topology=<device>` SHALL override the section's device for sweep studies.

#### Scenario: Report compares topologies

- **WHEN** `q-orca topology-report` is run on a QAOA MaxCut machine
- **THEN** the output reports CX counts under all-to-all, the declared device, and `linear_N`, with the SWAP overhead per topology
