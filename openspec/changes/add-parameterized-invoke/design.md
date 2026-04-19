## Context

Q-Orca machines today are atomic: they declare a context, states,
events, transitions, actions, and run to a final state. There is
no way for one machine to invoke another, and there is no way for
a machine to declare what it *returns* to a caller. The only
composition today is hand-written Python: instantiate machine A,
extract its final context, pass values into a constructor for
machine B. That works but skips the state-machine semantics
entirely at the boundary — no verification of arg/return types,
no visual composition, no uniform treatment across classical and
quantum children.

This change specifies the calling convention that both classical
orca (existing `invoke: ChildMachine` syntax) and q-orca (no
current invoke support) can implement. It intentionally stops
short of implementing the *runtime* that actually executes a
composed machine — that's a follow-up change
(`add-composed-runtime`). Landing the grammar + static checks
first gives both ends a settled target.

Prior scope decisions that informed this design (from the
`add-classical-context-updates` design review):

- **1b — bridge layer, not shared AST.** The classical orca and
  q-orca ASTs stay separate; composition works by having a
  translator at the boundary, not by unifying the types.
- **2 — both execution modes.** Synchronous run-to-completion AND
  shot-batched. Classical children are always synchronous; quantum
  children can be either.
- **3a — explicit `## returns`.** Parent gets typed values back
  that the child has declared it will produce.
- **4 — self-loops as the canonical iteration construct.** No new
  loop syntax.

## Goals / Non-Goals

**Goals:**

- One invoke syntax that works for both classical orca children
  and q-orca children; the child's kind determines semantics (sync
  vs shot-batched), not the syntax.
- Explicit, type-checkable argument binding from parent context
  into child context.
- Explicit, type-checkable return binding from child returns back
  into parent context.
- A clear vocabulary for the "aggregates over shots" that only
  quantum children produce — without dragging that vocabulary
  into classical child semantics.
- Verifier guarantees: unresolved children, type mismatches, and
  execution-mode misuse caught statically before any code runs.
- Verifier errors from children surface to the parent with
  readable path prefixes so multi-machine composition debugs
  cleanly.
- No change to existing single-machine behavior.

**Non-Goals:**

- No runtime. The dispatcher that actually walks a composed
  machine is `add-composed-runtime`.
- No cross-file imports of children. V1 resolves children in the
  same multi-machine file only. Cross-file composition is
  `add-machine-imports`.
- No new aggregate kinds beyond `expectation`, `histogram`,
  `variance`. Extending the vocabulary is a follow-up.
- No coroutine/yield-on-measure execution mode in v1 (the
  architectural sketch mentioned it as an option; deferred).
- No shared Python base AST across orca and q-orca. The bridge
  layer handles translation at the boundary.

## Decisions

### One invoke syntax for both child kinds

```
## state <name> [invoke: <ChildMachineName>(<arg_bindings>)] [shots=<int>]
> Optional description line
> [returns: <return_bindings>]
```

Where:
- `<arg_bindings>` ::= (`<child_param>=<parent_expr>`,)* with
  `<parent_expr>` being either a bare context-field identifier
  or a parent context field + index (e.g., `theta=theta`,
  `idx=iteration`, `seed=theta[0]`).
- `<return_bindings>` ::= (`<parent_field>=<child_return>`,)* —
  analogous shape, parent-side destination on the left, child-side
  source on the right.
- `shots=<int>` is optional; forbidden for classical children,
  optional (default 1) for quantum children.

The `[invoke: ...]` annotation sits alongside `[initial]` and
`[final]` as a state-level flag. A state can have at most one
`invoke:`; an invoke state is neither `[initial]` nor `[final]`.
It may still have outgoing transitions — those transitions fire
*after* the invoke completes, taking the child's returns as
classical context in the parent. If an invoke state has no
outgoing transitions, the runtime behavior is "fallthrough to end
of machine" (which is only sensible if the parent has no further
work).

**Alternatives considered:**

- *Dedicated `## invocations` section.* Rejected — the binding
  between a state and its child is load-bearing; separating the
  invoke declaration from the state it belongs to loses the visual
  structure.
- *Transition-level invokes (on an edge rather than a state).*
  Rejected — makes the state-machine semantics murkier. An invoke
  is a computation that takes time/context; it belongs on a node,
  not an edge.
- *Multiple invokes per state.* Rejected for v1 — composes poorly
  with self-loops and return-binding semantics. A state that
  needs two invocations splits into two states.

### `## returns` section and statistical-kind annotations

A machine optionally declares what values it returns to its
caller:

```
## returns
| Name           | Type             | Statistics              |
|----------------|------------------|-------------------------|
| converged      | bool             |                         |
| final_theta    | list<float>      |                         |
| bits[0]        | bit              | expectation, histogram  |
| bits[1]        | bit              | expectation             |
```

- `Name` is either a plain identifier (refers to a context field
  at machine exit) or an indexed reference like `bits[0]`
  (refers to a specific element of a list-typed field).
- `Type` uses the same type grammar as `## context`.
- `Statistics` is allowed only on a machine that performs
  measurement (quantum). Values are comma-separated from the set
  `{expectation, histogram, variance}`. Classical machines with
  non-empty `Statistics` cells are a parse error.

Under a shot-batched invocation, each statistic listed for a
return becomes a synthesized typed field in the parent:
- `expectation` → `prob_<return_name_sanitized>: float`
- `histogram` → `hist_<return_name_sanitized>: dict[int, int]`
- `variance` → `var_<return_name_sanitized>: float`

(The sanitized name replaces `[`, `]`, `.` with `_`, so
`bits[0]` → `bits_0`.)

Under a non-shot-batched invocation (`shots=1` default), the
return binding refers to the raw declared field as it exists at
machine exit — no aggregation. The `Statistics` column is silently
unused in that mode.

**Alternatives considered:**

- *Implicit expansion with no explicit declaration.* Rejected —
  parent author would have to guess which aggregates are
  available; not discoverable, not typeable.
- *Parent-declared aggregates (`invoke: Child(...) aggregates={...}`).*
  Rejected — pushes the statistical-kind vocabulary onto the
  caller; means the child has no voice in what it supports.
- *Implicit `prob_*` and `hist_*` for every measurement-bearing
  return.* Rejected — too magical; produces fields the parent
  didn't ask for.

### Execution-mode flag: shots=N

- `shots=N` on an invoke targeting a classical child is a **parse
  error** (`SHOTS_ON_CLASSICAL_CHILD`).
- `shots=N` omitted on a quantum child defaults to `shots=1`
  (single-shot run-to-completion, returns raw values).
- `shots=N` where `N < 1` is a parse error.
- The parser cannot know at parse time whether a child is
  classical or quantum (that depends on the child's definition,
  which may not be resolved yet). This rule is therefore **enforced
  at verifier time**, not parse time — the error code is the
  same, but its origin is the composition stage.

### Verifier composition stage: new, after classical-context

A new file `q_orca/verifier/composition.py` carries all
multi-machine checks. Stage order becomes:

```
structural → completeness → determinism
  → classical-context (from add-classical-context-updates)
  → composition (new)
  → quantum-static → dynamic → superposition-leak
```

For each invoke state:

1. **Resolve child.** Child name must match some other machine in
   the same `QOrcaFile`. Otherwise: `UNRESOLVED_CHILD_MACHINE`.
2. **Arg typing.** Each `<child_param>=<parent_expr>` binding:
   child_param must be a declared context field on the child;
   parent_expr's type (inferred from parent context) must unify
   with child_param's type. Otherwise:
   `INVOKE_ARG_TYPE_MISMATCH` or `INVOKE_ARG_UNDECLARED`.
3. **Return typing.** Each `<parent_field>=<child_return>`:
   child_return must appear in child's `## returns`; parent_field
   must be a declared parent context field; types must unify;
   under `shots=N>1`, the binding refers to the *synthesized*
   aggregate field (`prob_bits_0`, etc.), not the raw return.
   Otherwise: `INVOKE_RETURN_TYPE_MISMATCH` or
   `INVOKE_RETURN_UNDECLARED`.
4. **Shots-flag rules.** Classical child + `shots=*` present →
   `SHOTS_ON_CLASSICAL_CHILD`. Quantum child with `shots=N` where
   a bound aggregate requires a non-`Statistics` return →
   `AGGREGATE_NOT_DECLARED`.
5. **Recursive verification.** Run the child's own verifier
   pipeline. Any errors surface as parent errors with path prefix
   `<invoke_state>.<child_error_path>`.
6. **No-cycles check.** A machine invoking itself (directly or
   transitively) is rejected with `INVOKE_CYCLE` in v1. (Can be
   revisited once the runtime story is clear.)

### Compiler: Mermaid renders invokes; QASM/Qiskit refuse multi-machine input

Mermaid gets a new node style for invoke states (shape: rounded
rectangle with child machine name) and an arrow to the child's
subdiagram. Child is rendered as a `state X {...}` nested block
(Mermaid state-diagram-v2 supports this natively).

QASM and Qiskit backends, when given a machine whose context
contains invoke states, SHALL emit a structured error:

```
COMPILE_COMPOSED_MACHINE: cannot compile a machine with invoke states directly.
  Compile child machines individually and compose via the runtime.
  (Runtime support is planned as `add-composed-runtime`.)
```

This keeps the grammar/AST landing this change introduces usable
for verification and diagramming without forcing a half-built
runtime.

### Parent-side error-path prefixing

When the composition verifier runs a child's pipeline and gets an
error, it wraps the error's `location` dict with the parent's
invoke-state name under a `child_path` key. Example:

Parent invokes `Child` from state `|train>`. Child's verifier
emits `INCOMPLETE_EVENT_HANDLING` on its `|idle>` state. Parent
receives an error with `location = {"invoke_state": "|train>",
"child_path": [{"state": "|idle>", "event": "run"}]}` — so the
user sees exactly where in the composed graph the problem lives.

## Risks / Trade-offs

- **[Risk]** The grammar for `[invoke: Child(...)]` as a state
  annotation may clash with future state-annotation extensions
  (e.g., `[assert: separable]` from `add-runtime-state-assertions`).
  → **Mitigation:** the `invoke:` prefix is unique and the parser
  matches it specifically; other annotations are bare words. Lint
  against collisions as future annotations land.

- **[Risk]** Recursive verification (running child's verifier
  inside parent's) could explode: a deeply nested composition
  with circular-ish references. → **Mitigation:** the
  `INVOKE_CYCLE` check runs first; verification is depth-first
  with a visited set. Worst-case O(total-machines-in-file) for a
  composition DAG.

- **[Risk]** `shots=N` coupling of grammar to statistical
  semantics forces every shot-batched invoke to materialize
  aggregates in the parent context. If the parent only wants the
  raw last-shot value, it's an extra step (read `hist_bits_0`,
  extract the dominant key). → **Mitigation:** accept this; the
  shot-batched mode is explicitly for statistical workflows.
  Single-shot users use `shots=1` (the default).

- **[Trade-off]** Refusing to compile composed machines in
  QASM/Qiskit is a temporary restriction that will bite adopters
  until `add-composed-runtime` lands. Considered emitting a
  flat-composed circuit (inline the child's gates into the
  parent's QASM), but that silently loses the state-machine
  semantics and makes shot-batched invokes impossible to express.
  Preferred a clear error over silent semantics-loss.

- **[Trade-off]** Sanitized aggregate names (`bits[0]` →
  `bits_0`) could collide with an existing parent context field.
  Verifier catches this via `INVOKE_RETURN_TYPE_MISMATCH` (a
  parent field of the same name with an incompatible type), but
  collision with a same-type field silently binds. Leaning toward:
  if the collision is intentional, the parent is reusing a field,
  which is legal; if unintentional, it's a naming problem the
  parent author should fix.

## Migration Plan

No migration — existing machines have no invoke states, no
returns sections, no multi-machine composition, and behave
identically.

Rollback: revert this change's commits. Machines using the new
grammar fail to parse, which is the expected rollback signal.

## Open Questions

1. **Does `## returns` imply a named exit point, or just a snapshot
   of final-state context?** Leaning toward "snapshot at machine
   exit," which means the `Name` column in returns refers to a
   context field at the time the machine reaches a `[final]`
   state. A machine with multiple `[final]` states may have
   different exit contexts — is that a bug in the machine, or a
   union type? Punting; will default to "last-final-state wins"
   in implementation unless someone argues otherwise.

2. **Nested invoke depth limit.** Should the verifier cap
   composition depth at some small number (say 8) to catch
   pathological compositions? Defer until we see a real case; no
   cap in v1.

3. **Shot-batched quantum returns with `measure_all`-style
   semantics.** A machine with many measurement events produces
   many bits; does shot-batched mode aggregate each independently
   (per-bit statistics) or jointly (full bitstring histogram)?
   Leaning per-bit for v1 because it matches the declared
   per-return granularity; full-bitstring histograms can be a
   future `joint_histogram` statistic.

4. **Classical-orca adoption.** The classical orca tool already
   has `invoke: ChildMachine` with no args. Does it adopt this
   change's grammar, or does the bridge layer translate? Probably
   both: orca adopts over time, and the bridge handles
   mixed-version composition. Out of scope for this change.
