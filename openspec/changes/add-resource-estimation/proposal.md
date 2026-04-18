## Why

Q-Orca is currently mute on the static cost of a compiled circuit.
Authors writing VQE, QAOA, or Grover machines have no way to ask
"how many CX gates does this compile to?" or "is this circuit Clifford
+T?" without dropping out of the language and re-running the output
through Qiskit's transpiler by hand. That gap shows up three places:

1. **NISQ hardware fit checks happen at run time, not at verify time.**
   A user targeting `ibm_hanoi` (≤ 100 CX) only learns their circuit
   exceeds the budget after running it. The static verifier already
   catches structural problems (unitarity, no-cloning, completeness);
   resource budgets are the same kind of check applied to a different
   axis.

2. **Fault-tolerant readiness is invisible.** T-count is the dominant
   cost driver in Clifford+T fault tolerance (Fowler et al.,
   `1208.0928`), and the same `.q.orca.md` file should be evaluable
   for both near-term (CX-count) and long-term (T-count) feasibility.

3. **Optimization passes have no canonical metric.** A future
   ZX-calculus or RL-driven optimization pass needs a before/after
   number to chase. Resource estimation is that number.

The accounting is small — Qiskit's `transpile()` already computes
depth, CX-count, and T-count given a basis-gate set. What's missing is
a Q-Orca surface for declaring which metrics matter for a given
machine and a verifier rule that turns budget violations into errors
instead of silent regressions.

## What Changes

**New `## resources` section (declarative):**

- The parser SHALL accept an optional `## resources` table whose `Metric`
  column lists which resource quantities the machine wants reported.
  Recognized metric names: `gate_count`, `depth`, `cx_count`, `t_count`,
  `logical_qubits`. Unknown metric names SHALL produce a structured
  parser error.
- If the section is omitted, the compiler SHALL fall back to the
  default set (all five metrics).
- The section is purely declarative — it tells the compiler which
  numbers to compute and report. It does not assert bounds; for that
  see the invariants extension below.

**Resource invariants:**

- The existing `## invariants` bullet-list grammar SHALL recognize
  five new identifiers: `gate_count`, `depth`, `cx_count`, `t_count`,
  `logical_qubits`. They compose with the existing `<=`, `<`, `==`,
  `>=`, `>` operators and an integer literal RHS.
- A new `Invariant.kind="resource"` AST node SHALL hold the metric
  name, comparison operator, and bound.

**Resource estimator (compiler):**

- New module `q_orca/compiler/resources.py` exposing
  `estimate_resources(machine) -> dict[str, int]`. The function
  builds the Qiskit `QuantumCircuit` (reusing the existing Qiskit
  compiler's circuit construction) and computes:
  - `gate_count` — total gate count from the un-decomposed circuit.
  - `depth` — `transpile(qc, optimization_level=1).depth()`.
  - `cx_count` — `transpile(qc, basis_gates=['u3','cx'],
    optimization_level=1).count_ops().get('cx', 0)`.
  - `t_count` — `transpile(qc, basis_gates=['h','s','cx','t','tdg'],
    optimization_level=1).count_ops()`, summing `t` + `tdg`.
  - `logical_qubits` — declared qubit count from `## context`.
- `compile_with_resources(machine, options)` SHALL return both the
  Qiskit script and the resource dict in one call.
- The CLI / programmatic entry point SHALL render a resource report
  alongside compilation when the machine declares `## resources` or
  resource invariants.

**Resource invariant verification:**

- New rule `check_resource_invariants` in `q_orca/verifier/dynamic.py`.
  For each `Invariant(kind="resource")`, evaluate the metric via
  `estimate_resources()` (memoized per-machine), apply the comparison,
  emit a `RESOURCE_BOUND_EXCEEDED` error with the measured value and
  the bound on violation.
- The rule is gated by presence of any resource invariant in
  `## invariants` so it has zero cost for machines that don't use it.
- Activated under a new opt-in/opt-out name `resource_bounds` in
  `## verification rules`.

**Documentation & examples:**

- `examples/qaoa-maxcut.q.orca.md` and `examples/vqe-heisenberg.q.orca.md`
  SHALL grow a `## resources` section and a small set of resource
  invariants pinning their current numbers, demonstrating regression
  use.
- New doc `docs/language/resources.md` documenting the full grammar
  and semantics.

This change does **not**:

- Add support for `physical_qubits` or any FTQC-specific overhead
  estimation (deferred until a `## error_correction` section exists).
- Add support for parameterized resource estimates (worst-case over a
  parameter sweep). Metrics are computed against the default angle
  values declared in `## context`.
- Multiply resource estimates through `[loop N]` annotations beyond
  the static expansion the loop feature already provides. When a loop
  bound is unknown at compile time, the affected metric SHALL be
  reported as `unknown` and resource invariants involving it SHALL
  emit a structured `RESOURCE_BOUND_INDETERMINATE` warning rather
  than an error.
- Change any existing AST shape for `Invariant`. The new
  `kind="resource"` is additive; existing `entanglement` and
  `schmidt_rank` invariants continue to parse and verify identically.

## Capabilities

### New Capabilities

None. All three halves extend existing capabilities.

### Modified Capabilities

- `language`: the `## resources` section is new surface syntax; the
  `## invariants` grammar gains five identifiers.
- `compiler`: a new `estimate_resources()` accounting backend and a
  `compile_with_resources()` entry point.
- `verifier`: a new `check_resource_invariants` rule and the
  `RESOURCE_BOUND_EXCEEDED` / `RESOURCE_BOUND_INDETERMINATE`
  diagnostics.

## Impact

- `q_orca/parser/markdown_parser.py` — `## resources` section parser
  (~50 LOC); `## invariants` grammar gains five identifier branches
  (~30 LOC).
- `q_orca/ast.py` — `QMachine.resource_metrics: list[str]` field;
  `Invariant.kind` literal gains `"resource"` plus a `metric: str`
  field.
- `q_orca/compiler/resources.py` — new file, ~150 LOC, leans on
  `qiskit.transpile`.
- `q_orca/compiler/qiskit.py` — new `compile_with_resources()` entry
  point, ~30 LOC.
- `q_orca/verifier/dynamic.py` — new `check_resource_invariants` rule,
  ~40 LOC.
- `q_orca/__init__.py` — export `compile_with_resources` and
  `estimate_resources`.
- `tests/test_resource_estimation.py` — new file, ~250 LOC of unit
  + integration tests.
- `tests/test_parser.py` — parse cases for `## resources` and the
  new invariant identifiers.
- `tests/test_verifier.py` — `RESOURCE_BOUND_EXCEEDED` violation case
  and a satisfied case.
- `examples/qaoa-maxcut.q.orca.md` and
  `examples/vqe-heisenberg.q.orca.md` — add `## resources` section and
  pinned bounds.
- `docs/language/resources.md` — new doc.
- No new runtime dependency. Qiskit is already required for the
  Stage-4 simulation path and supplies `transpile()`.

## Non-Goals

- Real-device noise modeling, queue-time estimation, fidelity
  estimation. These are downstream features that consume the same
  resource dict.
- Worst-case parameter-sweep estimation. Single-point estimates only,
  using `## context` defaults.
- Symbolic resource expressions in invariants (`gate_count <=
  4 * p + 2`). Integer-literal RHS only.
- Replacing `qiskit.transpile` with a Q-Orca-internal pass. The
  Qiskit transpiler is the canonical accounting backend; the
  cuQuantum / CUDA-Q execution backends consume the same dict
  downstream without re-implementing the count.
