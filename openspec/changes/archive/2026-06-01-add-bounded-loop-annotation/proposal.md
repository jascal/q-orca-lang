## Why

Iterative quantum algorithms — Grover, QAOA, Simon's, QPE — are the bulk of the canon, and q-orca has no clean way to express them. Authors either **hand-unroll** the loop body N times in the transition table (the shipped `larql-gate-knn-grover` does this — the Mermaid diagram becomes a linear chain, the state count grows with N, and edits must be made in N places) or express it as a **self-cycle** driven by a classical counter (`predictive-coder-learning`), which the classical-context verifier flags as potentially unbounded and which the compiler unrolls anyway. Neither compiles to a QASM 3 `for`/`while` block — so a 50-iteration QAOA becomes 100 emitted gates instead of a two-line loop, and `gate_count` over-counts by exactly the loop multiplicity.

The grammar slot is already cut: the parser explicitly reserves `[loop …]` (alongside `[send]`/`[receive]`) as a recognized-but-unimplemented bracket token. This change fills it in. It also **completes a rule shipped two changes ago**: `qubit-role-types` left `syndrome_completeness` on a coarse SCC fallback "until `[loop …]` lands" — this lets it tighten to exact per-iteration completeness.

## What Changes

- Add a `## state` header annotation **`[loop <expr>]`** (fixed-count: a numeric literal, a context-field reference, or a closed-form expression over context fields + standard math functions, evaluated once at compile time) and **`[loop until: <predicate>]`** (adaptive: a *classical* context predicate evaluated after each body iteration).
- Recognize two Action-column tags: **`loop_done`** (the transition that exits the loop — required for `until:`) and **`loop_back`** (the back-edge re-entering the body; implicit when exactly one cycle exists).
- Delimit the loop body **structurally** — the strongly-connected component dominated by the annotated state; ambiguous bodies (multiple back-edges to distinct annotated states) are rejected.
- AST: `QLoopAnnotation(kind: fixed|adaptive, bound_expr)` on `QStateDef`; `loop_done`/`loop_back` flags on `QTransition`.
- Three verifier rules: `loop_body_well_formed` (`LOOP_AMBIGUOUS_BODY`), `loop_body_unitarity` (reuses `NON_UNITARY_ACTION` — `U^N` is unitary iff `U` is), `loop_termination_reachable` (`LOOP_TERMINATION_UNCHECKED` warning when an `until:` predicate is over floats).
- Resource estimation multiplies fixed-loop body cost by N (faithful `gate_count`); adaptive loops report a range with `RESOURCE_ESTIMATE_LOOP_ADAPTIVE`.
- Qiskit compiler emits `ForLoopOp` (fixed) / `WhileLoopOp` (adaptive); QASM 3 emits `for k in [0:N-1] {…}` / `while (P) {…}`. A `--unroll-loops` flag retains today's unrolled emission. Mermaid renders the loop with a `×N` (or condensed-predicate) back-edge label.
- **MODIFY** `syndrome_completeness`: when a `syndrome` qubit's cycle is a `[loop …]`-annotated body, check per-iteration completeness over that body instead of the SCC fallback.
- Out of scope (deferred, named): **nested loops** (single-level for v1; the SCC body-identification compounds with nesting); **quantum exit predicates** (`[loop until: M(q0)==1]` — classical predicates only for v1); the syntactic `[loop N: body=…]` escape hatch (held in reserve).

## Capabilities

### New Capabilities
<!-- none — extends language, verifier, compiler -->

### Modified Capabilities
- `language`: add the `[loop <expr>]` / `[loop until: <predicate>]` state annotation and the `loop_done`/`loop_back` transition tags.
- `verifier`: add the three loop rules; **modify** `syndrome_completeness` to tighten to per-iteration over an annotated loop body.
- `compiler`: emit QASM 3 `for`/`while` and Qiskit `ForLoopOp`/`WhileLoopOp`; multiply fixed-loop resource cost by N; `--unroll-loops` fallback; Mermaid loop rendering; stabilizer backend silently unrolls with `LOOP_UNROLLED_FOR_BACKEND`.

## Impact

- **Changed code**: `q_orca/parser/markdown_parser.py` (fill the reserved `[loop]` slot + tag recognition); `q_orca/ast.py` (`QLoopAnnotation`; `QStateDef.loop`; `QTransition.loop_done`/`loop_back`); `q_orca/verifier/` (3 rules + tighten syndrome); `q_orca/verifier/resources.py` + `q_orca/compiler/resources.py` (multiplier); `q_orca/compiler/qiskit.py`, `q_orca/compiler/qasm.py`, `q_orca/compiler/mermaid.py`.
- **New diagnostics**: `LOOP_AMBIGUOUS_BODY`, `LOOP_TERMINATION_UNCHECKED`, `RESOURCE_ESTIMATE_LOOP_ADAPTIVE`, `LOOP_UNROLLED_FOR_BACKEND`, `QASM2_DOWNGRADE_LOOP`.
- **New examples**: `examples/grover-search.q.orca.md` (fixed), `examples/simons-algorithm.q.orca.md` (adaptive).
- **Backward compatible**: machines without `[loop …]` are unchanged; `--unroll-loops` reproduces today's emission.
- **Dependencies**: `add-runtime-state-assertions` (merged, reserved the slot) and `add-resource-estimation` (merged, the multiplier hook) — both satisfied. Parameterized two-qubit gates (merged) needed only for QAOA, not the loop machinery; Grover/Simon's land first.
