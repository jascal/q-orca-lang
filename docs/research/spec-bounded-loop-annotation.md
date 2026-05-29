# Spec: Bounded Loop State Annotation `[loop N]` / `[loop until: …]`

**Status:** Draft
**Date:** 2026-05-01
**Priority:** High

> Generated: 2026-05-01 — weekly feature spec session

---

## Summary

Promote iteration from an emergent shape of the transition-table graph
into an explicit state-header annotation. A `## state` heading may now
carry a `[loop N]` annotation (fixed-count iteration of a sub-graph)
or `[loop until: <classical predicate>]` annotation (adaptive
iteration). The verifier checks loop-body unitarity once and reasons
about the back-edge as a structural feature; the compiler emits a
QASM 3.0 `for` block (or a Qiskit `ForLoopOp`) instead of unrolling
the gate sequence N times. The annotation slot is already named as
*queued* in the in-flight `add-runtime-state-assertions` proposal
(`[loop …]` listed alongside `[initial]`, `[final]`, `[assert: …]`,
`[send]`, `[receive]`), so the grammar reservation has already been
made — this spec fills it in.

The single-line argument from the v0.4 coverage analysis: *"this is
the single highest-leverage language addition relative to the
algorithm coverage it unlocks."* Grover, QAOA, Simon's, and QPE all
require iteration; without `[loop …]`, every one of them is either
manually unrolled at machine-author time (which defeats the purpose
of a high-level state-machine description and inflates Mermaid
diagrams beyond legibility) or expressed as a self-cycle in the
transition table that the classical-context verifier flags as
potentially unbounded.

---

## Motivation

**The user problem.** Iterative quantum algorithms are the bulk of
the algorithmic canon, and q-orca currently has no good way to
express them. The two existing options are:

1. **Hand-unroll the loop in the transition table.** This is what
   the shipped Grover-shaped example
   `larql-gate-knn-grover.q.orca.md` does — the diffusion operator
   is unrolled N times by copy-paste. The Mermaid diagram becomes a
   linear chain rather than a cycle, the `## state` count grows
   with N, and any change to the loop body has to be made in N
   places.

2. **Express the loop as a self-cycle and let the runtime drive it
   via a classical context counter.** This is what
   `predictive-coder-learning.q.orca.md` does — the
   `loop_back` event drives `|model_updated⟩ → |prior_ready⟩` once
   per iteration, with a guard `continue` that depends on a context
   counter. This works, but the verifier's
   `classical_context.unbounded_loop_check` has to be silenced or
   carefully proven non-divergent for every such cycle, the QASM
   compiler fully unrolls the body anyway, and the loop bound is
   invisible to the static reachability check.

Neither option compiles to a QASM 3.0 `for` block. QASM 3.0 has
first-class `for` and `while` control flow that the OpenQASM 3.0
spec (`https://openqasm.com/`) is explicit about being the
preferred shape for iterative protocols, and CUDA-Q's transpiler
(arXiv `2604.11599`) emphasizes that *"directly mapping OpenQASM 3.0
control structures to C++ control flow"* is the path to dynamic
circuits with low-latency classical feedback. Today q-orca emits
unrolled gate sequences regardless of how the iteration was
expressed, which means a 50-iteration QAOA cost-mixer alternation
becomes 100 emitted Pauli-rotation gates rather than a single
two-line `for` block.

**The current workaround.** Authors of iterative machines paste the
loop body N times, comment a `// repeat above N times` warning, and
remember to update both copies when they edit. This is the same
pattern that made macro assemblers obsolete.

**Why now.** Three forces converge in this release window:

- The just-merged `add-resource-estimation` change defines
  `gate_count` as a first-class resource metric. Unrolled loops
  inflate the metric by `N×`, making the static estimate
  overcount by exactly the loop multiplicity. A loop annotation
  fixes this — resource estimation can multiply the body cost by
  N once and report a faithful number.
- The queued `add-runtime-state-assertions` proposal explicitly
  reserves `[loop …]` in its grammar enumeration. Shipping
  `[loop N]` next slots into a slot already cut.
- QAOA, Simon's, and QPE are three of the eight examples named in
  the v0.4 coverage roadmap (§2.1, §2.2, §2.3, §2.8) as the next
  wave of canonical-algorithm coverage. None of them can be
  written cleanly without iteration.

---

## Proposed Syntax / API

### Fixed-count iteration

```markdown
## state |amplified> [loop sqrt(N)]
> Body of the Grover iteration: oracle then diffuser, N times total.
```

The argument is parsed as a numeric literal (`5`), a classical
context field reference (`p`), or a closed-form expression over
context fields and the standard math functions
(`sqrt(N)`, `ceil(pi/4 * sqrt(N))`). The expression is evaluated
once at compile time per machine instantiation; the loop bound is
then a fixed integer for the remainder of compilation and
verification.

### Adaptive iteration

```markdown
## state |constraint_collected> [loop until: rank(constraints) >= n - 1]
> Simon's algorithm: collect linearly-independent constraints
> until the period is recoverable.
```

The predicate is a classical-context expression evaluated after the
loop body completes each iteration. If false, control returns to
the loop entry; if true, control falls through to whichever
transition is annotated `loop_done`. Predicates may call any
function declared in the (existing) `## actions` table whose return
type is `bool`.

### Loop-body delimiting

A loop body is delimited by the *strongly connected component* of
the transition graph dominated by the annotated state. Concretely,
the loop body is every state on the cycle entered through the
annotated state and exited via a transition tagged
`loop_done` in the action column. The verifier rejects machines
where the SCC is ambiguous (multiple back-edges to distinct
annotated states) with a new diagnostic `LOOP_AMBIGUOUS_BODY`.

### Transition-table tags

```markdown
| Source       | Event   | Guard            | Target        | Action      |
|--------------|---------|------------------|---------------|-------------|
| |amplified>  | check   | not_converged    | |marked>      | identity    |
| |amplified>  | check   | converged        | |solution>    | measure_all, loop_done |
```

Two new action keywords are recognized:

- `loop_done` — marks the transition that exits the loop. Required
  on at least one transition out of an `[loop until: …]` annotated
  state. For `[loop N]` annotated states, optional; if absent the
  fall-through after the Nth iteration goes to whichever target
  is named in the transition with no guard (or `default`).
- `loop_back` (already used informally in
  `predictive-coder-learning.q.orca.md`; this spec promotes it to
  a recognized tag) — marks the back-edge that re-enters the loop
  body. Implicit if exactly one cycle exists.

### CLI

```bash
q-orca compile examples/grover-search.q.orca.md --target=qasm3
# emits: for i in [0:floor(pi/4 * sqrt(N))] { … body … }

q-orca compile examples/grover-search.q.orca.md --target=qasm3 --unroll-loops
# falls back to the current N-times-unrolled emission for compatibility
```

---

## Implementation Sketch

**Parser** (`q_orca/parser/markdown_parser.py`, ~120 LOC).
Extend the state-header annotation grammar already added by
`add-runtime-state-assertions` to recognize `[loop <expr>]` and
`[loop until: <predicate>]`. Reuse the existing classical-context
expression parser for the `<expr>` and `<predicate>` payloads —
these are the same expressions already accepted in the `## context`
defaults and in classical-context update actions. New AST node
`QLoopAnnotation` with discriminated kind `fixed | adaptive` and a
payload `bound_expr: ContextExpression`.

**AST** (`q_orca/ast.py`, ~30 LOC). Add `QLoopAnnotation`
dataclass; add an optional `loop: Optional[QLoopAnnotation]` field
to `QStateDef` alongside the existing `is_initial`, `is_final`
flags. Add `loop_done: bool` and `loop_back: bool` flags to
`QTransition`.

**Verifier**, three new rules:

1. `loop_body_well_formed` (~80 LOC) — runs Tarjan's SCC over the
   transition graph, identifies the SCC dominated by each `[loop]`
   annotated state, rejects ambiguous bodies. New diagnostic
   `LOOP_AMBIGUOUS_BODY`.

2. `loop_body_unitarity` (~40 LOC) — already-existing
   per-transition unitarity check, applied once over the loop
   body. The proof obligation that all N iterations are unitary
   reduces to "body is unitary" since `U^N` is unitary iff `U` is.
   No new diagnostic — reuses `NON_UNITARY_ACTION`.

3. `loop_termination_reachable` (~60 LOC) — for `[loop until: P]`,
   prove that P is satisfied on at least one execution path
   through the body. Static (model-checker-style) for predicates
   over bounded integer counters; falls back to a runtime warning
   `LOOP_TERMINATION_UNCHECKED` when the predicate involves
   floating-point context fields.

**Resource estimation** (`q_orca/verifier/resources.py`, ~25 LOC).
The just-merged `## resources` accounting walks the transition
graph and sums per-action costs. Add a multiplier on edges inside
a fixed-count loop body: cost contributions are multiplied by N
once. For adaptive loops, emit a `RESOURCE_ESTIMATE_LOOP_ADAPTIVE`
diagnostic and report cost as a range
`[body_cost, body_cost × MAX_LOOP_BOUND]` with `MAX_LOOP_BOUND=1000`
as the default.

**Qiskit compiler** (`q_orca/compiler/qiskit.py`, ~70 LOC).
Detect loop-annotated states, emit `qiskit.circuit.ForLoopOp` for
the fixed-count case (Qiskit ≥ 1.2 supports `with qc.for_loop`),
emit `WhileLoopOp` for the adaptive case. The `--unroll-loops`
flag retains current behavior.

**QASM compiler** (`q_orca/compiler/qasm.py`, ~50 LOC).
Emit OpenQASM 3.0 `for k in [0:N-1] { … }` for fixed loops; emit
`while (P) { … }` for adaptive. Falls back to unrolled QASM 2.0
if the `--qasm-version=2` flag is set, with a
`QASM2_DOWNGRADE_LOOP` warning.

**Mermaid renderer** (~30 LOC). Render loop-annotated states with
a doubled border and the loop bound as an edge label on the
back-edge (e.g., `|amplified> ←──┐ ×N`). Cleaner diagrams replace
the current N-state linear unrolling.

**Total estimate.** ~450 LOC implementation + ~250 LOC tests + ~80
LOC docs. About a week of focused work.

---

## Test Cases

1. **Fixed-bound Grover.** A new
   `examples/grover-search.q.orca.md` declares `## context | N | int
   | 16` and a state
   `## state |amplified> [loop ceil(pi/4 * sqrt(N))]` over a
   3-qubit register with a marked element. The compiled QASM 3
   contains exactly one `for k in [0:3]` block, and stage 4b
   simulation returns the marked element with probability `≥ 0.95`.

2. **Adaptive Simon's.** A new
   `examples/simons-algorithm.q.orca.md` declares
   `[loop until: rank(constraints) >= n - 1]` over a 4-qubit
   register. The verifier passes with no `LOOP_TERMINATION_UNCHECKED`
   warning (rank predicate is over integer counters). The
   classical-side post-processing (Gaussian elimination over GF(2))
   is left to the calling Python.

3. **Loop-body unitarity rejection.** A test machine annotates a
   state `[loop 5]` whose body contains a measurement (non-unitary).
   Verifier emits `NON_UNITARY_ACTION` pointing at the measurement
   row and refuses to compile.

4. **Ambiguous-body rejection.** A test machine has two states
   both annotated `[loop N]` with overlapping back-edges. Verifier
   emits `LOOP_AMBIGUOUS_BODY` with the conflicting state names.

5. **Resource-estimation accuracy.** A 4-state body annotated
   `[loop 100]` with a per-iteration `gate_count = 12` is checked
   to report `gate_count = 1200` rather than the body's `gate_count
   = 12`. The Qiskit compiler is independently checked to emit a
   single `ForLoopOp` so resource estimate and emitted code agree.

---

## Dependencies

- **`add-runtime-state-assertions`** (in flight) — names `[loop …]`
  in its annotation enumeration. We should sequence after the
  assertions proposal merges so the `[loop]` slot is already cut
  in the grammar; otherwise the two changes have to share a parser
  edit and risk merge conflict.
- **`add-resource-estimation`** (merged) — provides the
  `gate_count` infrastructure that the loop-body multiplier hooks
  into. No reverse dependency.
- **Parameterized two-qubit gates** (queued spec
  `spec-parameterized-two-qubit-gates.md`) — strict precondition
  for QAOA expressed via this loop construct, but not for the
  loop machinery itself. Grover and Simon's can land first.
- **No conflict** with `add-mps-concept-encoding` or
  `add-parameterized-invoke` — disjoint parts of the codebase.

---

## Open Questions

1. **Loop-body identification: structural or syntactic?** This
   spec proposes structural (Tarjan's SCC dominated by the
   annotated state). The alternative is syntactic — a
   `## state |...> [loop N: body=|s1>, |s2>, |s3>]` form that
   names the body explicitly. Structural is cleaner for the common
   case but requires the verifier to bail on ambiguous graphs;
   syntactic is uglier but disambiguates by construction. **Tentative
   choice: structural, with the syntactic form held in reserve as a
   `[loop N: ...explicit body...]` escape hatch if the structural
   form proves to confuse authors.**

2. **Nested loops.** Should `[loop N]` permit a nested `[loop M]`
   in its body? Theoretically fine — the SCC definition still
   identifies bodies — but it changes the emitted QASM 3 to a
   nested `for` block. **Tentative choice: permit, but add an
   integration test that a 3-level nesting compiles correctly.**

3. **Adaptive loops on quantum predicates.** `[loop until: M(q0) ==
   1]` would be a *quantum* exit condition (mid-circuit
   measurement guard). The shipped mid-circuit-measurement spec
   already covers the underlying machinery, but bounded-iteration
   semantics on a non-deterministic exit are subtle (how does the
   resource estimator bound the worst case?). **Defer:** scope
   v0.7 of this feature to *classical* exit predicates only;
   mid-circuit-measurement-guarded loops can be added in a
   follow-up once the unitary case is shipped and battle-tested.

4. **Backend coverage.** Stim (the stabilizer fast-path being
   speced separately) does not currently support `for` loops — it
   unrolls. Should the q-orca compiler refuse the stabilizer
   backend for loop-annotated machines, or silently fall through
   to unrolled emission? **Tentative choice:** silently unroll
   under stabilizer backend with an info-level diagnostic
   `LOOP_UNROLLED_FOR_BACKEND`; the cost is negligible given
   stabilizer simulation's polynomial scaling.

5. **Mermaid rendering for adaptive loops.** Fixed loops have an
   obvious "×N" edge label. Adaptive loops have no integer to
   label. **Tentative choice:** label the back-edge with a
   condensed form of the predicate (e.g.,
   `until rank ≥ n−1`) up to a 30-character cap.

