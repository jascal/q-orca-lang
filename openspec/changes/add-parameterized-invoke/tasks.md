## 1. AST

- [x] 1.1 Add `QInvoke` dataclass in `q_orca/ast.py` with fields
  `child_name: str`, `arg_bindings: dict[str, str]`,
  `return_bindings: dict[str, str]`, `shots: Optional[int]`.
- [x] 1.2 Add `QReturnDef` dataclass with fields `name: str`,
  `type: QType`, `statistics: list[str]`.
- [x] 1.3 Add `invoke: Optional[QInvoke] = None` to `QStateDef`.
- [x] 1.4 Add `returns: list[QReturnDef] = []` to `QMachineDef`.

## 2. Parser

- [x] 2.1 Extend state-heading parser in
  `q_orca/parser/markdown_parser.py` to recognize
  `[invoke: Child(args) shots=N]`. Parse arg bindings
  (comma-separated kwargs) and the optional `shots=` modifier.
  Reused the assertion-era bracket-group machinery; `invoke:` is a new
  token kind alongside `initial`/`final`/`assert:`. `_INVOKE_RE` matches
  `Child(args) [shots=N]`; args split with `_split_top_level_commas`.
- [x] 2.2 Extend state-body parsing to detect a `returns:` line
  and attach its bindings to the invoke `QInvoke`.
  `_parse_return_bindings` scans the blockquote for `returns: …` and
  fills `QInvoke.return_bindings` (only when the state has an invoke).
- [x] 2.3 Add `_parse_returns_table` that handles the
  `## returns` section with Name/Type/Statistics columns, parses
  `Statistics` as a comma-separated vocabulary filter
  (`expectation`, `histogram`, `variance`).
  Unknown statistic values emit `invalid_return_statistic` and are dropped.
- [x] 2.4 Parse-time validation: `shots >= 1`; no `[initial]`-or-
  `[final]`+invoke combos; at most one invoke per state; statistics
  vocabulary only on measurement-bearing machines (requires
  post-parse check — do it right after machine assembly in
  `parse_q_orca_markdown`).
  Errors: `invoke_shots_invalid`, `invoke_with_initial_or_final`,
  `invoke_duplicate`, `statistics_on_non_measurement_machine`.
- [x] 2.5 Unit tests in `tests/test_parser.py` covering: keyword
  arg binding, indexed RHS (`seed=theta[0]`), shots parsing,
  returns-section with and without statistics, malformed cases
  (shots=0, initial+invoke, non-measurement machine with
  statistics).
  `TestInvokeAnnotation` (7) + `TestReturnsSection` (4).

## 3. Verifier — composition stage

- [x] 3.1 Create `q_orca/verifier/composition.py` with
  `check_composition(file: QOrcaFile, machine: QMachineDef) ->
  QVerificationResult`. Takes the whole file so it can resolve
  sibling machines.
- [x] 3.2 Implement child resolution: `UNRESOLVED_CHILD_MACHINE`.
- [x] 3.3 Implement arg typing: `INVOKE_ARG_UNDECLARED`,
  `INVOKE_ARG_TYPE_MISMATCH`. Type unification follows existing
  `QType` rules; indexed RHS (`theta[0]`) unifies against
  element type of the parent's `list<float>`.
  Unification compares canonical `_type_key` strings; indexed RHS resolves
  to the parent list's `element_type`.
- [x] 3.4 Implement return typing: `INVOKE_RETURN_UNDECLARED`,
  `INVOKE_RETURN_TYPE_MISMATCH`. Under `shots>1`, synthesize
  aggregate field names/types (`prob_bits_0: float`,
  `hist_bits_0: dict[int, int]`, `var_bits_0: float`) and
  unify against them instead of the raw return type.
  `_synthesized_aggregates` builds the name→type-key map; `shots>1` switches
  the available-returns set from raw returns to aggregates.
- [x] 3.5 Implement shots-flag rules: `SHOTS_ON_CLASSICAL_CHILD`.
  Determine "classical" as "no transition action has a
  measurement or mid-circuit-measure effect" — reuse the helper
  added in `harden-completeness-detection`.
  Used a local `_machine_has_measurement` (any action with measurement /
  mid_circuit_measure) rather than the event-based completeness helper.
- [x] 3.6 Implement recursive verification: run the child's full
  pipeline (same `verify()` entry point) and wrap returned
  errors with the `child_path` breadcrumb in the `location`
  dict.
  `verify(child, opts, file=file, _visited=…)`; each child error re-wrapped
  with `{invoke_state, child_machine, child_path:[err.location]}`.
- [x] 3.7 Implement cycle detection: DFS over the
  invoke-reference graph, emit `INVOKE_CYCLE` on back-edges.
  Cycle detection runs before recursive verification to prevent
  infinite recursion.
  `_machines_in_cycle` (reachability: node that can reach itself). On a cycle
  the machine emits `INVOKE_CYCLE` and skips recursion; `_visited` is a
  secondary recursion guard.
- [x] 3.8 Wire the stage into `q_orca/verifier/__init__.py::verify()`
  between classical-context and quantum-static. Add
  `VerifyOptions.skip_composition` flag.
  `verify()` gained `file` and `_visited` params; composition runs only when a
  `file` is supplied and the machine has invoke states. NOTE: required fixing a
  latent bug — standalone `---` was *skipped* by the structural parser, so
  `_split_by_separator` never split multi-machine files. Now emitted as a
  level-0 separator (no existing file used a standalone `---`).
- [x] 3.9 Unit tests in `tests/test_verifier.py` covering each
  error code and the happy paths for both classical and quantum
  children, including nested invocation (A → B → C).
  `TestComposition` (15 tests).

## 4. Compiler — Mermaid + refusal

- [ ] 4.1 In `q_orca/compiler/mermaid.py`, detect invoke states
  and render them as rounded rectangles with the child machine
  name. Emit a nested `state <ChildName> { ... }` block by
  recursively rendering the resolved child.
- [ ] 4.2 In `q_orca/compiler/qasm.py` and
  `q_orca/compiler/qiskit.py`, detect invoke states in the input
  machine and return a structured `COMPILE_COMPOSED_MACHINE`
  error (shape defined in the compiler spec). Do not produce a
  partial output.
- [ ] 4.3 Unit tests in `tests/test_compiler.py` for all three
  backends: Mermaid renders composed machine, QASM/Qiskit refuse
  with the structured error, and a single-machine file (no
  invokes) still compiles identically to before.

## 5. Spec + docs sync

- [ ] 5.1 Run `openspec validate add-parameterized-invoke --strict`
  and address any issues.
- [ ] 5.2 Add a one-line back-reference in
  `docs/research/spec-quantum-predictive-coder.md` flagging that
  the full composed QPC requires this change plus
  `add-classical-context-updates` plus the
  `add-composed-runtime` follow-up.

## 6. End-to-end verification

- [ ] 6.1 Write a fixture multi-machine file combining a
  classical-orchestrator parent and a quantum-forward-pass
  child. Confirm parse + verify + Mermaid render all pass, and
  QASM/Qiskit refuse cleanly.
- [ ] 6.2 Run `.venv/bin/python -m pytest tests/ -q
  --ignore=tests/test_cuquantum_backend.py
  --ignore=tests/test_cudaq_backend.py` and confirm green.
- [ ] 6.3 Run `.venv/bin/q-orca verify` on all examples in
  `examples/` to confirm no regressions.

## 7. Parked follow-ups (NOT this change)

- [ ] 7.1 **Parked**: `add-composed-runtime` — the Python
  dispatcher that actually walks a composed machine, calls
  child machines, handles shot batching, and wires
  synthesized aggregates into parent context. Unblocks
  compiling and executing composed machines.
- [ ] 7.2 **Parked**: `add-machine-imports` — cross-file import
  of child machines from external `.q.orca.md` files. Current
  change resolves children only within the same file.
- [ ] 7.3 **Parked**: extended statistics vocabulary
  (`joint_histogram`, `covariance`, `purity`, etc.). Current
  change ships `expectation`, `histogram`, `variance` only.
- [ ] 7.4 **Parked**: classical-orca adoption of this protocol
  on its side of the repo boundary.
