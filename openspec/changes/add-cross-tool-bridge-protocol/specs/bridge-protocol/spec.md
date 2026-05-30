## ADDED Requirements

### Requirement: Bridge Protocol Envelopes

The bridge protocol SHALL define three versioned JSON envelopes that both
classical-orca and q-orca can produce and consume without sharing AST types. A
`protocol_version` field SHALL be present on each so mismatches are detectable.

- A **machine descriptor** SHALL carry `name`, `params` (a list of
  `{name, type}`), `returns` (a list of `{name, type, statistics}` where
  `statistics` is a possibly-empty subset of `expectation`/`histogram`/
  `variance`), and `measurement_bearing` (bool).
- An **invocation envelope** SHALL carry `child` (the target machine name),
  `args` (a `param → JSON-value` map), `shots` (integer or null), and
  `return_bindings` (a `parent_field → child_return` map).
- A **result envelope** SHALL carry `final_state` and `returns` (a
  `name → JSON-value` map). For a shot-batched, measurement-bearing child the
  `returns` map SHALL also include the synthesized `prob_<r>` / `hist_<r>` /
  `var_<r>` fields under the same sanitized names q-orca uses in-tool.

Only JSON scalars and arrays SHALL cross the boundary; qubit / state-vector
values SHALL NOT (composition is classical at the boundary).

#### Scenario: Descriptor captures typed returns and statistics

- **WHEN** a measurement-bearing machine declares a return `bits[0]` with
  `expectation, histogram`
- **THEN** its machine descriptor lists that return with
  `statistics = ["expectation", "histogram"]` and `measurement_bearing = true`

#### Scenario: Result envelope carries aggregates for a shot-batched child

- **WHEN** a measurement-bearing child is invoked with `shots > 1` via an
  invocation envelope
- **THEN** the result envelope's `returns` includes `prob_bits_0` (and any other
  declared aggregates) under the q-orca synthesized names

#### Scenario: Version mismatch is detectable

- **WHEN** a result envelope carries a `protocol_version` the caller does not
  support
- **THEN** the bridge raises a structured error rather than silently misreading

### Requirement: Cross-Tool Invocation Handoff

The bridge SHALL execute a foreign child — a child resolved as belonging to the
other tool — over a process boundary using JSON, reusing each tool's existing
`run` entry point rather than an in-process FFI or a long-lived server. The
caller SHALL build the invocation envelope by evaluating its parent expressions
to JSON values, dispatch it to the other tool's runner, and map the result
envelope's `returns` back through `return_bindings` into the parent context
exactly as for a native child. A child SHALL be treated as foreign only when it
does not resolve in the caller's own file/import graph and is declared as living
in the other tool.

#### Scenario: Foreign child resolved and executed across the boundary

- **WHEN** a parent invokes a child that resolves to a machine owned by the
  other tool
- **THEN** the bridge serializes the invocation envelope, runs the other tool's
  runner, and binds the returned values into the parent context

#### Scenario: Same-tool children are unaffected

- **WHEN** a parent invokes a child resolvable in its own file or import graph
- **THEN** resolution and execution use the native in-tool path with no bridge
  involvement

#### Scenario: Statistics honoured only for measurement-bearing foreign children

- **WHEN** an invocation envelope sets `shots > 1` for a foreign child whose
  descriptor has `measurement_bearing = false`
- **THEN** the bridge reports an error, mirroring the in-tool
  `SHOTS_ON_CLASSICAL_CHILD` rule

### Requirement: q-orca Reference Bridge

q-orca SHALL provide a reference implementation of its side of the protocol.
`run_composed` SHALL gain a foreign-child dispatch path that builds the
invocation envelope, hands it to the bridge, and maps the result envelope back
through `return_bindings`, leaving the native same-tool path unchanged. q-orca's
`run --json` SHALL emit a result envelope compatible with this contract, serving
as the inbound entry point when a foreign (orca) parent invokes a q-orca child.

#### Scenario: run_composed dispatches a foreign child

- **WHEN** `run_composed` reaches an invoke whose child is foreign
- **THEN** it dispatches via the bridge and threads the result envelope's
  returns into the parent context, identically to a native child's returns

#### Scenario: run --json is a valid inbound entry point

- **WHEN** an external caller runs `q-orca run --json` on a q-orca child with an
  invocation envelope's args supplied
- **THEN** stdout is a result envelope another tool can consume
