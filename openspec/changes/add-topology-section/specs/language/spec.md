## ADDED Requirements

### Requirement: Declarative Topology Section

The parser SHALL recognize a `## topology` section, placed between `## context` and `## actions`, with three optional sub-fields: `### coupling_map`, `### device`, and `### mapping`. At least one of `### coupling_map` or `### device` MUST be present. The parser SHALL attach a `TopologyDecl(edges, device, mapping)` to `QMachineDef`.

`### coupling_map` is a two-column edge table over 0-based physical-qubit indices; edges are undirected (the parser/verifier symmetrises), and an empty table declares all-to-all connectivity explicitly. `### device` is a named alias (e.g. `ibm_brisbane`) resolving to a shipped coupling map. `### mapping` is a two-column `logical → physical` table over the qubits declared in `## context`.

A machine with no `## topology` section parses exactly as before this change and retains the implicit all-to-all assumption.

#### Scenario: Coupling-map edge table parses

- **WHEN** a machine declares `### coupling_map` with rows `0 1`, `1 2`, `2 3`
- **THEN** `TopologyDecl.edges` contains the undirected edges {(0,1),(1,2),(2,3)}

#### Scenario: Device alias parses

- **WHEN** a machine declares `### device` with body `ibm_brisbane`
- **THEN** `TopologyDecl.device` is `ibm_brisbane`

#### Scenario: Logical-to-physical mapping parses

- **WHEN** a machine declares `### mapping` rows `q0 → 14`, `q1 → 15`
- **THEN** `TopologyDecl.mapping` maps logical `q0→14`, `q1→15`
