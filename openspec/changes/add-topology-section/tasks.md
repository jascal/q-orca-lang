## 1. AST + parser

- [ ] 1.1 In `q_orca/ast.py`, add `TopologyDecl(edges, device, mapping)`; add `topology: Optional[TopologyDecl]` to `QMachineDef`
- [ ] 1.2 Parser `_parse_topology_block`: parse `## topology` + `### coupling_map` (undirected edge table, empty = all-to-all), `### device` (alias line), `### mapping` (logical→physical); integrate into section dispatch
- [ ] 1.3 Backward-compat: a machine with no `## topology` section parses unchanged (implicit all-to-all)

## 2. Device registry

- [ ] 2.1 New `q_orca/topology/__init__.py`: device-registry loader, edge-list canonicalisation/symmetrisation, subgraph check
- [ ] 2.2 Ship `q_orca/topology/devices/*.json`: `ibm_brisbane`, `ibm_torino`, `all_to_all`; generate `linear_N` / `ring_N` / `grid_NxM` on demand

## 3. Verifier

- [ ] 3.1 Topology consistency: `TOPOLOGY_UNKNOWN_DEVICE`, `TOPOLOGY_INCONSISTENT`, `TOPOLOGY_INSUFFICIENT_QUBITS`, `TOPOLOGY_IDENTITY_MAPPING_NARROW` (warning)
- [ ] 3.2 `_check_two_qubit_adjacency`: walk every two-qubit gate (reuse `_walk_two_qubit_gates`), resolve logical→physical, assert edge membership; `TOPOLOGY_NON_ADJACENT_GATE` otherwise; recurse into invoke children with the parent mapping
- [ ] 3.3 Add the 4 error codes to `verifier/types.py`; report topology before routed-CX `RESOURCE_BOUND_EXCEEDED`

## 4. Compiler

- [ ] 4.1 Qiskit: wire `coupling_map` + `initial_layout` into the `transpile()` call
- [ ] 4.2 QASM: emit `// device: <name>` (+ mapping) comment header
- [ ] 4.3 `resources.estimate_resources`: add `cx_count_routed` (re-transpile under the declared map); invalidate cache on topology change
- [ ] 4.4 New `q_orca/cli/topology_report.py`: `q-orca topology-report <file>` (declared / all-to-all / linear_N); `q-orca run --topology=<device>` override

## 5. Examples + tests + docs

- [ ] 5.1 Add an illustrative `## topology device: ibm_brisbane` section to `examples/qaoa-maxcut.q.orca.md`
- [ ] 5.2 Tests: adjacent CX accepted; non-adjacent CX → `TOPOLOGY_NON_ADJACENT_GATE`; subgraph `TOPOLOGY_INCONSISTENT`; identity-mapping warning; end-to-end SWAP overhead pinned within ±2; resource-bound interaction (topology reported first); backward-compat
- [ ] 5.3 Docs: `docs/language/topology.md` (section grammar, device registry, mapping, adjacency check, `topology-report`); mark `docs/research/spec-topology-section.md` delivered
