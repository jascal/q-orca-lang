## 1. Reconcile spec wording (spec-only — no code change)

- [x] 1.1 verifier — Loop Body Well-Formedness: state that adaptive `[loop until: …]` bodies are exempt from the body-unitarity rule (per-iteration measurement on `loop_back` is expected)
- [x] 1.2 verifier — Loop Termination Reachability: replace the "monotone progress" wording with type-based predicate classification (int counter → accepted; float / no-counter → `LOOP_TERMINATION_UNCHECKED`)
- [x] 1.3 compiler — Loop Compilation: adaptive QASM emits `while (!(P))`; Qiskit adaptive is host-driven (body emitted once), not a literal `WhileLoopOp`
- [x] 1.4 Confirm the implementation and `tests/test_bounded_loops.py` already match the reconciled wording (no code change required)
