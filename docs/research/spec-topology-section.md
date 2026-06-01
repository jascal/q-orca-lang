# Spec: Declarative `## topology` Section

**Status:** Draft
**Date:** 2026-05-29
**Priority:** Medium

> Generated: 2026-05-29 — weekly feature spec session

---

## Summary

Add a declarative `## topology` section to `.q.orca.md` machines that
specifies a target hardware coupling map (an undirected graph of physical
qubits with edges indicating directly-connectable pairs) and a logical-to-
physical qubit mapping. The verifier consumes this section to check that
every two-qubit gate in the machine's effects respects the declared
adjacency — or, if it does not, reports the SWAP overhead that would be
required. The Qiskit compiler consumes it to pass a real `CouplingMap`
into `transpile()` and to record the routed circuit's depth in the
resource report. This makes q-orca circuits portable across the
heterogeneous coupling graphs of real hardware (heavy-hex, linear,
T-shaped, all-to-all) and turns "did my machine survive transpilation?"
into a verify-time question rather than a runtime surprise.

## Motivation

Every shipped example in q-orca today assumes an all-to-all coupling
graph. The QAOA / VQE / GHZ / teleportation examples freely apply
two-qubit gates between any two declared qubits. On real superconducting
hardware (heavy-hex on IBM Eagle / Heron, fixed nearest-neighbour on
Google Willow, T-junction on Quantinuum), most of these gates are not
physical — the transpiler inserts SWAP gates to route them, sometimes
doubling or tripling the CX count, which silently invalidates the
`cx_count <= N` invariants that machines declare today.

The `compute-needs.md` document and the `## resources` machinery (already
shipped) acknowledge this: the post-transpile metrics are computed
against `optimization_level=1` on a *fully-connected* coupling graph,
which is the most optimistic case. A user who declares
`cx_count <= 3` and runs against a heavy-hex backend can have their
machine pass `verify` and fail at hardware-execution time with a SWAP-
expanded circuit of 12 CXs.

Beyond the false-confidence problem, there is no way today to:

- Declare "this circuit targets IBM Brisbane" without inlining a Python
  backend stub.
- Compare two ansätze on the same coupling map (a Hardware-Efficient
  Ansatz study in the `add-rung2-hea-encoding` direction would want
  this).
- Run a single machine across multiple topologies and report depth
  blowup per topology (a routing study).

This spec closes those gaps by lifting the topology assumption to a
declarative section the verifier and compiler agree on.

## Proposed Syntax / API

The `## topology` section lives between `## context` and `## actions`. It
has three sub-fields: a coupling map, an optional named-device alias, and
an optional logical-to-physical mapping.

```markdown
## topology

### coupling_map
| q0 | q1 |
|----|----|
|  0 |  1 |
|  1 |  2 |
|  2 |  3 |

### device
ibm_brisbane

### mapping
| logical | physical |
|---------|----------|
| q0      | 14       |
| q1      | 15       |
| q2      | 18       |
| q3      | 19       |
```

All three sub-fields are optional but at least one of `coupling_map` or
`device` must be present.

### `### coupling_map`

A two-column edge table over physical-qubit indices (0-based ints).
Edges are undirected (the verifier symmetrises). An empty table declares
all-to-all (today's implicit default), which is useful for spelling out
the assumption explicitly.

### `### device`

A named alias resolving to a coupling map shipped as JSON under
`q_orca/topology/devices/<name>.json`. The verifier rejects unknown
device names with `TOPOLOGY_UNKNOWN_DEVICE`. Initial devices to ship
in v1: `ibm_brisbane`, `ibm_torino` (heavy-hex 156-qubit and
heavy-hex 133-qubit Heron), `linear_N` (parameterised), `all_to_all`,
`ring_N`, `grid_NxM`. The named-alias path is the recommended one;
inline `### coupling_map` is reserved for novel or research topologies.

If both `### device` and `### coupling_map` are given, the inline edges
must form a subgraph of the device map; otherwise the verifier raises
`TOPOLOGY_INCONSISTENT`.

### `### mapping`

A two-column table mapping the logical qubits declared in
`## context` to physical qubit indices in the topology. If absent, the
verifier assumes the identity mapping and warns when
`len(physical_qubits) > len(logical_qubits)`. Explicit mapping is
required when the logical count exceeds physical, in which case the
verifier raises `TOPOLOGY_INSUFFICIENT_QUBITS`.

### Compiler integration

The Qiskit compiler reads the section and passes:

```python
transpile(
    qc,
    coupling_map=coupling_map,
    initial_layout=mapping,
    basis_gates=[...],
    optimization_level=1,
)
```

The QASM compiler emits a comment header recording the target device and
mapping (QASM 3 does not yet have a standard `device` annotation).

### CLI integration

A new flag `q-orca run --topology=<device>` overrides the section's
device choice — useful for sweep studies.

A new sub-command `q-orca topology-report <file>` prints the routed
CX count, depth, and SWAP overhead under each of: declared topology,
all-to-all (best case), `linear_N` (worst case).

## Implementation Sketch

| File / module                                | Change                                                                | LoC |
|----------------------------------------------|-----------------------------------------------------------------------|-----|
| `q_orca/ast.py`                               | New `TopologyDecl` AST node (edges, device, mapping).                  | +50 |
| `q_orca/parser/markdown_parser.py`           | New `_parse_topology_block`; integrate into section dispatch.          | +130 |
| `q_orca/topology/__init__.py` (new)          | Device-registry loader, edge-list canonicalisation, subgraph check.    | +120 |
| `q_orca/topology/devices/*.json` (new)       | Ship 6 devices (ibm_brisbane, ibm_torino, linear_N, all_to_all, ring_N, grid_NxM). | +200 |
| `q_orca/verifier/composition.py`             | New `_check_two_qubit_adjacency` pass walking every two-qubit gate.    | +110 |
| `q_orca/verifier/types.py`                   | Four new error codes: `TOPOLOGY_UNKNOWN_DEVICE`, `TOPOLOGY_INCONSISTENT`, `TOPOLOGY_INSUFFICIENT_QUBITS`, `TOPOLOGY_NON_ADJACENT_GATE`. | +15 |
| `q_orca/compiler/qiskit.py`                  | Wire coupling_map + initial_layout into `transpile()` call.            | +60 |
| `q_orca/compiler/qasm.py`                    | Comment-header emission.                                                | +20 |
| `q_orca/compiler/resources.py`               | Add a `cx_count_routed` field that re-transpiles under the declared coupling map. Cache invalidated when topology changes. | +80 |
| `q_orca/cli/topology_report.py` (new)        | Sub-command implementation.                                             | +130 |
| `docs/language/topology.md` (new)            | User-facing docs.                                                       | +180 |
| `examples/qaoa-maxcut.q.orca.md`             | Add a `## topology device: ibm_brisbane` section as illustrative.       | edit |
| Tests                                         | Parser, verifier, compiler, end-to-end topology-report.                | +350 |

Estimated total: ~1,100 new LoC + ~350 in tests.

The `TOPOLOGY_NON_ADJACENT_GATE` check is the only step that interacts
with the *gate-level* AST (everything else is metadata). It walks every
action effect, extracts two-qubit gates with their target qubit indices,
resolves logical→physical via the mapping, and asserts edge membership.
Pattern-match on the existing two-qubit gate walker in
`q_orca/verifier/quantum.py:_walk_two_qubit_gates`.

Symbolic-action effects (sub-machine `invoke:` returns) are handled by
the existing `composition.py` infrastructure under
`add-composed-runtime` — the topology check recurses into invoked
children with the parent's mapping.

## Test Cases

1. **Linear topology, adjacent CX** — `## topology device: linear_4`,
   `CNOT(qs[0], qs[1])`. Verifier accepts; transpile keeps original CX
   count.

2. **Linear topology, non-adjacent CX** — `## topology device: linear_4`,
   `CNOT(qs[0], qs[2])`. Verifier raises `TOPOLOGY_NON_ADJACENT_GATE`
   with the offending gate location and a suggestion to insert SWAP or
   re-map.

3. **Subgraph consistency** — `## topology` with both `device:
   ibm_brisbane` and an inline `coupling_map` containing an edge that
   isn't in the heavy-hex graph. Verifier raises
   `TOPOLOGY_INCONSISTENT`.

4. **Identity-mapping warning** — 4 logical qubits, device with 156
   physical qubits, no explicit `### mapping`. Verifier accepts with
   `TOPOLOGY_IDENTITY_MAPPING_NARROW` (warning), and the topology-report
   shows the identity mapping was used.

5. **End-to-end SWAP overhead** — Run `q-orca topology-report
   qaoa-maxcut.q.orca.md`. Output reports CX count of 6 under
   all-to-all, ~14 under `ibm_brisbane` heavy-hex, and ~20 under
   `linear_4`. Regression test pins these counts within ±2 to detect
   transpiler-version drift.

6. **Compatibility with `## invariants` resource bounds** — A machine
   declaring `cx_count <= 4` and `## topology device: linear_4` with a
   non-adjacent two-qubit gate. The verifier raises both
   `TOPOLOGY_NON_ADJACENT_GATE` and `RESOURCE_BOUND_EXCEEDED` (under the
   routed CX count, which exceeds 4 after SWAPs). The error order is
   topology first, since fixing topology may remove the resource
   violation.

## Dependencies

- **`add-composed-runtime`** (just landed): topology checks must recurse
  into invoked children. The recursion uses `run_composed`'s
  parent-context-resolution helper, so this spec sequences after.
- **`extend-composed-gate-parents`** (in flight): once a parent can emit
  its own two-qubit gates, the topology check must walk parent gates as
  well as child gates. Spec can ship before, but the check needs an
  upgrade when `extend-composed-gate-parents` archives.
- **Independent of `## hamiltonian` spec** (other draft in this session):
  the two sections compose cleanly — the Hamiltonian measurement
  circuits also pass through the topology-aware transpile path with no
  extra wiring.

## Open Questions

1. **Directed vs undirected coupling graphs** — real hardware has
   directional CX coupling (e.g. CX(0→1) is fine, CX(1→0) costs four H
   gates and a CX). Heavy-hex Brisbane is directional. Should the
   topology section model this, or rely on the Qiskit transpiler to fix
   directionality at routing time? Suggest: undirected in v1, with a
   `### coupling_directions` sub-block as a follow-on.

2. **Time-varying couplers** — Some hardware (Quantinuum trapped-ion)
   has effectively all-to-all connectivity that is technically routed
   via ion shuttling. Should there be a `## topology family:
   trapped_ion` annotation that overrides the connectivity check
   entirely? Or do we model it as `all_to_all` with a separate cost
   metric for shuttling? Suggest: `all_to_all` with a documented
   convention.

3. **Topology in `## test_cases`** — Should a single example file be
   able to declare multiple topologies for parameterised testing
   ("verify this circuit against linear_4, ring_4, and ibm_brisbane")?
   This crosses into `spec-test-cases-section` territory and is
   probably better solved there.

4. **Device-registry update cadence** — IBM and Google publish device
   graphs that change as hardware is decommissioned and brought online.
   Should the shipped JSONs be a versioned snapshot, or fetched at
   verify time from a remote registry? Suggest: shipped snapshots
   pinned to a date, with a `q-orca topology refresh` command that
   pulls the latest from each vendor's public registry (network call,
   off by default).

5. **Compatibility with `## hardware` / `## pulses`** — A future
   pulse-level extension would need its own `pulse-topology`
   (qubit-to-control-line mapping). Is `## topology` intended to be
   the umbrella section for both gate-level and pulse-level routing,
   or are those separate? Suggest: gate-level for now,
   `## pulse_topology` as a parallel section if/when pulses ship.

---

**KB grounding:**

- *Reinforcement Learning for Quantum Layout and Routing.*
  `arXiv:2405.13196`. Indexed in q-orca-kb (`q-orca-implementations`,
  `circuits`). Source for the linear-connectivity SWAP-routing baseline
  and the formalisation of the qubit-mapping problem as adjacency
  satisfaction.
- Tannu & Qureshi (2019) *A Case for Variability-Aware Policies for
  NISQ-Era Quantum Computers.* The qubit-mapping problem definition
  cited at `arXiv:2407.00736`. Indexed in q-orca-kb (`circuits`).
- Tan & Cong (2022) *Optimal Qubit Mapping with SAT.* `arXiv:2208.13679`.
  Indexed in q-orca-kb (`circuits`). Source for the mapping/routing
  constraint formalisation and the BIP-mapper benchmark used in test
  case 5.
