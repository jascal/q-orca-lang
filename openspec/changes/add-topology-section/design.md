## Context

`compute-needs.md` and the shipped `## resources` machinery compute post-
transpile metrics at `optimization_level=1` on a *fully-connected* coupling
graph — the most optimistic case. A user who declares `cx_count <= 3` and runs
against a heavy-hex backend can pass `verify` and fail at execution with a
SWAP-expanded 12-CX circuit. There is no way today to target a named device, to
compare two ansätze on one coupling map, or to report depth blow-up per
topology. Research draft: `docs/research/spec-topology-section.md`.

## Goals / Non-Goals

**Goals**
- A declarative `## topology` section the verifier and compiler agree on.
- Verify-time `TOPOLOGY_NON_ADJACENT_GATE` instead of a runtime transpilation
  surprise; a routed CX count (`cx_count_routed`) in the resource report.
- A named-device registry so a file can target `ibm_brisbane` without a Python
  backend stub.

**Non-Goals (v1)**
- Directed coupling graphs — undirected in v1; `### coupling_directions` is a
  follow-on. Open Question 1.
- Pulse-level routing (`## pulse_topology`) — gate-level only. Open Question 5.
- A live remote device registry — shipped JSON snapshots pinned to a date; a
  `q-orca topology refresh` fetch is a follow-on. Open Question 4.

## Decisions

### D1 — Section grammar and sub-fields
`## topology` lives between `## context` and `## actions`, with three optional
sub-fields: `### coupling_map` (two-column undirected edge table over 0-based
physical indices; empty = all-to-all), `### device` (a named alias), and
`### mapping` (logical→physical). At least one of `coupling_map`/`device` MUST be
present. AST: `TopologyDecl(edges, device, mapping)` on `QMachineDef`.

### D2 — Device registry
Named devices resolve to JSON under `q_orca/topology/devices/<name>.json`.
v1 ships `ibm_brisbane`, `ibm_torino` (heavy-hex), `linear_N`, `all_to_all`,
`ring_N`, `grid_NxM` (the parameterised ones generated on demand). Unknown names
raise `TOPOLOGY_UNKNOWN_DEVICE`. If both `device` and inline `coupling_map` are
given, the inline edges MUST form a subgraph of the device map, else
`TOPOLOGY_INCONSISTENT`.

### D3 — Mapping and the adjacency check
Absent `### mapping` ⇒ identity mapping, with a `TOPOLOGY_IDENTITY_MAPPING_NARROW`
warning when `len(physical) > len(logical)`; `len(logical) > len(physical)` is a
`TOPOLOGY_INSUFFICIENT_QUBITS` error. The verifier walks every two-qubit gate
(pattern-matching the existing `_walk_two_qubit_gates`), resolves logical→
physical, and asserts edge membership; a non-edge gate raises
`TOPOLOGY_NON_ADJACENT_GATE` with the gate location and a SWAP/re-map suggestion.
The check recurses into `invoke:` children with the parent's mapping (via the
`add-composed-runtime` resolution helper).

### D4 — Compiler integration
The Qiskit backend passes `coupling_map=` + `initial_layout=` into `transpile()`.
`resources.estimate_resources` gains a `cx_count_routed` field re-transpiled
under the declared map (cache invalidated on topology change). QASM emits a
`// device: <name>` comment header (QASM 3 has no standard device annotation).

### D5 — CLI surface
`q-orca run --topology=<device>` overrides the section (sweep studies).
`q-orca topology-report <file>` prints routed CX count, depth, and SWAP overhead
under declared / all-to-all (best) / `linear_N` (worst).

### D6 — Error ordering with resource bounds
When both a non-adjacent gate and a routed-CX bound violation occur, topology
errors are reported first, since fixing topology may remove the resource
violation.

## Risks / Trade-offs
- **Transpiler-version drift** — `topology-report` CX counts are pinned within
  ±2 in tests to detect drift.
- **Directionality** — heavy-hex CX is directional; v1 models undirected and
  relies on the transpiler to fix direction at routing time.

## Migration Plan
Additive. Absent section ⇒ implicit all-to-all (today's behaviour), unchanged.
Rollback = revert.

## Open Questions
1. Directed vs undirected coupling graphs (v1 undirected).
2. Trapped-ion all-to-all-via-shuttling modelling (`all_to_all` + a documented
   shuttling-cost convention).
3. Multiple topologies per file for parameterised testing — better solved in
   `spec-test-cases-section`.
4. Device-registry update cadence (pinned snapshots + opt-in `refresh`).
5. `## pulse_topology` as a parallel section if/when pulses ship.
