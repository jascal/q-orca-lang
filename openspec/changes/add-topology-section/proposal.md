## Why

Every shipped example assumes all-to-all qubit connectivity. On real hardware
(heavy-hex IBM Eagle/Heron, nearest-neighbour Google, T-junction Quantinuum)
most two-qubit gates aren't physical — the transpiler inserts SWAPs that can
double or triple the CX count, silently invalidating the `cx_count <= N`
invariants machines declare. The `## resources` metrics are computed on a
fully-connected graph (the most optimistic case), so a machine can pass `verify`
and then fail at hardware-execution time with a SWAP-expanded circuit. A
declarative `## topology` section turns "did my machine survive transpilation?"
into a verify-time question and makes circuits portable across coupling graphs.

## What Changes

- Add a `## topology` section (between `## context` and `## actions`) with three
  optional sub-fields — `### coupling_map` (an undirected edge table over
  physical-qubit indices; empty = all-to-all), `### device` (a named alias
  resolving to shipped JSON), and `### mapping` (logical→physical) — of which at
  least one of `coupling_map`/`device` must be present.
- Ship a device registry: `ibm_brisbane`, `ibm_torino`, `linear_N`,
  `all_to_all`, `ring_N`, `grid_NxM` under `q_orca/topology/devices/`.
- Verifier: walk every two-qubit gate, resolve logical→physical via the mapping,
  and assert edge membership — `TOPOLOGY_NON_ADJACENT_GATE` otherwise; plus
  `TOPOLOGY_UNKNOWN_DEVICE`, `TOPOLOGY_INCONSISTENT` (inline edges not a subgraph
  of the named device), `TOPOLOGY_INSUFFICIENT_QUBITS` (logical > physical).
- Compiler: pass a real `CouplingMap` + `initial_layout` into `transpile()`;
  add a `cx_count_routed` resource field re-transpiled under the declared map;
  QASM emits a `// device:` comment header.
- CLI: `q-orca run --topology=<device>` overrides the section; a new
  `q-orca topology-report <file>` prints routed CX count, depth, and SWAP
  overhead under declared / all-to-all / linear topologies.

## Capabilities

### New Capabilities
<!-- none — extends language, verifier, compiler -->

### Modified Capabilities
- `language`: add the `## topology` section (coupling_map / device / mapping).
- `verifier`: add two-qubit adjacency checking and topology consistency checks
  (4 new diagnostics).
- `compiler`: wire coupling_map + initial_layout into `transpile()`, add
  `cx_count_routed`, the QASM device comment header, and the
  `q-orca topology-report` sub-command.

## Impact

- New code: `q_orca/topology/` (device-registry loader + 6 device JSONs); AST
  `TopologyDecl`; parser `_parse_topology_block`; verifier
  `_check_two_qubit_adjacency` + 4 error codes; Qiskit transpile wiring; QASM
  header; `resources.cx_count_routed`; `q_orca/cli/topology_report.py`.
- Edited example: `qaoa-maxcut` gains an illustrative `## topology` section.
  New docs: `docs/language/topology.md`.
- Backward compatible: machines without `## topology` keep the implicit
  all-to-all assumption and are unchanged.
- **Dependencies**: `add-composed-runtime` (merged) — the adjacency check
  recurses into invoked children using the parent mapping. Composes cleanly with
  the `## hamiltonian` draft (measurement circuits pass through the same
  topology-aware transpile path).
