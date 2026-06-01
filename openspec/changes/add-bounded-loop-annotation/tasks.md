## 1. AST + parser

- [ ] 1.1 In `q_orca/ast.py`, add `QLoopAnnotation(kind: 'fixed'|'adaptive', bound_expr)`; add `loop: Optional[QLoopAnnotation]` to `QStateDef`; add `loop_done: bool` / `loop_back: bool` to `QTransition`
- [ ] 1.2 Fill the reserved `[loop …]` slot in `_parse_state_heading` / annotation scanner: parse `[loop <expr>]` (fixed) and `[loop until: <predicate>]` (adaptive), reusing the classical-context expression parser for the payload; compose with `[initial]`/`[final]`
- [ ] 1.3 Recognize `loop_done` / `loop_back` Action-column tags (comma-separated alongside a real action) and set the `QTransition` flags
- [ ] 1.4 Backward-compat: a state with no `[loop …]` is unchanged; `[loop …]` is no longer silently ignored

## 2. Verifier rules

- [ ] 2.1 `loop_body_well_formed` (`verifier/loops.py`): Tarjan SCC dominated by the annotated state; `LOOP_AMBIGUOUS_BODY` for shared cycles / multiple back-edges / nested `[loop]` (v1 rejects nesting)
- [ ] 2.2 Loop-body unitarity: apply the existing per-transition unitarity check once over the body (reuse `NON_UNITARY_ACTION`); allow measurement on the `loop_done` exit edge
- [ ] 2.3 `loop_termination_reachable`: static check for integer-counter `until:` predicates; `LOOP_TERMINATION_UNCHECKED` warning for float predicates
- [ ] 2.4 Wire the loop stage into the verify pipeline (fires only when a `[loop …]` state is present)
- [ ] 2.5 Tighten `syndrome_completeness` (`verifier/roles.py`): when the syndrome qubit's cycle is a `[loop …]` body, require a per-iteration measure within the body before `loop_back`; keep the SCC fallback for unannotated cycles

## 3. Resource estimation

- [ ] 3.1 In the resource walk (`verifier/resources.py` / `compiler/resources.py`), multiply a fixed `[loop N]` body's per-action cost by N once
- [ ] 3.2 Adaptive loop: report `[body, body × MAX_LOOP_BOUND]` (default 1000) + `RESOURCE_ESTIMATE_LOOP_ADAPTIVE`

## 4. Compiler emission

- [ ] 4.1 Qiskit (`compiler/qiskit.py`): emit `with qc.for_loop(range(N))` / `ForLoopOp` for fixed, `WhileLoopOp` for adaptive; `--unroll-loops` retains current emission
- [ ] 4.2 QASM (`compiler/qasm.py`): emit `for k in [0:N-1] { … }` / `while (P) { … }`; `--qasm-version=2` unrolls with `QASM2_DOWNGRADE_LOOP`
- [ ] 4.3 Stabilizer backend: silently unroll with info-level `LOOP_UNROLLED_FOR_BACKEND` (dormant until that backend ships)
- [ ] 4.4 Mermaid (`compiler/mermaid.py`): render loop states with a back-edge label (`×N` / condensed predicate) instead of an unrolled chain

## 5. Examples + tests + docs

- [ ] 5.1 Add `examples/grover-search.q.orca.md` (fixed `[loop ceil(pi/4 * sqrt(N))]`) and `examples/simons-algorithm.q.orca.md` (adaptive `[loop until: rank >= n - 1]`); confirm they verify and that Grover's compiled QASM has one `for` block
- [ ] 5.2 Tests: fixed parse + single `for` block; adaptive parse + `while`; `LOOP_AMBIGUOUS_BODY`; `NON_UNITARY_ACTION` inside a body; `LOOP_TERMINATION_UNCHECKED` for floats; resource multiplier (body 12 × loop 100 = 1200); `--unroll-loops` fallback; syndrome per-iteration tightening; backward-compat (unannotated unchanged)
- [ ] 5.3 Docs: `docs/language/bounded-loops.md` (both forms, body delimiting, tags, backend behavior, deferred nesting/quantum-predicates); mark `docs/research/spec-bounded-loop-annotation.md` delivered

## 6. Recorded follow-ups (not in this change)

- Nested loops (`[loop]` inside a `[loop]` body) → nested `for` emission.
- Quantum exit predicates (`[loop until: M(q0)==1]`, mid-circuit-measurement-guarded) with a worst-case resource bound.
- The syntactic `[loop N: body=|s1>,|s2>]` escape hatch if the structural form confuses authors.
- Per-machine `MAX_LOOP_BOUND` override and runtime-parameterized loop counts.
