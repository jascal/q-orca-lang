# Resource estimation

Q-Orca compiles each `.q.orca.md` machine to a Qiskit `QuantumCircuit`,
then asks the Qiskit transpiler for five static cost numbers. You can
declare which numbers a machine cares about with a `## resources`
table, and you can pin static budgets via the existing `## invariants`
grammar. The verifier turns budget violations into errors at verify
time, before any hardware run.

## The five metrics

| Metric            | Definition |
|-------------------|------------|
| `gate_count`      | Total ops on the **un-transpiled** circuit (the literal gate sequence the machine declares). |
| `depth`           | Critical-path depth after `transpile(qc, optimization_level=1)`. |
| `cx_count`        | Number of `cx` ops after `transpile(qc, basis_gates=['u3', 'cx'], optimization_level=1)` — NISQ-relevant. |
| `t_count`         | `t + tdg` count after `transpile(qc, basis_gates=['h', 's', 'cx', 't', 'tdg'], optimization_level=1)` — Clifford+T fault-tolerance proxy. |
| `logical_qubits`  | Declared qubit count from `## context` (`qubits: list<qubit>` or fallback rules in the compiler spec). |

`gate_count` is intentionally pre-transpile: it tells you what the
machine *says*. The other four are post-transpile against canonical
basis sets so they compare cleanly across machines.

## `## resources` section

Optional. Declares which metrics the compiler should report alongside
the script.

```markdown
## resources
| Metric         | Basis      |
|----------------|------------|
| gate_count     | logical    |
| depth          | logical    |
| cx_count       | u3+cx      |
```

The `Basis` column is documentation only. A third `Notes` column is
also accepted. Unknown metric names produce a structured
`unknown_resource_metric` error during parsing.

If the section is omitted, `compile_with_resources` reports all five
metrics by default.

## Resource invariants

The `## invariants` block already accepts entanglement and Schmidt-rank
claims. It additionally accepts the five resource identifiers as the
LHS of a comparison against an integer literal:

```markdown
## invariants
- gate_count <= 9
- depth <= 5
- cx_count <= 6
- t_count == 0
- logical_qubits == 3
```

Operators: `<=`, `<`, `==`, `>=`, `>`. RHS must be an integer literal.

## Verification rule `resource_bounds`

The verifier runs `check_resource_invariants` automatically when at
least one resource invariant is present in `## invariants`. To opt out
explicitly, omit the invariants or set
`VerifyOptions(skip_resource_bounds=True)`.

Diagnostics:

- `RESOURCE_BOUND_EXCEEDED` (error) — measured value violates the
  declared bound. Message names the metric, the measured value, the
  operator, and the bound.
- `RESOURCE_BOUND_INDETERMINATE` (warning) — the metric came back
  `"unknown"` because of a runtime-bound construct (currently no
  shipped feature triggers this; the branch exists for forward
  compatibility with parameterized loop counts).
- `unknown_resource_metric` (parser error) — `## resources` row names
  a metric outside the recognized five.

## Programmatic API

```python
from q_orca import (
    parse_q_orca_markdown,
    estimate_resources,
    compile_with_resources,
    format_resource_report,
)

machine = parse_q_orca_markdown(open("my.q.orca.md").read()).file.machines[0]

# Just the numbers
resources = estimate_resources(machine)
# → {'gate_count': 2, 'depth': 2, 'cx_count': 1, 't_count': 0, 'logical_qubits': 2}

# Full one-shot: Qiskit script + numbers
script, resources = compile_with_resources(machine)

# One-screen summary table
print(format_resource_report(machine, resources))
#   gate_count : 2  <= 2  ✓
#   cx_count   : 1  == 1  ✓
```

`estimate_resources` is memoized by `id(machine)`, so the verifier
and compiler share one transpile pass per call site.

## Default-metric-set fallback

If a machine has no `## resources` section, `compile_with_resources`
and `format_resource_report` use the canonical default order:
`gate_count, depth, cx_count, t_count, logical_qubits`. A machine with
a `## resources` section uses that section's order verbatim.
