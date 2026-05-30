# Cross-Tool Bridge Protocol

How a classical-**orca** orchestrator and a **q-orca** quantum child compose
across the tool boundary — the hybrid trainer → forward-pass workflow. The
contract is tool-agnostic (no shared AST); the transport is **process + JSON**.
Spec: `openspec/changes/add-cross-tool-bridge-protocol/specs/bridge-protocol/spec.md`.
Implementation: `q_orca/bridge/`.

## Envelopes (`q_orca.bridge.protocol`)

All carry `protocol_version` (`BRIDGE_PROTOCOL_VERSION`); a version the receiver
doesn't support is a hard `BridgeError`.

- **Machine descriptor** — `descriptor_for(machine)` →
  `{name, params: [{name, type}], returns: [{name, type, statistics}],
  measurement_bearing}`. `measurement_bearing` is a property of the *child*
  (derived from its measurement effects), never from `shots`.
- **Invocation envelope** — `build_invocation(child, args, shots, return_bindings)`
  → `{child, args, shots, return_bindings}`.
- **Result envelope** — `make_result(final_state, returns, error=None)` →
  `{final_state, returns, error?}`. For a shot-batched measurement-bearing child,
  `returns` includes the synthesized `prob_<r>` / `hist_<r>` / `var_<r>` under the
  same names q-orca uses in-tool.

Only JSON scalars/arrays cross the boundary — never qubits/state vectors.

## Transport

An **invocation envelope on stdin → a result envelope on stdout**, over each
tool's `run` entry point.

- **Outbound** (q-orca parent → foreign child): `run_composed(..., foreign_runners=
  {ChildName: ["<runner>", "args", ...]})`. When an invoke's child does not
  resolve in-tool but is registered in `foreign_runners`, the runtime builds the
  invocation envelope, runs the foreign runner over a process boundary
  (`q_orca.bridge.dispatch.dispatch_foreign`), and binds the result envelope's
  returns into the parent context. A transport failure (unlaunchable / timeout /
  non-JSON / bad version) raises `BridgeError`; a child error rides in the result
  envelope's `error` field.
- **Inbound** (foreign parent → q-orca child): `q-orca run <file> --bridge` reads
  an invocation envelope from stdin, runs the named child with its `args` /
  `shots`, and writes a result envelope to stdout
  (`q_orca.bridge.dispatch.run_inbound`).

Because both ends speak the same envelopes, q-orca can sit on **either** side — so
the bridge is exercised end-to-end with q-orca on both ends (see
`tests/test_bridge_protocol.py`) even before the orca-side adoption lands.

## Worked example (q-orca both ends)

```python
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.runtime.composed import run_composed
from q_orca.runtime.types import QIterativeSimulationOptions

pf = parse_q_orca_markdown(open("trainer.q.orca.md").read()).file   # invokes QForward (foreign)
runner = ["q-orca", "run", "forward.q.orca.md", "--bridge"]         # the foreign child's runner
result = run_composed(pf, pf.machines[0],
                      QIterativeSimulationOptions(seed_simulator=42),
                      foreign_runners={"QForward": runner})
print(result.final_context["prob"])   # the child's prob_bits_0 aggregate, bound back
```

The orca-side endpoint (a classical orca trainer dispatching a q-orca child) is
proposed in `orca-lang/docs/cross-tool-invoke-and-returns.md`; landing it makes
the runner an actual `orca` ↔ `q-orca` pair rather than q-orca on both ends.
