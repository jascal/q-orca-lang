# Tasks: Runtime State-Category Assertions

## 1. AST extensions

- [ ] 1.1 Add `QubitSlice(start: int, end: int | None = None)` to
      `q_orca/ast.py`. `end=None` means single-qubit; `end>=start`
      means inclusive range. Reuse for both invariants and
      assertions.
- [ ] 1.2 Add `QAssertion` dataclass to `q_orca/ast.py` with fields
      `category: Literal['classical','superposition','entangled','separable']`,
      `targets: list[QubitSlice]`, and `source_span: Span`.
- [ ] 1.3 Extend `QStateDef` with
      `assertions: list[QAssertion] = field(default_factory=list)`.
- [ ] 1.4 Add `AssertionPolicy` dataclass to `q_orca/ast.py` with
      fields `shots_per_assert: int = 512`, `confidence: float = 0.99`,
      `on_failure: Literal['error','warn'] = 'error'`,
      `backend: str = 'auto'`.
- [ ] 1.5 Extend `QMachine` with
      `assertion_policy: AssertionPolicy = field(default_factory=AssertionPolicy)`.

## 2. Parser — state-heading `[assert: …]` annotation

- [ ] 2.1 Extend `parse_state_header` in
      `q_orca/parser/markdown_parser.py` to recognize an additional
      bracketed-annotation kind `assert:` alongside the existing
      `initial` and `final`. Multiple bracketed groups on the same
      heading SHALL be conjunctive and order-independent.
- [ ] 2.2 Add helper `_parse_assertion_payload(payload: str) ->
      list[QAssertion]` that splits on `;` and dispatches to a
      per-category sub-parser keyed off the leading identifier.
- [ ] 2.3 Implement four sub-parsers covering
      `classical(qs[…])`, `superposition(qs[…])`,
      `entangled(qs[i], qs[j])`, `separable(qs[i], qs[j])`. Reuse
      `_parse_qubit_slice` (extracted from existing invariants
      parser) for `qs[k]` and `qs[a..b]`.
- [ ] 2.4 Unrecognized category names SHALL produce a structured
      `unknown_assertion_category` parse error referencing the
      heading and naming the offending category.
- [ ] 2.5 Wire parsed assertions into `QStateDef.assertions` in
      declaration order.

## 3. Parser — `## assertion policy` section

- [ ] 3.1 Add `_parse_assertion_policy_table(table, errors) ->
      AssertionPolicy` in `q_orca/parser/markdown_parser.py`. Accept a
      2- or 3-column table whose header is `Setting | Value | Notes?`.
      The notes column SHALL be parsed and discarded.
- [ ] 3.2 Validate each setting name against the recognized set
      (`shots_per_assert`, `confidence`, `on_failure`, `backend`).
      Unknown names SHALL append a structured
      `unknown_assertion_policy_setting` error referencing the row.
- [ ] 3.3 Validate each value against its declared type. Out-of-range
      values (`confidence` outside `[0, 1]`, `shots_per_assert <= 0`,
      `on_failure` not in `{'error', 'warn'}`) SHALL append a
      structured `assertion_policy_value_error` referencing the row,
      the setting, and the offending value.
- [ ] 3.4 Wire `_parse_machine_chunk` to detect `## assertion policy`
      after the existing `## actions` and `## invariants` parsing.
      Section is optional; absence leaves the default
      `AssertionPolicy()`.

## 4. Parser — `state_assertions` verification rule

- [ ] 4.1 Add `state_assertions` to the recognized verification-rule
      kinds in `q_orca/parser/markdown_parser.py`'s
      `## verification rules` parser. Other kinds remain custom rules.
- [ ] 4.2 Add a unit test in `tests/test_parser.py` confirming that
      `- state_assertions: …` produces a
      `VerificationRule(kind="state_assertions")` AST node.

## 5. Verifier — partial-trace primitive

- [ ] 5.1 Create `q_orca/verifier/_partial_trace.py` with
      `reduced_density_matrix(state_vector: np.ndarray, n_qubits: int,
      keep: list[int]) -> np.ndarray` using NumPy reshape/einsum.
      Backend-agnostic; takes a complex state vector and returns a
      density matrix on the kept subsystem.
- [ ] 5.2 Add a unit test that confirms the Bell pair reduces to a
      maximally mixed marginal `I/2` on each individual qubit and to
      a pure entangled `ρ` on the joint pair (`Tr(ρ²)≈1`).
- [ ] 5.3 Add a unit test that confirms a product state reduces to a
      pure single-qubit marginal (`Tr(ρ²)≈1` for each qubit
      individually).

## 6. Verifier — assertion-checker module

- [ ] 6.1 Create `q_orca/verifier/assertions.py` exposing
      `check_state_assertions(machine: QMachine, backend) ->
      list[Diagnostic]`.
- [ ] 6.2 Implement `_circuit_prefix_for_state(machine, state_name) ->
      list[QuantumGate]` that walks the transition graph from
      `[initial]` to the target state along its actions. For machines
      with branching, choose the *first* path in declaration order
      and return it; document this in a docstring.
- [ ] 6.3 Implement four predicate evaluators:
      `_eval_classical(state_vec, slice, shots, confidence)`,
      `_eval_superposition(state_vec, slice, shots, confidence)`,
      `_eval_entangled(state_vec, qi, qj)`, and
      `_eval_separable(state_vec, qi, qj)`. The classical /
      superposition pair MUST use Z-basis sampling with binomial /
      Wilson-score bounds. The entangled / separable pair MUST use
      `reduced_density_matrix` from §5.
- [ ] 6.4 Wire the dispatcher in `check_state_assertions` to:
      (a) skip states flagged unreachable by the structural stage;
      (b) emit a single `ASSERTION_BACKEND_MISSING` and bail when the
      requested backend is unavailable;
      (c) for each remaining assertion, evaluate the predicate and
      append exactly one of `ASSERTION_PASSED`, `ASSERTION_FAILED`,
      `ASSERTION_INCONCLUSIVE` to the diagnostics list.
- [ ] 6.5 Honour `assertion_policy.on_failure`: `error` → severity
      error; `warn` → severity warning. `INCONCLUSIVE` and
      `BACKEND_MISSING` are always warnings.
- [ ] 6.6 Add `ASSERTIONS_SKIPPED_NO_SIMULATOR` info diagnostic when
      the backend dispatcher reports a real-device target.

## 7. Verifier — wire stage into pipeline

- [ ] 7.1 Add `skip_state_assertions: bool = False` to
      `VerifyOptions` in `q_orca/verifier/__init__.py`.
- [ ] 7.2 Insert the state-assertions stage at the end of the pipeline
      (after `superposition_leak`). Skip when:
      (a) `VerifyOptions.skip_state_assertions` is set;
      (b) no `state_assertions` verification rule is declared;
      (c) no state carries any assertions.
- [ ] 7.3 Merge stage diagnostics into the main
      `QVerificationResult` exactly like the other stages.

## 8. Compiler — Qiskit metadata

- [ ] 8.1 Extend the per-state metadata block emitted by
      `q_orca/compiler/qiskit.py` to include
      `assertion_probe: list[QAssertion]` for any state with a
      non-empty `assertions` list.
- [ ] 8.2 Confirm via test that the Bell-pair Qiskit script's gate
      sequence is byte-identical between the asserted and
      unasserted versions of the same machine.

## 9. Compiler — QASM comments

- [ ] 9.1 Update `q_orca/compiler/qasm.py` to emit a comment line
      `// assert: <category>(<qubit-slice>...) @ state <state-name>`
      immediately before the gate sequence for the next outgoing
      transition out of an annotated state. Source order of
      assertions within a single state SHALL be preserved.
- [ ] 9.2 Confirm via test that the emitted QASM contains no
      assertion-derived instructions — only comment lines.

## 10. Compiler — Mermaid pass-through

- [ ] 10.1 Update `q_orca/compiler/mermaid.py` to optionally append a
      brief `assert:` summary to the description of a state node
      that has assertions. No new state nodes, transitions, or
      labels SHALL be introduced.
- [ ] 10.2 Confirm via test that the Mermaid node count and
      transition count match the unasserted version of the machine.

## 11. Tests — parser

- [ ] 11.1 Add `tests/test_parser.py::TestAssertionAnnotations` with
      coverage for: single-category assertion, multi-category
      semicolon-separated assertion, slice form, range form,
      conjunctive `[final, assert: …]`, unknown category error.
- [ ] 11.2 Add `tests/test_parser.py::TestAssertionPolicy` with
      coverage for: default policy, single-setting override, all-four
      override, unknown setting error, out-of-range value error,
      notes column accepted-and-ignored.

## 12. Tests — verifier (one per category + edge cases)

- [ ] 12.1 Create `tests/test_state_assertions.py`. Add a passing test
      per category (`classical`, `superposition`, `entangled`,
      `separable`) using minimal hand-built machines.
- [ ] 12.2 Add a failing-assertion test confirming
      `ASSERTION_FAILED` at error severity by default and at warning
      severity when `on_failure='warn'`.
- [ ] 12.3 Add an inconclusive test using `shots_per_assert=16` that
      confirms `ASSERTION_INCONCLUSIVE` at warning severity.
- [ ] 12.4 Add a backend-missing test (mock QuTiP unavailable) that
      confirms exactly one `ASSERTION_BACKEND_MISSING` warning and no
      per-assertion diagnostics.
- [ ] 12.5 Add a real-device-target test confirming a single
      `ASSERTIONS_SKIPPED_NO_SIMULATOR` info diagnostic.
- [ ] 12.6 Add a mid-circuit-measurement test asserting on a state
      that lives downstream of a `measure` action.
- [ ] 12.7 Add an unreachable-state test confirming the assertion
      checker emits no diagnostic for assertions on a state already
      flagged unreachable.

## 13. Examples & docs

- [ ] 13.1 Create `examples/bell-entangler-asserts.q.orca.md` — Bell
      pair with `[assert: superposition(qs[0])]` on the
      Hadamard state and `[assert: entangled(qs[0], qs[1])]` on the
      post-CNOT state. Set `shots_per_assert=256` for fast CI.
- [ ] 13.2 Update `examples/bit-flip-syndrome.q.orca.md` with
      `[assert: entangled(qs[0], qs[1])]` etc. at the encoded state
      and `[assert: classical(qs[3..4])]` at the measured state.
- [ ] 13.3 Create `docs/language/assertions.md` covering the
      vocabulary, statistical semantics, the destructive-measurement
      caveat, and the GHZ-marginal subtlety from design.md
      Decision 4.
- [ ] 13.4 Update `docs/specs/spec-runtime-assertions.md`'s status
      header to mark this proposal as in flight and link to
      `openspec/changes/add-runtime-state-assertions/`.

## 14. Spec sync

- [ ] 14.1 At archive time, sync the three delta specs into
      `openspec/specs/{language,verifier,compiler}/spec.md` per the
      OpenSpec workflow.
