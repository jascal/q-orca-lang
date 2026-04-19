## 1. AST

- [ ] 1.1 Add `QContextMutation` dataclass in `q_orca/ast.py` with
  fields `target_field: str`, `target_idx: Optional[int]`,
  `op: str` (= | += | -=), `rhs_literal: Optional[float]`,
  `rhs_field: Optional[str]`.
- [ ] 1.2 Add `QEffectContextUpdate` dataclass with fields
  `bit_idx: Optional[int]`, `bit_value: Optional[int]`,
  `then_mutations: list[QContextMutation]`,
  `else_mutations: list[QContextMutation]`.
- [ ] 1.3 Add `context_update: Optional[QEffectContextUpdate] = None`
  to `QActionSignature`.

## 2. Parser

- [ ] 2.1 Add `_parse_context_update_from_effect(effect_str, errors,
  action_name)` in `q_orca/parser/markdown_parser.py`. Handle the
  unconditional `<lhs> <op> <rhs>` form first, then the
  `if bits[i] == v: ... else: ...` form. Return `None` if the
  effect doesn't match the grammar (so other parsers still get a
  chance).
- [ ] 2.2 Wire the new parser into `_parse_actions_table` alongside
  the existing measurement/conditional parsers. If a row produces
  both a `context_update` and any of `gate` / `measurement` /
  `conditional_gate`, emit a structured parse error and drop the
  row's `context_update`.
- [ ] 2.3 Enforce LHS constraints at parse time: the LHS identifier
  must be a simple ident (no dot paths); indexed LHS requires a
  non-negative integer literal index.
- [ ] 2.4 Unit tests in `tests/test_parser.py` covering: scalar
  increment, list-element increment with literal RHS, list-element
  update with field-ref RHS, conditional form with then+else,
  conditional with only then-branch, malformed forms (unknown op,
  nested conditions, non-bit condition).

## 3. Verifier — classical context stage

- [ ] 3.1 Create `q_orca/verifier/classical_context.py` with
  `check_classical_context(machine: QMachineDef) ->
  QVerificationResult`. Iterate all actions with `context_update`.
- [ ] 3.2 Implement the typing check (Requirement:
  "Classical Context Update — Static Typing") — emit
  `UNDECLARED_CONTEXT_FIELD`, `CONTEXT_FIELD_TYPE_MISMATCH`,
  `CONTEXT_INDEX_OUT_OF_RANGE` per the spec.
- [ ] 3.3 Implement the feedforward-completeness check (Requirement:
  "Classical Context Update — Feedforward Completeness") using
  `analyze_machine` for reachability. Walk paths from initial
  state; for each context-update with a `bit_idx`, confirm every
  path to that transition contains a prior `mid_circuit_measure`
  or `measurement` writing that bit. Emit
  `BIT_READ_BEFORE_WRITE` on violation.
- [ ] 3.4 Wire the stage into `q_orca/verifier/__init__.py::verify()`
  between completeness and quantum-static. Respect
  `VerifyOptions.skip_classical_context` (add that flag to
  `VerifyOptions`).
- [ ] 3.5 Unit tests in `tests/test_verifier.py` covering each
  error code (missing field, wrong type, out-of-range index,
  bit-read-before-write) and the happy path where a measurement
  transition writes the bit before the update.

## 4. Compiler — annotation emission

- [ ] 4.1 In `q_orca/compiler/qasm.py`, detect
  `QEffectContextUpdate` actions and emit a `// context_update: ...`
  comment at the action's site. Track presence-of-any to decide
  whether to emit the file-level banner.
- [ ] 4.2 Same treatment in `q_orca/compiler/qiskit.py` with Python
  `#` comments.
- [ ] 4.3 In `q_orca/compiler/mermaid.py`, confirm transition-arrow
  labels render unchanged — likely no code change, just a test.
- [ ] 4.4 Serialize the original effect string on
  `QEffectContextUpdate` at parse time (add `raw: str` field) so
  compilers can emit the round-trippable text without re-stringifying
  the AST.
- [ ] 4.5 Unit tests in `tests/test_compiler.py` covering QASM and
  Qiskit emission (presence of comment, presence of banner) and
  the no-context-update negative case (banner absent).

## 5. Spec + docs sync

- [ ] 5.1 Run `openspec validate add-classical-context-updates
  --strict` — already required at the end of the OpenSpec propose
  flow; re-run after code lands.
- [ ] 5.2 Add a one-line pointer in
  `docs/research/spec-quantum-predictive-coder.md` referencing this
  change ID as the blocker the research proposal flagged (research
  doc's §Proposed Architecture item 5, "Parameter-update
  actions...not yet shipped").

## 6. End-to-end verification

- [ ] 6.1 Write a minimal fixture machine using the new grammar
  (extends `examples/predictive-coder-minimal.q.orca.md` with a
  `gradient_step` action and a loop-back transition). Confirm it
  parses, verifies, and compiles to QASM/Qiskit with annotations
  present.
- [ ] 6.2 Run the full suite
  `.venv/bin/python -m pytest tests/ -q
  --ignore=tests/test_cuquantum_backend.py
  --ignore=tests/test_cudaq_backend.py` and confirm green.
- [ ] 6.3 Run `.venv/bin/q-orca verify` on all examples in
  `examples/` and confirm none regress.

## 7. Follow-up parked (NOT this change)

- [ ] 7.1 **Parked**: open a follow-up OpenSpec proposal
  `run-context-updates` that designs the shot-to-shot runtime
  execution of context updates (simulator loop, backend-agnostic
  mutation semantics). Out of scope for this change.
- [ ] 7.2 **Parked**: once the runtime follow-up lands, extend
  `examples/predictive-coder-minimal.q.orca.md` (or a new
  `predictive-coder-learning.q.orca.md`) with the full learning
  loop and demo convergence.
