# Tasks: Runtime State-Category Assertions

## 1. AST extensions

- [x] 1.1 Add `QubitSlice(start: int, end: int | None = None)` to
      `q_orca/ast.py`. `end=None` means single-qubit; `end>=start`
      means inclusive range. Reuse for both invariants and
      assertions.
      Added with a `__post_init__` that normalizes `end=None → end=start`
      so `QubitSlice(k)` and `QubitSlice(k, k)` compare equal (both spec
      notations appear across the language-delta scenarios). Helpers
      `is_single` and `indices()` added. Invariants still use the legacy
      `qubits: list[int]` shape (`qN` notation), so the "reuse for
      invariants" half is not wired — assertions are the only consumer.
- [x] 1.2 Add `QAssertion` dataclass to `q_orca/ast.py` with fields
      `category: Literal['classical','superposition','entangled','separable']`,
      `targets: list[QubitSlice]`, and `source_span: Span`.
      No `Span` type existed in the codebase (parse errors are plain
      strings). Added a minimal `Span(line: int, text: str)` populated
      from the Markdown element's `.line` and the original category-
      expression text, so failure diagnostics can cite what the author
      wrote. `AssertionCategory` is a module-level `Literal` alias.
- [x] 1.3 Extend `QStateDef` with
      `assertions: list[QAssertion] = field(default_factory=list)`.
- [x] 1.4 Add `AssertionPolicy` dataclass to `q_orca/ast.py` with
      fields `shots_per_assert: int = 512`, `confidence: float = 0.99`,
      `on_failure: Literal['error','warn'] = 'error'`,
      `backend: str = 'auto'`.
- [x] 1.5 Extend `QMachine` with
      `assertion_policy: AssertionPolicy = field(default_factory=AssertionPolicy)`.
      The machine dataclass is `QMachineDef` (the tasks say `QMachine`);
      field added there.

## 2. Parser — state-heading `[assert: …]` annotation

- [x] 2.1 Extend `parse_state_header` in
      `q_orca/parser/markdown_parser.py` to recognize an additional
      bracketed-annotation kind `assert:` alongside the existing
      `initial` and `final`. Multiple bracketed groups on the same
      heading SHALL be conjunctive and order-independent.
      Reworked `_parse_state_heading` to extract all top-level `[…]`
      groups via a new nesting-aware `_extract_bracket_groups` (assertion
      payloads carry `qs[…]` subscripts, so naive `[^\]]` matching
      breaks). Each group is split with the existing `_split_top_level_commas`
      (§1.7) so `[final, assert: entangled(qs[0], qs[1])]` parses as two
      conjunctive tokens. Unrecognized bracket tokens (queued `[loop …]`
      etc.) are left untouched, not errored.
- [x] 2.2 Add helper `_parse_assertion_payload(payload: str) ->
      list[QAssertion]` that splits on `;` and dispatches to a
      per-category sub-parser keyed off the leading identifier.
- [x] 2.3 Implement four sub-parsers covering
      `classical(qs[…])`, `superposition(qs[…])`,
      `entangled(qs[i], qs[j])`, `separable(qs[i], qs[j])`. Reuse
      `_parse_qubit_slice` (extracted from existing invariants
      parser) for `qs[k]` and `qs[a..b]`.
      Implemented as a single `_parse_assertion_expression` dispatching on
      `_ASSERTION_CATEGORIES` (category → arity). Wrote `_parse_qubit_slice`
      fresh rather than extracting from the invariants parser: invariants
      use `qN` notation, not `qs[k]`/`qs[a..b]`, so there was nothing to
      reuse. Added an `invalid_assertion_target` error for malformed slices
      / wrong arity (e.g. `entangled(qs[0])`).
- [x] 2.4 Unrecognized category names SHALL produce a structured
      `unknown_assertion_category` parse error referencing the
      heading and naming the offending category.
- [x] 2.5 Wire parsed assertions into `QStateDef.assertions` in
      declaration order.

## 3. Parser — `## assertion policy` section

- [x] 3.1 Add `_parse_assertion_policy_table(table, errors) ->
      AssertionPolicy` in `q_orca/parser/markdown_parser.py`. Accept a
      2- or 3-column table whose header is `Setting | Value | Notes?`.
      The notes column SHALL be parsed and discarded.
      Columns located by name via `_find_column_index`; any column past
      `Value` is ignored. Missing `Setting`/`Value` headers emit an
      `assertion_policy_value_error`.
- [x] 3.2 Validate each setting name against the recognized set
      (`shots_per_assert`, `confidence`, `on_failure`, `backend`).
      Unknown names SHALL append a structured
      `unknown_assertion_policy_setting` error referencing the row.
- [x] 3.3 Validate each value against its declared type. Out-of-range
      values (`confidence` outside `[0, 1]`, `shots_per_assert <= 0`,
      `on_failure` not in `{'error', 'warn'}`) SHALL append a
      structured `assertion_policy_value_error` referencing the row,
      the setting, and the offending value.
      Invalid values leave that setting at its default and append the
      error (parse continues). `backend` accepts any string.
- [x] 3.4 Wire `_parse_machine_chunk` to detect `## assertion policy`
      after the existing `## actions` and `## invariants` parsing.
      Section is optional; absence leaves the default
      `AssertionPolicy()`. Added `"assertion policy"` to `_KNOWN_SECTIONS`.

## 4. Parser — `state_assertions` verification rule

- [x] 4.1 Add `state_assertions` to the recognized verification-rule
      kinds in `q_orca/parser/markdown_parser.py`'s
      `## verification rules` parser. Other kinds remain custom rules.
      Added to `known_kinds` in `_parse_verification_rules`.
- [x] 4.2 Add a unit test in `tests/test_parser.py` confirming that
      `- state_assertions: …` produces a
      `VerificationRule(kind="state_assertions")` AST node.
      Covered in §11 (`TestAssertionAnnotations`) rather than a standalone
      test; will be added there when §11 lands.

## 5. Verifier — partial-trace primitive

- [x] 5.1 Create `q_orca/verifier/_partial_trace.py` with
      `reduced_density_matrix(state_vector: np.ndarray, n_qubits: int,
      keep: list[int]) -> np.ndarray` using NumPy reshape/einsum.
      Backend-agnostic; takes a complex state vector and returns a
      density matrix on the kept subsystem.
      Big-endian convention (qubit 0 = MSB), matching the QuTiP
      `basis([2]*n, …)` / `.full()` flatten order. Added a `purity(rho)`
      helper returning `Tr(ρ²)`.
- [x] 5.2 Add a unit test that confirms the Bell pair reduces to a
      maximally mixed marginal `I/2` on each individual qubit and to
      a pure entangled `ρ` on the joint pair (`Tr(ρ²)≈1`).
      Verified inline during development; formal test lands with §12.
- [x] 5.3 Add a unit test that confirms a product state reduces to a
      pure single-qubit marginal (`Tr(ρ²)≈1` for each qubit
      individually).
      Verified inline (product + GHZ marginals); formal test lands with §12.

## 6. Verifier — assertion-checker module

- [x] 6.1 Create `q_orca/verifier/assertions.py` exposing
      `check_state_assertions(machine: QMachine, backend) ->
      list[Diagnostic]`.
      `backend` is an optional name hint; `assertion_policy.backend` wins
      unless `auto`. Returns `list[QVerificationError]` (the codebase's
      diagnostic type).
- [x] 6.2 Implement `_circuit_prefix_for_state(machine, state_name) ->
      list[QuantumGate]` that walks the transition graph from
      `[initial]` to the target state along its actions. For machines
      with branching, choose the *first* path in declaration order
      and return it; document this in a docstring.
      Returns a list of op dicts (`gate` / `measure` / `cond`), not bare
      gates, so the simulator can honour mid-circuit measurement +
      feedforward. DFS with a per-path visited set takes the first
      declaration-order transition that reaches the target.
- [x] 6.3 Implement four predicate evaluators ... classical /
      superposition use Z-basis sampling with Wilson bounds; entangled /
      separable use `reduced_density_matrix` from §5.
      DEVIATION (recorded in module docstring): entangled/separable use the
      **PPT / negativity criterion** on the reduced 2-qubit matrix, not the
      design's `Tr(ρ²)<1−ε` pair-purity (which is wrong for a 2-qubit Bell
      state — pair purity is exactly 1 — and false-positives on GHZ pairs).
      classical/superposition treat `confidence` as the Wilson *level* and
      decide against a fixed definiteness threshold (0.90); sampling uses a
      fixed seed for reproducibility.
- [x] 6.4 Wire the dispatcher: (a) skip unreachable states (computed via
      BFS from initial); (b) single `ASSERTION_BACKEND_MISSING` + bail when
      the simulator is unavailable; (c) one of `ASSERTION_PASSED` /
      `ASSERTION_FAILED` / `ASSERTION_INCONCLUSIVE` per assertion.
- [x] 6.5 Honour `assertion_policy.on_failure`: `error` → severity
      error; `warn` → severity warning. `INCONCLUSIVE` and
      `BACKEND_MISSING` are always warnings.
- [x] 6.6 Add `ASSERTIONS_SKIPPED_NO_SIMULATOR` info diagnostic when
      the backend dispatcher reports a real-device target.
      Real-device detection via `_REAL_DEVICE_BACKENDS` name set (no real
      backend ships today; forward-looking contract).
      Mid-circuit measurement is handled by deterministic dominant-outcome
      collapse + feedforward (the design's "Stage 4b already replays
      measurements" is not true of the current code).

## 7. Verifier — wire stage into pipeline

- [x] 7.1 Add `skip_state_assertions: bool = False` to
      `VerifyOptions` in `q_orca/verifier/__init__.py`.
- [x] 7.2 Insert the state-assertions stage at the end of the pipeline
      (after `superposition_leak`). Skip when:
      (a) `VerifyOptions.skip_state_assertions` is set;
      (b) no `state_assertions` verification rule is declared;
      (c) no state carries any assertions.
      Gate is `not skip and _has_state_assertions_rule(machine)`; condition
      (c) is handled inside `check_state_assertions` (returns `[]` when no
      state is annotated), so a rule-declared-but-unannotated machine runs
      trivially. Import is lazy to avoid touching the QuTiP-importing
      `dynamic` module on the no-assertions path.
- [x] 7.3 Merge stage diagnostics into the main
      `QVerificationResult` exactly like the other stages.

## 8. Compiler — Qiskit metadata

- [x] 8.1 Extend the per-state metadata block emitted by
      `q_orca/compiler/qiskit.py` to include
      `assertion_probe: list[QAssertion]` for any state with a
      non-empty `assertions` list.
      The Qiskit backend emits a Python *script* (text), so the metadata is a
      `# assertion_probe @ state <name>: <category>(qs[…])` comment emitted
      before the annotated state's first outgoing transition (final/no-outgoing
      states flushed after the sequence). Shared formatting via new
      `q_orca/compiler/util.py::format_assertion_expr` + `state_label`.
- [x] 8.2 Confirm via test that the Bell-pair Qiskit script's gate
      sequence is byte-identical between the asserted and
      unasserted versions of the same machine.
      `TestQiskitAssertionMetadata` in `tests/test_state_assertions.py`.

## 9. Compiler — QASM comments

- [x] 9.1 Update `q_orca/compiler/qasm.py` to emit a comment line
      `// assert: <category>(<qubit-slice>...) @ state <state-name>`
      immediately before the gate sequence for the next outgoing
      transition out of an annotated state. Source order of
      assertions within a single state SHALL be preserved.
      Uses the OpenQASM register name `q` (e.g. `q[0..2]`) per the compiler
      spec scenario, and the ket-stripped state label (`encoded`).
- [x] 9.2 Confirm via test that the emitted QASM contains no
      assertion-derived instructions — only comment lines.
      `TestQasmAssertionComments` (comment presence + source order +
      instruction byte-identity).

## 10. Compiler — Mermaid pass-through

- [x] 10.1 Update `q_orca/compiler/mermaid.py` to optionally append a
      brief `assert:` summary to the description of a state node
      that has assertions. No new state nodes, transitions, or
      labels SHALL be introduced.
      Appended as ` — assert: <expr>; <expr>` to the existing state
      description line.
- [x] 10.2 Confirm via test that the Mermaid node count and
      transition count match the unasserted version of the machine.
      `TestMermaidAssertionPassThrough`.

## 11. Tests — parser

- [x] 11.1 Add `tests/test_parser.py::TestAssertionAnnotations` with
      coverage for: single-category assertion, multi-category
      semicolon-separated assertion, slice form, range form,
      conjunctive `[final, assert: …]`, unknown category error.
      Plus separate-bracket-groups conjunction, invalid-target error, and
      the §4.2 `state_assertions` verification-rule kind test.
- [x] 11.2 Add `tests/test_parser.py::TestAssertionPolicy` with
      coverage for: default policy, single-setting override, all-four
      override, unknown setting error, out-of-range value error,
      notes column accepted-and-ignored.

## 12. Tests — verifier (one per category + edge cases)

- [x] 12.1 Create `tests/test_state_assertions.py`. Add a passing test
      per category (`classical`, `superposition`, `entangled`,
      `separable`) using minimal hand-built machines.
      Also includes the §5.2-5.3 partial-trace tests (Bell marginals,
      product purity, GHZ pairwise mixedness).
- [x] 12.2 Add a failing-assertion test confirming
      `ASSERTION_FAILED` at error severity by default and at warning
      severity when `on_failure='warn'`.
- [x] 12.3 Add an inconclusive test using `shots_per_assert=16` that
      confirms `ASSERTION_INCONCLUSIVE` at warning severity.
      Uses `Ry(qs[0], 0.5)` (p(|0>)≈0.94) — borderline vs the 0.90
      definiteness threshold at 16 shots with the fixed seed.
- [x] 12.4 Add a backend-missing test (mock QuTiP unavailable) that
      confirms exactly one `ASSERTION_BACKEND_MISSING` warning and no
      per-assertion diagnostics.
- [x] 12.5 Add a real-device-target test confirming a single
      `ASSERTIONS_SKIPPED_NO_SIMULATOR` info diagnostic.
- [x] 12.6 Add a mid-circuit-measurement test asserting on a state
      that lives downstream of a `measure` action.
      Two cases: `classical(qs[0])` PASSES post-collapse, and
      `superposition(qs[0])` FAILS post-collapse.
- [x] 12.7 Add an unreachable-state test confirming the assertion
      checker emits no diagnostic for assertions on a state already
      flagged unreachable.

## 13. Examples & docs

- [x] 13.1 Create `examples/bell-entangler-asserts.q.orca.md` — Bell
      pair with `[assert: superposition(qs[0])]` on the
      Hadamard state and `[assert: entangled(qs[0], qs[1])]` on the
      post-CNOT state. Set `shots_per_assert=256` for fast CI.
      Verifies VALID (both assertions PASS) under `q-orca verify` and
      `--strict`; added to `tests/test_examples.py::EXAMPLE_FILES`.
- [x] 13.2 Update `examples/bit-flip-syndrome.q.orca.md` with
      `[assert: entangled(qs[0], qs[1])]` etc. at the encoded state
      and `[assert: classical(qs[3..4])]` at the measured state.
      DEVIATION: used `classical(qs[0..2])` at the encoded state, not
      `entangled`. On the no-error path the checker simulates, the data
      register stays in the product codeword |000⟩ (the syndrome CNOTs have
      |0> controls), so `entangled` would *fail*. `classical(qs[3..4])` at
      the measured state holds as specified. Existing
      `tests/test_bit_flip_syndrome.py` still green.
- [x] 13.3 Create `docs/language/assertions.md` covering the
      vocabulary, statistical semantics, the destructive-measurement
      caveat, and the GHZ-marginal subtlety from design.md
      Decision 4. Also documents the PPT/negativity and confidence
      deviations.
- [x] 13.4 Update `docs/specs/spec-runtime-assertions.md`'s status
      header to mark this proposal as in flight and link to
      `openspec/changes/add-runtime-state-assertions/`.
      The spec actually lives at `docs/research/spec-runtime-assertions.md`
      (not `docs/specs/`); updated there. Also bumped the stale example
      count 19 → 20 in README.md and docs/compute-needs.md (§5.2-style drift).

## 14. Spec sync

- [x] 14.1 At archive time, sync the three delta specs into
      `openspec/specs/{language,verifier,compiler}/spec.md` per the
      OpenSpec workflow.
      Done by `openspec archive` on 2026-05-29: +3 added (Assertion Policy
      Section → language, State Assertions Stage → verifier, Assertion Metadata
      Pass-Through → compiler) and ~3 modified (State Headings + Verification
      Rules → language, Pipeline Ordering → verifier). No header mismatch — the
      MODIFIED deltas matched their existing canonical requirements.
