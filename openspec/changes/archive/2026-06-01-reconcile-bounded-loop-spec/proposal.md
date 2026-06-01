## Why

`add-bounded-loop-annotation` (#112) shipped three verifier/compiler behaviours
that differ from the wording its delta specs synced into the main specs. The
implementation is correct and pinned by `tests/test_bounded_loops.py`; the spec
text is what's out of date. This reconciles the specs to what the code does.

## What Changes

- **verifier — Loop Body Well-Formedness**: state explicitly that *adaptive*
  `[loop until: …]` bodies are **exempt** from the body-unitarity rule. Their
  per-iteration measurement on the `loop_back` edge is how the classical exit
  predicate advances (this is how Simon's collects one constraint per
  iteration), so a measurement inside an adaptive body does not emit
  `NON_UNITARY_ACTION`. The "fixed body must be unitary" rule is unchanged.
- **verifier — Loop Termination Reachability**: drop the unsound "the counter
  must make monotone progress toward `P`" claim. The shipped check classifies
  the predicate by the *types* of the context fields it references — an
  integer-counter predicate is accepted; a predicate involving a floating-point
  field (or referencing no bounded integer counter) emits
  `LOOP_TERMINATION_UNCHECKED`. No monotone-progress proof is attempted, because
  a counter may legitimately stall (Simon's `rank` on a linearly-dependent draw).
- **compiler — Loop Compilation**: the adaptive QASM emission is
  `while (!(P)) { … }` — `[loop until: P]` iterates *while `P` is not yet
  satisfied*. Adaptive predicates are host-computed (e.g. Simon's `rank` over
  GF(2)) and not expressible over QASM classical registers, so the Qiskit
  backend emits the adaptive body **once** under a structured host-driven marker
  rather than a literal `WhileLoopOp`; faithful adaptive iteration is host-driven.

## Impact

- Affected specs: `verifier`, `compiler` (wording only).
- Affected code: **none** — the implementation already matches; this is a
  spec-text reconciliation. The shipped behaviour is already pinned by
  `tests/test_bounded_loops.py` (`test_measurement_in_adaptive_body_allowed`,
  `test_adaptive_float_predicate_warns`, `test_adaptive_emits_while_block_qasm`).
