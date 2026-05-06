## 0. Proposal + spec deltas

- [x] 0.1 Author `proposal.md`, `specs/language/spec.md`,
  `specs/compiler/spec.md`, `specs/verifier/spec.md`, this
  `tasks.md`. Validate via `openspec validate
  extend-conditional-gate-compound-bits --strict`.

## 1. AST

- [x] 1.1 Extended `q_orca/ast.py::QEffectConditional` with
  `conditions: list[tuple[int, int]]`. `bit_idx` / `value` are kept
  as legacy fields and re-synced from `conditions[0]` in
  `__post_init__`, so existing read-only consumers and the legacy
  `(bit_idx, value, gate)` constructor form keep working.

## 2. Parser

- [x] 2.1 Replaced `_parse_conditional_gate_from_effect` with a
  head + and-chain regex parser that recognises zero or more
  `and bits[<int>] == <0|1>` clauses after the head and builds
  the full `[(bit_idx, value), …]` list before parsing the gate
  body.
- [x] 2.2 Conflicting clauses (same `bits[i]`, different values)
  are rejected with a structured parse error that names the action,
  bit index, and both declared values.
- [x] 2.3 Added 12 unit tests in
  `tests/test_mid_circuit_measurement.py::TestCompoundConditional`
  covering single-clause, two-bit, mixed-value, three-bit,
  conflict-rejection, and whitespace-flexibility cases.

## 3. Compiler — OpenQASM

- [x] 3.1 `q_orca/compiler/qasm.py` joins per-clause `c[i]` /
  `!c[i]` tokens with ` && ` and emits
  `if (c[0] && !c[1]) { x q[0]; }`. Single-clause emit is
  unchanged (`if (c[0]) { ... }`).
- [x] 3.2 Compound and single-clause shapes are pinned in the new
  `TestCompoundConditional` cases.

## 4. Compiler — Qiskit

- [x] 4.1 Both the script-emit path and the iterative
  `build_circuit_for_iteration` path now nest `with
  qc.if_test((c[i_k], v_k)):` blocks one per clause, with the
  gate at the innermost level. Single-clause emit is unchanged.
- [x] 4.2 `_infer_bit_count` now iterates every condition in
  `cond.conditions`, not just the head, so the classical register
  is sized to fit the largest referenced bit index.
- [x] 4.3 Tests covering the nested `if_test` shape and
  classical-register sizing live in `TestCompoundConditional`.

## 5. Compiler — resource estimation

- [x] 5.1 Audited `q_orca/compiler/resources.py`. `qc.count_ops()`
  treats a nested `if_test` chain as a single top-level `if_else`
  op — compound conditionals contribute exactly `1` to
  `gate_count` and `0` to `cx_count` / `t_count`, satisfying the
  spec scenario without any code change. Pinned by
  `tests/test_resource_estimation.py::test_compound_conditional_counts_as_single_gate`
  and `…::test_bit_flip_syndrome_resources`.

## 6. Verifier

- [x] 6.1 `q_orca/verifier/quantum.py` now iterates
  `action.conditional_gate.conditions` (instead of the head only)
  when collecting `feedforward_bits`, so a machine that reads two
  measured bits via compound conditionals registers both as
  fed-forward.
- [x] 6.2 The `verify_skill` exercise of the rewritten
  `examples/bit-flip-syndrome.q.orca.md` (compound conditionals
  reading both `bits[0]` and `bits[1]`) now passes
  `feedforward_completeness` — captured in
  `TestBitFlipSyndromeVerify`.

## 7. Example fix

- [x] 7.1 Rewrote `examples/bit-flip-syndrome.q.orca.md` so all
  four syndrome patterns map to the right correction. Added a
  `correct_q1` event, a `|q1_corrected>` state, and a fourth
  correction transition between the existing
  `|q0_corrected>` / `|corrected>` chain. The three correction
  actions are:
  - `correct_q0`: `if bits[0] == 1 and bits[1] == 0: X(qs[0])`
  - `correct_q1`: `if bits[0] == 1 and bits[1] == 1: X(qs[1])`
  - `correct_q2`: `if bits[0] == 0 and bits[1] == 1: X(qs[2])`
- [x] 7.2 The state docstrings now match each branch
  ("(1, 0) — error on q0", etc.).

## 8. Behavior test for the example

- [x] 8.1 Added `tests/test_bit_flip_syndrome.py` with parse /
  verify / compile / snapshot classes mirroring
  `tests/test_quantum_teleportation.py`, plus a behavior class
  that simulates all four syndrome patterns ((0,0), (1,0),
  (1,1), (0,1)) and asserts the data register ends in |000>.
  The behavior tests gate on `qiskit_aer` (it is the only
  installed simulator that supports `if_test`) — they skip
  locally and run in CI where the `[quantum]` extras install
  `qiskit-aer`.

## 9. Snapshot updates

- [x] 9.1 No external snapshot files exist; AST/verification
  snapshots in this repo are inline dicts within the relevant
  test file. The bit-flip-syndrome inline snapshot is in
  `tests/test_bit_flip_syndrome.py::TestBitFlipSyndromeSnapshot`.

## 10. Wire in the backlog

- [x] 10.1 Marked §5.1 done in
  `openspec/changes/tech-debt-backlog/tasks.md` with a pointer to
  this change.

## 11. Validation

- [x] 11.1 `pytest -q` green: 891 passed, 10 skipped (4 of which
  are the new aer-gated behavior tests; the other 6 are
  pre-existing).
- [x] 11.2 `openspec validate extend-conditional-gate-compound-bits
  --strict` passes.
