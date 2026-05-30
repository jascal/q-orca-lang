## Context

Two sibling tools share the Orca markdown-machine philosophy but are separate
implementations: classical **orca** (TypeScript; `- invoke: Child input: {…}`,
`on_done`/`on_error`, implicit `{finalState, context}` returns) and **q-orca**
(Python; `[invoke: Child(args) shots=N]`, typed `## returns` with statistics,
`run_composed`). The standing scope decision from `add-classical-context-updates`
is **1b — bridge layer, not shared AST**: the two ASTs stay separate and a
translator bridges them at the boundary. This change writes that contract down
and gives q-orca a reference implementation of its side.

## Goals / Non-Goals

**Goals:**

- A tool-agnostic, versioned contract that both tools can implement without
  sharing code or AST types.
- A concrete, low-friction transport: process boundary + JSON, reusing each
  tool's existing `run` CLI rather than inventing an RPC layer.
- Preserve q-orca's typed-returns + statistics semantics across the boundary
  (the synthesized `prob_/hist_/var_` names are part of the contract).
- Symmetry: an orca parent can invoke a q-orca child and vice versa.

**Non-Goals:**

- In-process FFI or a shared serialized AST.
- Streaming / yield-on-measure / partial results.
- Forcing one surface syntax on both tools — each keeps its own `invoke`
  notation and maps to the neutral envelope.

## Decisions

### Decision 1: Three envelopes, JSON, versioned

The contract is three JSON shapes with a `protocol_version`:

- **Machine descriptor** — `{name, params: [{name, type}], returns: [{name,
  type, statistics: [...]}], measurement_bearing: bool}`. Each tool can emit
  this for any machine (q-orca derives it from `## context` + `## returns`;
  orca derives it from its context + the proposed `## returns`).
- **Invocation envelope** — `{child, args: {param: value}, shots: int|null,
  return_bindings: {parent_field: child_return}}`. The caller fills `args` by
  evaluating its parent expressions; `value`s are JSON scalars/arrays.
- **Result envelope** — `{final_state, returns: {name: value}}` where, for a
  shot-batched measurement-bearing child, `returns` also carries the synthesized
  `prob_<r>`/`hist_<r>`/`var_<r>` fields. q-orca's `run --json` already emits a
  compatible shape.

**Alternative considered:** a shared protobuf/typed schema package imported by
both. Rejected — couples the build systems and violates decision 1b; JSON with a
version field is enough.

### Decision 2: Transport is process + the existing `run` CLI

A parent runtime, on a *foreign* invoke, writes the invocation envelope and
shells out to the other tool's runner (`q-orca run --json`; the orca equivalent),
reading the result envelope from stdout. No long-lived server, no FFI. This is
debug/simulation tooling; process-per-invoke is acceptable, and it keeps the two
toolchains fully decoupled.

**Alternative considered:** a persistent bridge daemon. Deferred — only worth it
if process-spawn overhead dominates a real workload; the contract does not
preclude adding one later behind the same envelopes.

### Decision 3: Foreign children are marked, resolved by the bridge

A child is "foreign" when it is not resolvable in the caller's own file/import
graph but is declared as living in the other tool (e.g. an import row pointing at
a `.orca.md` rather than `.q.orca.md`, or an explicit `tool:` marker). The
verifier's resolution order is unchanged for same-tool children; foreign children
are resolved by the bridge, which emits the descriptor and validates the
arg/return envelope against it. Statistics on returns are honoured only when the
foreign child is measurement-bearing — same rule as in-tool.

### Decision 4: q-orca reference bridge is additive

`q_orca/bridge/` serializes/deserializes envelopes; `run_composed` gains a
foreign-child branch that builds the invocation envelope, dispatches via the
bridge, and maps the result envelope back through `return_bindings` exactly as a
native child's returns. q-orca's existing `run --json` is the inbound entry
point. Nothing in the native (same-tool) path changes.

## Risks / Trade-offs

- **[Risk] Type-system skew between tools.** orca and q-orca have overlapping but
  not identical type grammars. → Mitigation: the descriptor's `type` strings are
  matched structurally with a small documented mapping table; unmappable types
  are a bridge error, surfaced before execution.
- **[Risk] Process-per-invoke latency for shot-batched loops.** → Mitigation:
  acceptable for v1 (simulation/debug); a daemon transport can slot behind the
  same envelopes later.
- **[Trade-off] JSON scalars only across the boundary.** Qubit/state-vector
  values cannot cross — only classical params and typed/aggregated returns. This
  is intentional and matches the in-tool boundary (composition is classical at
  the boundary).

## Open Questions

1. **Where the `tool:` / foreign marker lives.** An import-row convention
   (`.orca.md` vs `.q.orca.md` extension) vs an explicit `tool: orca` field on
   the import. Leaning extension-based, with an explicit override available.
2. **Who owns protocol versioning.** A shared `BRIDGE_PROTOCOL_VERSION` constant
   duplicated in both repos vs a tiny shared spec file. v1: duplicate the
   constant + a conformance test in each repo against the same example envelopes.
