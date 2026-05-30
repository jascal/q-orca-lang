## Why

q-orca can now compose machines *within its own tool* — `invoke:`, typed
`## returns`, shot-batched aggregates, cross-file imports, and `run_composed`
all ship. But the original motivation for composition is **hybrid**: a classical
orca orchestrator (epoch loop, convergence check, parameter schedule) driving a
q-orca quantum forward pass. Classical orca (the sibling TypeScript tool) has its
own `- invoke: Child` with `input:` mapping and implicit `{finalState, context}`
returns — a *different* surface and a weaker return contract than q-orca's typed
`## returns` + statistics. There is no agreed contract for one tool to invoke a
machine defined in the other. This change specifies that contract: a
tool-agnostic **bridge protocol** both orca and q-orca implement against, plus a
concrete reference bridge (JSON envelope over each tool's `run` CLI) so a parent
in one tool can execute a child in the other.

## What Changes

- **Define a tool-agnostic composition contract** (the bridge protocol), not a
  shared AST — per the standing "1b: bridge layer, not shared AST" decision.
  It covers: a **machine descriptor** (name, typed parameters, typed returns,
  per-return statistics, whether the machine is measurement-bearing); an
  **invocation envelope** (child name, argument bindings as `param → value`,
  `shots`, return bindings); and a **result envelope** (typed return values, and
  for shot-batched quantum children the synthesized `prob_`/`hist_`/`var_`
  aggregates under the same names q-orca already uses).
- **Specify the bridge handoff**: when a parent runtime in tool A reaches an
  invoke whose child resolves to a machine owned by tool B, it serializes the
  invocation envelope to JSON and dispatches to tool B's runner (q-orca already
  exposes `q-orca run --json`), then maps the result envelope back into the
  parent context. No in-process FFI; the boundary is process + JSON.
- **Reference bridge on the q-orca side**: `run_composed` learns to dispatch a
  *foreign* child (a machine flagged as orca-owned) through the bridge, and
  q-orca's `run --json` is documented as the inbound entry point so an orca
  parent can invoke a q-orca child symmetrically.
- **Companion (other repo)**: a matched adoption design doc lands in `orca-lang`
  (`docs/`) proposing orca add typed `## returns` + a `shots:`/statistics
  notion and implement this protocol on its side. This proposal defines the
  contract orca implements against.

## Capabilities

### New Capabilities

- `bridge-protocol`: the tool-agnostic contract (machine descriptor, invocation
  envelope, result envelope, handoff semantics) for composing classical-orca and
  q-orca machines across the tool boundary, plus q-orca's reference bridge.

### Modified Capabilities

None. `runtime`, `language`, `verifier`, and `compiler` are unchanged by the
*contract*; the reference-bridge implementation is additive and tracked in tasks.

## Impact

- **Code (reference bridge, additive)**: a small `q_orca/bridge/` module that
  serializes/deserializes the envelopes; `run_composed` gains a foreign-child
  dispatch path that shells out to the other tool's runner. `q-orca run --json`
  already emits a compatible result envelope.
- **Docs**: protocol reference in q-orca; matched adoption design doc in
  `orca-lang/docs/`. A worked hybrid example (orca trainer → q-orca forward pass).
- **Dependencies**: none new — the bridge is process + JSON.
- **Sequenced after** `add-parameterized-invoke`, `add-machine-imports`, and
  `add-composed-runtime` (all merged). **Cross-repo**: pairs with the orca-lang
  adoption doc. **Out of scope (v1)**: in-process FFI, streaming/partial results,
  and a shared serialized AST.
