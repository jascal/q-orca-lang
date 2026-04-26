# Tasks: Resource Estimation

## 1. AST extensions

- [x] 1.1 Add `QMachine.resource_metrics: list[str] = field(default_factory=list)`
      to `q_orca/ast.py`. Empty list means "use the default metric
      set" downstream.
- [x] 1.2 Extend the `Invariant` dataclass with a new `kind` value
      `"resource"` and a `metric: str | None = None` field. Existing
      `entanglement` and `schmidt_rank` invariants continue to set
      `metric=None`.

## 2. Parser — `## resources` section

- [x] 2.1 Add `_parse_resources_table(table, errors) -> list[str]` in
      `q_orca/parser/markdown_parser.py`. Accept a 2- or 3-column
      table with header `Metric | Basis | Notes?`. Return the list of
      metric names from the first column.
- [x] 2.2 Validate each metric name against the recognized set
      (`gate_count`, `depth`, `cx_count`, `t_count`,
      `logical_qubits`). Unknown names SHALL append a structured
      `unknown_resource_metric` error referencing the row.
- [x] 2.3 Wire `_parse_machine_chunk` to detect `## resources` after
      the existing `## actions` and `## invariants` parsing. Section
      is optional; absence leaves `resource_metrics=[]`.

## 3. Parser — resource invariants

- [x] 3.1 Extend the `## invariants` bullet-list grammar in
      `q_orca/parser/markdown_parser.py` to recognize five new
      identifiers (`gate_count`, `depth`, `cx_count`, `t_count`,
      `logical_qubits`) on the LHS of a comparison.
- [x] 3.2 Accept the comparison operators `<=`, `<`, `==`, `>=`, `>`
      and an integer literal RHS. Produce
      `Invariant(kind="resource", metric=<name>, op=<op>,
      value=<int>)`.
- [x] 3.3 Add tests in `tests/test_parser.py::TestResourceInvariants`
      covering each metric × operator combination plus an
      unknown-identifier error case.

## 4. Compiler — `estimate_resources`

- [x] 4.1 Create `q_orca/compiler/resources.py` with
      `estimate_resources(machine) -> dict[str, int | str]`.
- [x] 4.2 Build the Qiskit circuit by reusing the existing
      circuit-construction helpers in `q_orca/compiler/qiskit.py`.
      Do not duplicate gate emission.
- [x] 4.3 Compute each metric:
      - `gate_count` — sum gate effects from the un-transpiled
        circuit.
      - `depth` — `transpile(qc, optimization_level=1).depth()`.
      - `cx_count` — `transpile(qc, basis_gates=['u3','cx'],
        optimization_level=1).count_ops().get('cx', 0)`.
      - `t_count` — `transpile(qc, basis_gates=['h','s','cx','t','tdg'],
        optimization_level=1).count_ops()`, summing `t` + `tdg`.
      - `logical_qubits` — `len(machine.context['qubits'])`.
- [x] 4.4 Memoize the result by `id(machine)` so repeated calls
      within one verify-or-compile invocation are free.
- [x] 4.5 Return `"unknown"` for any metric whose computation
      fails because of a runtime-bound `[loop N]`. Today no shipped
      feature triggers this; the branch exists for forward
      compatibility.

## 5. Compiler — `compile_with_resources`

- [x] 5.1 Add `compile_with_resources(machine, options) -> tuple[str,
      dict]` to `q_orca/compiler/qiskit.py` (or a new top-level entry
      in `q_orca/__init__.py`). Returns the Qiskit script and the
      resource dict in one call.
- [x] 5.2 Format the resource report as a one-screen summary table:
      `metric : value [≤ bound] [✓|✗]`. Bound and pass/fail are
      omitted when the machine has no invariant for that metric.
- [x] 5.3 Export `estimate_resources` and `compile_with_resources`
      from `q_orca/__init__.py`.

## 6. Verifier — `check_resource_invariants`

- [x] 6.1 Add `check_resource_invariants(machine) -> list[VerifyError]`
      to `q_orca/verifier/dynamic.py`. For each
      `Invariant(kind="resource")`, evaluate the metric via
      `estimate_resources(machine)` and apply the comparison.
- [x] 6.2 On violation, emit a `VerifyError` with code
      `RESOURCE_BOUND_EXCEEDED`, message naming the metric, the
      measured value, the operator, and the bound.
- [x] 6.3 On indeterminate measurement (`"unknown"` returned), emit
      a `VerifyError` with severity `warning` and code
      `RESOURCE_BOUND_INDETERMINATE`.
- [x] 6.4 Activate the rule under the name `resource_bounds` in
      `## verification rules`. Default state: enabled when any
      resource invariant is present, else skipped (zero cost).
- [x] 6.5 Wire the rule into the verifier's main dispatch alongside
      `check_unitarity`, `check_completeness`, etc.

## 7. Tests

- [x] 7.1 `tests/test_resource_estimation.py` (new file):
      - `test_bell_pair_resources`: `bell-entangler.q.orca.md`
        produces `gate_count=2, depth=2, cx_count=1, t_count=0,
        logical_qubits=2`.
      - `test_ghz_resources`: `ghz-state.q.orca.md` produces
        `gate_count=3, depth=3, cx_count=2, t_count=0,
        logical_qubits=3`.
      - `test_qaoa_maxcut_resources`: pinned numbers for the
        bundled QAOA example.
      - `test_memoization`: two calls to
        `estimate_resources(machine)` return the identical dict
        and the second call doesn't re-invoke `transpile`
        (assert via patching).
      - `test_unknown_metric_in_resources_section`: parser error.
      - `test_no_resources_section_uses_default_metrics`:
        `compile_with_resources` on a machine without `##
        resources` returns all five metrics.
- [x] 7.2 `tests/test_verifier.py`:
      - `test_resource_bound_exceeded`: a machine with
        `cx_count <= 0` and a CNOT in its action emits
        `RESOURCE_BOUND_EXCEEDED`.
      - `test_resource_bound_satisfied`: same machine with
        `cx_count <= 5` passes.
      - `test_resource_invariants_skipped_when_absent`: a machine
        with no resource invariants does not invoke
        `estimate_resources` (assert via patching).
- [x] 7.3 `tests/test_parser.py::TestResourcesSection`:
      - 2-column form parses.
      - 3-column form with `Notes` parses identically.
      - Unknown metric name produces structured error.
      - Missing section leaves `resource_metrics=[]`.

## 8. Examples

- [x] 8.1 Update `examples/qaoa-maxcut.q.orca.md` to include a
      `## resources` section listing all five metrics, plus a
      `## invariants` block with pinned bounds. Run the example
      through the verifier; the bounds SHALL pass at the values the
      example currently produces.
- [x] 8.2 Update `examples/vqe-heisenberg.q.orca.md` similarly.
- [x] 8.3 Update `examples/bell-entangler.q.orca.md` to demonstrate
      a minimal resource section: `gate_count <= 2; cx_count == 1`.
      Smallest possible illustration.

## 9. Documentation

- [x] 9.1 New file `docs/language/resources.md` covering:
      - Surface syntax of `## resources` (with example).
      - Metric definitions (un-optimized vs post-transpile).
      - Resource invariants in `## invariants`.
      - Diagnostic codes (`RESOURCE_BOUND_EXCEEDED`,
        `RESOURCE_BOUND_INDETERMINATE`,
        `unknown_resource_metric`).
      - The default-metric-set fallback rule.
- [x] 9.2 Update README's verifier rule list with `resource_bounds`.
- [x] 9.3 CHANGELOG entry under the next release noting the
      additive `## resources` section, the five new invariant
      identifiers, and the two new compiler entry points.

## 10. Spec consistency

- [x] 10.1 `openspec validate add-resource-estimation --strict` is
      green.
- [x] 10.2 Full pytest suite green.
- [x] 10.3 Ruff clean across the touched files.
- [x] 10.4 Run `openspec archive add-resource-estimation` after
      merge so the deltas land in
      `openspec/specs/{language,compiler,verifier}/spec.md`.
