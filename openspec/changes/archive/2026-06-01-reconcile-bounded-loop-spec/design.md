## Context

`add-bounded-loop-annotation` shipped with three implementation choices that
diverged from the wording its delta specs synced into the main specs (the
divergences were flagged in the implementation PR #112). This change is
**spec-only**: it edits three requirement texts to match the shipped, tested
behaviour. There is no code change.

## Decisions

### D1 — Adaptive bodies are exempt from body-unitarity
A fixed `[loop N]` body must be unitary (`U^N` is unitary iff `U` is). An
adaptive `[loop until: P]` body measures on its `loop_back` edge each iteration
to advance the classical exit predicate (this is how Simon's collects one
constraint per iteration), so it is exempt from the unitarity rule. The verifier
requirement now states this explicitly rather than only saying "fixed".

### D2 — Termination by predicate-type classification, not monotone progress
The shipped `loop_termination_reachable` rule accepts integer-counter predicates
and warns (`LOOP_TERMINATION_UNCHECKED`) on float-involving or no-counter
predicates. It does not attempt a monotone-progress proof — an integer counter
may legitimately stall between iterations (Simon's `rank` on a
linearly-dependent draw), so the original "must make monotone progress" wording
was unsound.

### D3 — Adaptive QASM is `while (!(P))`; Qiskit adaptive is host-driven
`[loop until: P]` iterates *while `P` is not yet satisfied*, so the QASM `while`
condition is the negation of the predicate. Adaptive predicates are
host-computed (e.g. Simon's `rank` over GF(2)) and not expressible over QASM
classical registers, so the Qiskit backend emits the adaptive body once under a
structured host-driven marker rather than a literal `WhileLoopOp`.

## Risks / Trade-offs

None functional — the implementation and `tests/test_bounded_loops.py` already
encode all three behaviours. The only risk is spec-text drift if future work
re-introduces the superseded wording; the tests guard the behaviour regardless.
