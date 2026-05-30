## 1. Protocol definition

- [x] 1.1 Document the three envelopes (machine descriptor, invocation, result)
  with field schemas and a `BRIDGE_PROTOCOL_VERSION` constant in
  `q_orca/bridge/protocol.py`.
- [x] 1.2 Define the type-mapping table between q-orca and orca type grammars;
  unmappable types raise a structured bridge error.
- [x] 1.3 Define the result-envelope error contract: an `error` field for
  child errors vs a distinct `bridge`-category error for transport failures
  (unlaunchable runner, timeout, non-JSON, unsupported `protocol_version`);
  neither binds partial returns. Derive `measurement_bearing` from the child's
  measurement effects (not from `shots`).

## 2. Descriptor + envelopes (q-orca side)

- [x] 2.1 Emit a machine descriptor from a `QMachineDef` (`## context` →
  params, `## returns` → returns + statistics, measurement-bearing flag).
- [x] 2.2 Build an invocation envelope from a `QInvoke` + parent context
  (evaluate arg expressions to JSON values).
- [x] 2.3 Parse a result envelope and map `returns` through `return_bindings`
  (raw for `shots<=1`, synthesized aggregates for `shots>1`).

## 3. Handoff + reference bridge

- [x] 3.1 Foreign-child detection: a child not resolvable in the file/import
  graph that is declared as the other tool's (extension/`tool:` marker).
- [x] 3.2 `q_orca/bridge/` dispatch: serialize the invocation envelope, run the
  other tool's runner over a process boundary, read the result envelope.
- [x] 3.3 `run_composed` foreign-child branch wiring (native path unchanged).
- [x] 3.4 Confirm `q-orca run --json` emits a conformant result envelope
  (inbound entry point); add fields if missing.

## 4. Conformance + example

- [x] 4.1 Conformance test: fixed example envelopes (descriptor / invocation /
  result) round-trip through the q-orca serializer/deserializer; pin the same
  fixtures the orca-side adoption doc references.
- [x] 4.2 Worked hybrid example: an orca trainer parent → q-orca forward-pass
  child, executed across the bridge end-to-end (gated on the orca-side adoption
  landing; until then, a q-orca-side mock of the foreign runner).

## 5. Docs + cross-repo

- [x] 5.1 Protocol reference doc in q-orca (`docs/`).
- [x] 5.2 Land the matched adoption design doc in `orca-lang/docs/` (separate
  repo) and cross-link the two.

## 6. Spec sync

- [ ] 6.1 At archive time, sync the `bridge-protocol` delta into
  `openspec/specs/bridge-protocol/spec.md`.
