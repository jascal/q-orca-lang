## 1. AST

- [ ] 1.1 Add `QInvoke` dataclass in `q_orca/ast.py` with fields
  `child_name: str`, `arg_bindings: dict[str, str]`,
  `return_bindings: dict[str, str]`, `shots: Optional[int]`.
- [ ] 1.2 Add `QReturnDef` dataclass with fields `name: str`,
  `type: QType`, `statistics: list[str]`.
- [ ] 1.3 Add `invoke: Optional[QInvoke] = None` to `QStateDef`.
- [ ] 1.4 Add `returns: list[QReturnDef] = []` to `QMachineDef`.

## 2. Parser

- [ ] 2.1 Extend state-heading parser in
  `q_orca/parser/markdown_parser.py` to recognize
  `[invoke: Child(args) shots=N]`. Parse arg bindings
  (comma-separated kwargs) and the optional `shots=` modifier.
- [ ] 2.2 Extend state-body parsing to detect a `returns:` line
  and attach its bindings to the invoke `QInvoke`.
- [ ] 2.3 Add `_parse_returns_table` that handles the
  `## returns` section with Name/Type/Statistics columns, parses
  `Statistics` as a comma-separated vocabulary filter
  (`expectation`, `histogram`, `variance`).
- [ ] 2.4 Parse-time validation: `shots >= 1`; no `[initial]`-or-
  `[final]`+invoke combos; at most one invoke per state; statistics
  vocabulary only on measurement-bearing machines (requires
  post-parse check — do it right after machine assembly in
  `parse_q_orca_markdown`).
- [ ] 2.5 Unit tests in `tests/test_parser.py` covering: keyword
  arg binding, indexed RHS (`seed=theta[0]`), shots parsing,
  returns-section with and without statistics, malformed cases
  (shots=0, initial+invoke, non-measurement machine with
  statistics).

## 3. Verifier — composition stage

- [ ] 3.1 Create `q_orca/verifier/composition.py` with
  `check_composition(file: QOrcaFile, machine: QMachineDef) ->
  QVerificationResult`. Takes the whole file so it can resolve
  sibling machines.
- [ ] 3.2 Implement child resolution: `UNRESOLVED_CHILD_MACHINE`.
- [ ] 3.3 Implement arg typing: `INVOKE_ARG_UNDECLARED`,
  `INVOKE_ARG_TYPE_MISMATCH`. Type unification follows existing
  `QType` rules; indexed RHS (`theta[0]`) unifies against
  element type of the parent's `list<float>`.
- [ ] 3.4 Implement return typing: `INVOKE_RETURN_UNDECLARED`,
  `INVOKE_RETURN_TYPE_MISMATCH`. Under `shots>1`, synthesize
  aggregate field names/types (`prob_bits_0: float`,
  `hist_bits_0: dict[int, int]`, `var_bits_0: float`) and
  unify against them instead of the raw return type.
- [ ] 3.5 Implement shots-flag rules: `SHOTS_ON_CLASSICAL_CHILD`.
  Determine "classical" as "no transition action has a
  measurement or mid-circuit-measure effect" — reuse the helper
  added in `harden-completeness-detection`.
- [ ] 3.6 Implement recursive verification: run the child's full
  pipeline (same `verify()` entry point) and wrap returned
  errors with the `child_path` breadcrumb in the `location`
  dict.
- [ ] 3.7 Implement cycle detection: DFS over the
  invoke-reference graph, emit `INVOKE_CYCLE` on back-edges.
  Cycle detection runs before recursive verification to prevent
  infinite recursion.
- [ ] 3.8 Wire the stage into `q_orca/verifier/__init__.py::verify()`
  between classical-context and quantum-static. Add
  `VerifyOptions.skip_composition` flag.
- [ ] 3.9 Unit tests in `tests/test_verifier.py` covering each
  error code and the happy paths for both classical and quantum
  children, including nested invocation (A → B → C).

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
