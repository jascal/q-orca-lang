## 1. AST

- [x] 1.1 Add `QContextMutation` dataclass in `q_orca/ast.py` with
  fields `target_field: str`, `target_idx: Optional[int]`,
  `op: str` (= | += | -=), `rhs_literal: Optional[float]`,
  `rhs_field: Optional[str]`.
- [x] 1.2 Add `QEffectContextUpdate` dataclass with fields
  `bit_idx: Optional[int]`, `bit_value: Optional[int]`,
  `then_mutations: list[QContextMutation]`,
  `else_mutations: list[QContextMutation]`.
- [x] 1.3 Add `context_update: Optional[QEffectContextUpdate] = None`
  to `QActionSignature`.

## 2. Parser

- [x] 2.1 Add `_parse_context_update_from_effect(effect_str, errors,
  action_name)` in `q_orca/parser/markdown_parser.py`. Handle the
  unconditional `<lhs> <op> <rhs>` form first, then the
  `if bits[i] == v: ... else: ...` form. Return `None` if the
  effect doesn't match the grammar (so other parsers still get a
  chance).
- [x] 2.2 Wire the new parser into `_parse_actions_table` alongside
  the existing measurement/conditional parsers. If a row produces
  both a `context_update` and any of `gate` / `measurement` /
  `conditional_gate`, emit a structured parse error and drop the
  row's `context_update`.
- [x] 2.3 Enforce LHS constraints at parse time: the LHS identifier
  must be a simple ident (no dot paths); indexed LHS requires a
  non-negative integer literal index.
- [x] 2.4 Unit tests in `tests/test_context_updates.py` covering: scalar
  increment, list-element increment with literal RHS, list-element
  update with field-ref RHS, conditional form with then+else,
  conditional with only then-branch, malformed forms (unknown op,
  nested conditions, non-bit condition).

## 3. Verifier — classical context stage

- [x] 3.1 Create `q_orca/verifier/classical_context.py` with
  `check_classical_context(machine: QMachineDef) ->
  QVerificationResult`. Iterate all actions with `context_update`.
- [x] 3.2 Implement the typing check (Requirement:
  "Classical Context Update — Static Typing") — emit
  `UNDECLARED_CONTEXT_FIELD`, `CONTEXT_FIELD_TYPE_MISMATCH`,
  `CONTEXT_INDEX_OUT_OF_RANGE` per the spec.
- [x] 3.3 Implement the feedforward-completeness check (Requirement:
  "Classical Context Update — Feedforward Completeness") using
  acyclic-path enumeration from the initial state. For each
  context-update with a `bit_idx`, confirm every path to that
  transition contains a prior `mid_circuit_measure` or
  `measurement` writing that bit. Emit
  `BIT_READ_BEFORE_WRITE` on violation.
- [x] 3.4 Wire the stage into `q_orca/verifier/__init__.py::verify()`
  between completeness/determinism and quantum-static. Respect
  `VerifyOptions.skip_classical_context` (added to `VerifyOptions`).
- [x] 3.5 Unit tests in `tests/test_context_updates.py` covering each
  error code (missing field, wrong type, out-of-range index,
  bit-read-before-write) and the happy path where a measurement
  transition writes the bit before the update.

## 4. Compiler — annotation emission

- [x] 4.1 In `q_orca/compiler/qasm.py`, detect
  `QEffectContextUpdate` actions and emit a `// context_update: ...`
  comment at the action's site. Track presence-of-any to decide
  whether to emit the file-level banner.
- [x] 4.2 Same treatment in `q_orca/compiler/qiskit.py` with Python
  `#` comments.
- [x] 4.3 In `q_orca/compiler/mermaid.py`, confirm transition-arrow
  labels render unchanged — no code change needed; covered by test.
- [x] 4.4 Serialize the original effect string on
  `QEffectContextUpdate` at parse time (`raw: str` field) so
  compilers can emit the round-trippable text without re-stringifying
  the AST.
- [x] 4.5 Unit tests in `tests/test_context_updates.py` covering QASM
  and Qiskit emission (presence of comment, presence of banner) and
  the no-context-update negative case (banner absent).

## 5. Spec + docs sync

- [x] 5.1 Run `openspec validate add-classical-context-updates
  --strict` — performed after code lands.
- [x] 5.2 Update `docs/research/spec-quantum-predictive-coder.md`
  to reference this change as the source of the grammar/AST/verifier/
  compiler landing (§Proposed Architecture item 5).

## 6. End-to-end verification

- [x] 6.1 Inline fixture machine in `tests/test_context_updates.py`
  exercises the new grammar through parser, verifier, and both
  compilers (QASM + Qiskit) end-to-end.
- [x] 6.2 Run the full suite
  `.venv/bin/python -m pytest tests/ -q
  --ignore=tests/test_cuquantum_backend.py
  --ignore=tests/test_cudaq_backend.py` — 468 passed, 5 skipped.
- [x] 6.3 Run `.venv/bin/q-orca verify` on all examples in
  `examples/` — all 10 remain VALID.

## 7. Follow-up parked (NOT this change)

- [ ] 7.1 **Parked**: open a follow-up OpenSpec proposal
  `run-context-updates` that designs the shot-to-shot runtime
  execution of context updates (simulator loop, backend-agnostic
  mutation semantics). Out of scope for this change.
- [ ] 7.2 **Parked**: once the runtime follow-up lands, extend
  `examples/predictive-coder-minimal.q.orca.md` (or a new
  `predictive-coder-learning.q.orca.md`) with the full learning
  loop and demo convergence.
