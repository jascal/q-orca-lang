## ADDED Requirements

### Requirement: Resource Estimation Backend

The compiler SHALL expose a resource-estimation entry point
`estimate_resources(machine) -> dict[str, int | str]` in
`q_orca/compiler/resources.py`. The function SHALL build the Qiskit
`QuantumCircuit` for the machine (reusing the existing Qiskit
compilation path) and compute five metrics:

- `gate_count` — total gate effects from the un-transpiled circuit
  (an honest count of what the user wrote).
- `depth` — circuit depth after `transpile(qc,
  optimization_level=1)`.
- `cx_count` — `transpile(qc, basis_gates=['u3','cx'],
  optimization_level=1).count_ops().get('cx', 0)`.
- `t_count` — `transpile(qc, basis_gates=['h','s','cx','t','tdg'],
  optimization_level=1).count_ops()`, summing the `t` and `tdg`
  entries.
- `logical_qubits` — length of the declared `qubits` list in
  `## context`.

The returned dict SHALL contain exactly the metric names listed in
`machine.resource_metrics` when that list is non-empty, and SHALL
contain all five metrics when the list is empty. Values SHALL be
non-negative integers, or the literal string `"unknown"` when the
metric depends on a runtime-bound construct that cannot be
statically evaluated.

The compiler SHALL memoize results per `id(machine)` so repeated
calls within one verify-or-compile invocation are free.

#### Scenario: Bell-pair resource counts

- **WHEN** `estimate_resources(bell_pair_machine)` is called
- **THEN** the returned dict satisfies `gate_count == 2`,
  `depth == 2`, `cx_count == 1`, `t_count == 0`,
  `logical_qubits == 2`

#### Scenario: GHZ resource counts

- **WHEN** `estimate_resources(ghz_machine)` is called
- **THEN** the returned dict satisfies `gate_count == 3`,
  `depth == 3`, `cx_count == 2`, `t_count == 0`,
  `logical_qubits == 3`

#### Scenario: Default metric set when section is absent

- **WHEN** `estimate_resources(machine)` is called on a machine with
  no `## resources` section
- **THEN** the returned dict contains all five metric keys
  (`gate_count`, `depth`, `cx_count`, `t_count`, `logical_qubits`)

#### Scenario: Subset metric set when section is present

- **WHEN** a machine declares `## resources` listing only
  `gate_count` and `logical_qubits`
- **THEN** `estimate_resources(machine)` returns a dict with
  exactly those two keys

#### Scenario: Memoization on repeated calls

- **WHEN** `estimate_resources(machine)` is called twice with the
  same machine within one verify-or-compile invocation
- **THEN** the second call returns the identical dict and does not
  re-invoke `qiskit.transpile`

### Requirement: Compile-with-Resources Entry Point

The compiler SHALL expose `compile_with_resources(machine, options)
-> tuple[str, dict[str, int | str]]` returning both the Qiskit
script and the resource dict in one call. The script SHALL be
identical to the output of `compile_to_qiskit(machine, options)`;
the resource dict SHALL be identical to
`estimate_resources(machine)`.

`q_orca/__init__.py` SHALL re-export both
`compile_with_resources` and `estimate_resources`.

#### Scenario: Compile-with-resources returns both artifacts

- **WHEN** `compile_with_resources(bell_pair_machine, default_options)`
  is called
- **THEN** the result is a 2-tuple where the first element is a
  Qiskit script string identical to `compile_to_qiskit(...)` and
  the second element is the resource dict from
  `estimate_resources(...)`

#### Scenario: Top-level re-export

- **WHEN** a user runs `from q_orca import estimate_resources,
  compile_with_resources`
- **THEN** both names resolve to the implementations in
  `q_orca/compiler/resources.py` and `q_orca/compiler/qiskit.py`
  respectively

### Requirement: Resource Report Rendering

The compiler SHALL render a one-screen resource report when
`compile_with_resources` is invoked or when the CLI is run with a
machine that has a `## resources` section or any resource
invariant. The report SHALL list one row per metric with: metric
name, measured value, and (when an invariant exists for the metric)
the comparison operator, the bound, and a pass/fail marker.

#### Scenario: Resource report contains all declared metrics

- **WHEN** the resource report is rendered for a machine with
  `gate_count <= 40` and `cx_count <= 12` invariants
- **THEN** the report contains rows for `gate_count` and `cx_count`
  that include the bound and a pass marker (when satisfied) or a
  fail marker (when violated)

#### Scenario: Resource report omits bound for metrics without invariants

- **WHEN** the resource report is rendered for a machine that
  declares `## resources` listing `t_count` but has no `t_count`
  invariant
- **THEN** the `t_count` row contains the measured value and no
  bound or pass/fail marker
