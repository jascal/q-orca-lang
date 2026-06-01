## Context

State-header annotations (`[initial]`, `[final]`, `[assert: …]`, `[invoke: …]`) are scanned by `_parse_md_annotations`/`_parse_state_heading`; unrecognized bracket tokens — explicitly including `[loop …]`, `[send]`, `[receive]` — are "left untouched, not errored" (markdown_parser.py:822). So the grammar slot exists and machines using `[loop N]` today silently ignore it. `QStateDef` carries `is_initial`/`is_final`/`assertions`/`invoke`; `QTransition` carries `source`/`event`/`target`/`guard`/`action`. The classical-context expression parser already handles the kind of expressions a loop bound/predicate needs (it parses `## context` defaults and context-update RHS). `add-resource-estimation` walks the transition graph summing per-action costs. And `qubit-role-types` left `syndrome_completeness` on an SCC fallback explicitly pending this change.

## Goals / Non-Goals

**Goals:**
- Express iteration as a first-class `[loop …]` annotation, compiling to QASM 3 `for`/`while` and Qiskit `ForLoopOp`/`WhileLoopOp` rather than an unrolled gate list.
- Faithful resource estimation (body × N) and per-iteration `syndrome_completeness`.
- Backward compatibility + a `--unroll-loops` escape to today's emission.

**Non-Goals:**
- **Nested loops** — v1 targets single-level loops; nesting compounds the SCC body-identification and the emitted nested-`for` story. Deferred (Open Question 2).
- **Quantum exit predicates** (`[loop until: M(q0)==1]`) — classical predicates only for v1; mid-circuit-measurement-guarded loops have subtle worst-case resource bounds. Deferred (Open Question 3).
- The syntactic `[loop N: body=|s1>,|s2>]` escape hatch — held in reserve unless the structural form confuses authors (Open Question 1).

## Decisions

### D1 — Two annotation forms, classical payloads
`[loop <expr>]` (fixed) takes a numeric literal, a context-field reference, or a closed-form expression over context fields + standard math (`sqrt`, `ceil`, `floor`, `pi`), evaluated once at compile time to a fixed integer. `[loop until: <predicate>]` (adaptive) takes a classical-context boolean predicate (may call a `## actions` function whose return type is `bool`), evaluated after each body iteration. Both reuse the existing classical-context expression parser. `QLoopAnnotation(kind, bound_expr)` on `QStateDef`.

### D2 — Structural loop-body delimiting (SCC dominated by the annotated state)
The body is the strongly-connected component entered through the `[loop]`-annotated state and exited via a `loop_done`-tagged transition. Tarjan's SCC identifies it. A machine where the SCC is ambiguous — multiple back-edges to distinct annotated states, or two `[loop]` states sharing a cycle — is rejected with `LOOP_AMBIGUOUS_BODY` naming the conflicting states. Chosen over the syntactic body-naming form (Open Question 1) for ergonomics; the syntactic form is the reserved escape hatch.

### D3 — Transition tags `loop_done` / `loop_back`
Recognized as Action-column keywords (comma-separated alongside a real action, e.g. `measure_all, loop_done`). `loop_done` marks the exit edge (required for `until:`; optional for `[loop N]` where the unguarded/`default` target is the fall-through). `loop_back` marks the back-edge; implicit when exactly one cycle exists. New `loop_done`/`loop_back` bool flags on `QTransition`.

### D4 — Three verifier rules
- `loop_body_well_formed` — Tarjan SCC; reject ambiguous bodies (`LOOP_AMBIGUOUS_BODY`).
- `loop_body_unitarity` — the existing per-transition unitarity check applied once over the body; `U^N` is unitary iff `U` is, so a measurement inside a `[loop N]` body still triggers the existing `NON_UNITARY_ACTION` (no new diagnostic). (An adaptive loop whose exit is classical may legitimately measure on the `loop_done` edge — outside the unitary body.)
- `loop_termination_reachable` — for `until: P`, statically prove P is satisfiable on some body path when P is over bounded integer counters; fall back to a `LOOP_TERMINATION_UNCHECKED` warning when P involves floats.

### D5 — Resource estimation multiplier
Fixed loop: multiply the body's summed per-action cost by N once (faithful `gate_count`/`cx_count`/`depth`). Adaptive loop: report a range `[body_cost, body_cost × MAX_LOOP_BOUND]` (`MAX_LOOP_BOUND = 1000`) and emit `RESOURCE_ESTIMATE_LOOP_ADAPTIVE`. This corrects the over-count the current unroll-everything path produces.

### D6 — Compiler emission + backend behaviour
Qiskit: `with qc.for_loop(range(N))` (`ForLoopOp`) for fixed; `WhileLoopOp` for adaptive. QASM 3: `for k in [0:N-1] { … }` / `while (P) { … }`. `--unroll-loops` retains the current N-times emission. QASM 2 downgrade unrolls with `QASM2_DOWNGRADE_LOOP`. The stabilizer backend (when it ships) has no `for`, so it silently unrolls with an info-level `LOOP_UNROLLED_FOR_BACKEND` (cost negligible under polynomial stabilizer scaling — Open Question 4).

### D7 — Tighten `syndrome_completeness` (closes the qubit-role follow-up)
`qubit-role-types` shipped `syndrome_completeness` on an SCC fallback "until `[loop …]` lands". This change MODIFIES that requirement: when a `syndrome` qubit's cycle is a `[loop …]`-annotated body, the rule checks that the qubit is measured **once per body iteration** (within the annotated body, before `loop_back`), which is exact rather than the conservative SCC approximation. Unannotated cyclic machines keep the SCC fallback.

### D8 — Mermaid rendering
Loop-annotated states render with a doubled border and a back-edge label: `×N` for fixed loops, a condensed predicate (`until rank ≥ n−1`, ≤30 chars) for adaptive (Open Question 5). Replaces today's N-state linear unrolling.

## Risks / Trade-offs

- **SCC body-identification is the hard part** → it can be ambiguous on dense graphs; the rule errors (`LOOP_AMBIGUOUS_BODY`) rather than guessing, and the reserved syntactic escape hatch is the fallback if real machines hit it.
- **Compile-time evaluation of `[loop sqrt(N)]`** → requires the bound's context fields to be concrete at compile time; if a referenced field has no default, emit a clear error rather than a runtime-shaped bound.
- **Qiskit `for_loop` body must contain only loop-safe ops** → the unitarity rule already forbids measurement inside a fixed body; the adaptive `WhileLoopOp` path is more delicate and is gated on classical predicates only (D1).
- **Backward compatibility** → `[loop …]` was a silently-ignored token, so a machine that *accidentally* wrote `[loop 5]` and relied on it being ignored would change behavior; this is acceptable (the token was reserved and documented as queued), and `--unroll-loops` reproduces the unrolled shape.

## Migration Plan

Additive. New annotation (absent = unchanged), new verifier rules (fire only on `[loop]` states), one MODIFIED syndrome rule (tightens only when a loop body is annotated — strictly more precise, never more permissive for unannotated machines), compiler emission behind the new annotation with `--unroll-loops` for the old shape. New Grover/Simon's examples. Rollback = revert; unannotated machines are the pre-change behavior.

## Open Questions

1. **Nested loops** — deferred to a follow-up; v1 rejects a `[loop]` inside a `[loop]` body with `LOOP_AMBIGUOUS_BODY` (or a dedicated `LOOP_NESTING_UNSUPPORTED`) rather than mis-emitting.
2. **Adaptive worst-case bound** — `MAX_LOOP_BOUND = 1000` is a default; a per-machine override is a possible follow-up.
3. **`for_loop` parameter binding for `[loop sqrt(N)]` where N varies per instantiation** — v1 evaluates the bound at compile time from context defaults; parameterized loop counts (a runtime `N`) are a follow-up.
