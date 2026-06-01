# Bounded loops

Promote iteration from an emergent shape of the transition graph to an explicit
`## state` annotation. A loop-annotated state heads a **loop body** — the
strongly-connected component it enters — that the verifier checks once and the
compiler emits as a real QASM 3 `for`/`while` block (or a Qiskit
`ForLoopOp`/`WhileLoopOp`) instead of unrolling. Shipped by
`add-bounded-loop-annotation`.

```markdown
## state |amplifying> [loop ceil(pi/4 * sqrt(N))]
> Grover iterate runs a fixed number of times.

## state |collecting> [loop until: rank >= n - 1]
> Adaptive: repeat until enough constraints are gathered.
```

A state with no `[loop …]` annotation behaves exactly as before, so every
existing machine parses, verifies, and compiles unchanged.

## Two forms

| Form | Meaning | Bound |
|---|---|---|
| `[loop <expr>]` | **fixed**-count iteration | `<expr>` evaluated once at compile time to an integer |
| `[loop until: <predicate>]` | **adaptive** iteration | a classical predicate re-checked after each body iteration |

A fixed `<expr>` is a numeric literal, a context-field reference, or a
closed-form expression over context fields and the math functions `sqrt`,
`ceil`, `floor`, `round`, and the constant `pi` (e.g. `ceil(pi/4 * sqrt(N))`).
Every referenced field must have a concrete integer default, or compilation
raises `LoopBoundError`.

An adaptive `<predicate>` is a classical-context boolean expression (it may
reference context fields and call a `## actions` function returning `bool`).
`[loop until: P]` means *iterate while `P` is not yet satisfied*.

## Loop-body delimiting and transition tags

The loop body is the **strongly-connected component** entered through the
annotated state. Two Action-column tags, comma-separated alongside a real
action, mark the loop edges:

```markdown
| Source       | Event   | Guard | Target       | Action                    |
|--------------|---------|-------|--------------|---------------------------|
| |amplifying> | iterate |       | |amplifying> | grover_iterate, loop_back |
| |amplifying> | measure |       | |measured>   | read_out, loop_done       |
```

- **`loop_back`** — the back-edge that re-enters the body (implicit when exactly
  one cycle exists).
- **`loop_done`** — the edge that exits the loop. **Required** for
  `[loop until: …]`; for `[loop N]` the unguarded fall-through is the exit.

The `loop_done` edge is **outside** the body, so its action (e.g. a final
measurement) is emitted after the loop block.

## Verifier rules

Three rules fire automatically whenever a `[loop …]` state is present:

| Rule | Diagnostic | Severity |
|---|---|---|
| **loop_body_well_formed** | `LOOP_AMBIGUOUS_BODY` | error |
| **loop_body_unitarity** | `NON_UNITARY_ACTION` | error |
| **loop_termination_reachable** | `LOOP_TERMINATION_UNCHECKED` | warning |

- **Ambiguous body** — two `[loop …]`-annotated states sharing one cycle (which
  also covers nested loops in v1) is rejected.
- **Body unitarity** — a **fixed** `[loop N]` body must be unitary, so a
  measurement on an in-body transition (anything but the `loop_done` exit edge)
  is rejected: `U^N` is unitary iff `U` is. An **adaptive** `[loop until: …]`
  body is *exempt* — its per-iteration measurement on the `loop_back` edge is
  exactly how the classical exit predicate advances (this is how Simon's
  algorithm collects one constraint per iteration).
- **Termination** — an adaptive predicate over integer counters is accepted; one
  that compares a floating-point context field (whose progress can't be checked
  statically) emits the `LOOP_TERMINATION_UNCHECKED` warning rather than failing.

A `syndrome` qubit whose cycle is a `[loop …]` body is held to the **exact
per-iteration** completeness check (measured on every path before `loop_back`),
tightening the strongly-connected-component fallback that `add-qubit-role-types`
left in place for unannotated cycles.

## Compilation

| Target | Fixed `[loop N]` | Adaptive `[loop until: P]` |
|---|---|---|
| QASM 3 | `for k in [0:N-1] { … }` | `while (!(P)) { … }` |
| Qiskit | `with qc.for_loop(range(N)): …` | host-driven (body emitted once, marked) |
| Mermaid | loop state + `⟲ ×N` back-edge label | `⟲ until …` (condensed, ≤ 30 chars) |

Pass **`--unroll-loops`** to retain the previous emission: a fixed body is
repeated `N` times with no `for` block. Resource estimation multiplies a fixed
body's per-iteration cost by `N` so `gate_count` / `cx_count` / `depth` are
faithful; an adaptive loop reports a range up to `MAX_LOOP_BOUND` (default 1000)
with a `RESOURCE_ESTIMATE_LOOP_ADAPTIVE` diagnostic.

> **Adaptive QASM caveat.** A `while` condition references QASM classical
> registers, but adaptive predicates are typically host-computed (e.g. Simon's
> `rank` over GF(2)). The emitted `while (!(P))` is a structural placeholder;
> the Qiskit path emits the body once under a host-driven marker. Faithful
> adaptive execution is host-driven.

## Examples

- `examples/grover-search.q.orca.md` — fixed `[loop ceil(pi/4 * sqrt(N))]`.
- `examples/simons-algorithm.q.orca.md` — adaptive `[loop until: rank >= n - 1]`.

## Deferred (v1 scope)

- **Nested loops** (`[loop]` inside a `[loop]` body) — rejected as
  `LOOP_AMBIGUOUS_BODY` for now.
- **Quantum exit predicates** (`[loop until: M(q0) == 1]`) — classical
  predicates only.
- The syntactic `[loop N: body=…]` body-naming escape hatch.
