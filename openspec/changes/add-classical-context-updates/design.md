## Context

Q-Orca's execution model today: a machine defines a quantum circuit
(optionally with mid-circuit measurement and bit-conditional gates).
A single "shot" runs once. Any iterative learning loop — run the
circuit, read outcome, update parameters, run again — is done by a
Python harness that parses outcomes and re-instantiates the machine
with new context values.

The QPC research proposal identified the first *in-machine* learning
primitive: a classical mutation on numeric context fields, gated on
a measured bit, intended to run between shots. Shape B from the
scope discussion — conditional + arithmetic — matches the research
doc's `gradient_step` verbatim and mirrors the structural shape of
the already-shipped `QEffectConditional` (which conditions gates on
bits; this conditions *mutations* on bits).

This design spells out the AST, grammar, parser integration,
verifier additions, and compiler-emit strategy. Execution semantics
for the shot-to-shot mutation itself are deferred to a follow-up
change.

## Goals / Non-Goals

**Goals:**

- Specify a context-update effect form that covers the QPC's
  `gradient_step` verbatim: an if/else on a classical bit whose
  branches do one or more `+=`/`-=`/`=` mutations on `int` or
  `list<float>` context fields, with literal or context-ref RHS.
- Fit the existing Effect-column-of-actions pattern. No new section
  headers, no new AST layer — just a new member of the existing
  effect-type union.
- Make the verifier catch three classes of error statically:
  (1) typing mismatch (LHS is not int / list<float>), (2) undeclared
  field/bit references, (3) bit read before written
  (feedforward-incomplete) on a path to the update.
- Leave gate/measurement effects untouched — existing machines
  behave identically.
- Be tight enough in v1 that the grammar is unambiguous and the
  verifier's decisions don't require a real expression evaluator.

**Non-Goals:**

- No arbitrary RHS expressions (`theta[0] = alpha * theta[1] + beta`
  is **out**). RHS is literal-or-single-field-ref only.
- No mutation of `qubit`, `bit`, or `string` fields. Only `int` and
  `list<float>`.
- No branching on non-bit classical state (no `if iteration > 10`).
  Bit conditions only.
- No nested conditions (`if bits[0] == 1: (if bits[1] == 1: ...)`).
  Flat if/else only.
- No runtime implementation of the shot-to-shot mutation.
  Compilers emit structured comments; the actual mutation is a
  separate follow-up change (`run-context-updates` or similar).
  This keeps the current change grammar-first.
- No decision-table integration. This lives in the `## actions`
  table, not as a decision table.

## Decisions

### Disjoint effect kinds: one action = one effect kind

A single `QActionSignature` SHALL have *exactly one* of:
`gate`, `measurement`, `mid_circuit_measure`, `conditional_gate`,
`context_update`. An action that both applies a gate and mutates
context is **rejected at parse time** in v1.

**Alternatives considered:**
- *Sequence of mixed effects (gate; context_update)*. Rejected for
  v1 because the research doc's `gradient_step` doesn't need it,
  and mixing raises execution-ordering questions (does the mutation
  happen before or after the gate? within the shot or between?).
  Can be lifted in a later change once the runtime story is clear.
- *Separate section (e.g., `## context_updates`)*. Rejected because
  context updates are conceptually action-effects gated on bits —
  they belong in the same table that already carries
  measurement-and-conditional-gate effects.

### Grammar: flat if/else with semicolon-separated mutations

```
<effect>   ::= <mutation>
             | if <bit_cond>: <mut_seq> [else: <mut_seq>]
<mut_seq>  ::= <mutation> (; <mutation>)*
<mutation> ::= <lhs> <op> <rhs>
<lhs>      ::= <ident> | <ident>[<int_literal>]
<op>       ::= = | += | -=
<rhs>      ::= <int_literal> | <float_literal> | <ident>
<bit_cond> ::= bits[<int_literal>] == (0 | 1)
```

**Alternatives considered:**
- *Python-style statement blocks.* Rejected — effect strings are
  single-cell Markdown values; multi-line blocks don't fit the
  table grammar.
- *JSON-in-the-cell.* Rejected — uglier than the research-doc
  syntax, and the research doc's syntax is readable.

### AST: one new dataclass, one new optional field

```python
@dataclass
class QContextMutation:
    target_field: str
    target_idx: Optional[int]     # None for scalar, int for list element
    op: str                        # "=", "+=", "-="
    rhs_literal: Optional[float]   # if RHS is a literal
    rhs_field: Optional[str]       # if RHS is a field reference (mutually exclusive)

@dataclass
class QEffectContextUpdate:
    bit_idx: Optional[int]        # None for unconditional
    bit_value: Optional[int]      # 0 or 1; None iff bit_idx is None
    then_mutations: list[QContextMutation]
    else_mutations: list[QContextMutation]  # empty if no else clause
```

And on `QActionSignature`:
```python
context_update: Optional[QEffectContextUpdate] = None
```

### Verifier: two new static checks in a new `classical_context` substage

Adding a new file `q_orca/verifier/classical_context.py` rather
than overloading `quantum.py`. Rationale: the checks operate purely
on classical context and bit flow — zero quantum involvement.
Co-locating with quantum checks would blur the boundary.

The stage runs after `completeness` and before the quantum static
stage. If `VerifyOptions.skip_classical_context` is set, the stage
SHALL be skipped (same pattern as existing skip flags).

**Check 1 — Field typing:**
For each `QContextMutation`, look up `target_field` in
`machine.context`. If absent: `UNDECLARED_CONTEXT_FIELD` (error).
If present but not `int` (for scalar mutations) or `list<float>`
(for indexed mutations): `CONTEXT_FIELD_TYPE_MISMATCH` (error).
For indexed mutations, if the index is outside the default list's
length: `CONTEXT_INDEX_OUT_OF_RANGE` (error). RHS field refs are
checked the same way — must exist, must be numeric.

**Check 2 — Feedforward completeness:**
For each transition whose action has a `context_update` with a
`bit_idx`, verify that on every path from the initial state to
that transition, *some* prior transition's action writes to the
same bit via `measure(qs[_]) -> bits[bit_idx]` or
`mid_circuit_measure` with that bit. If no such path exists or
some path is missing the write: `BIT_READ_BEFORE_WRITE` (error).
Reachability via the existing `analyze_machine` graph — no new
graph algorithm.

### Compiler: annotation emission, not execution

Each of QASM, Qiskit, and Mermaid SHALL recognize the
`context_update` effect and emit a structured trailing comment
(QASM: `// context_update: if bits[0] == 1: theta[0] -= eta`) or
Python comment (Qiskit: `# context_update: ...`) at the site the
action would otherwise emit gates. Mermaid diagrams SHALL show the
action label as-is — no special rendering.

**Rationale:** The actual shot-to-shot mutation belongs to a
runtime (simulator / real-backend loop). Emitting it as a comment
preserves the information in the compiled artifact so downstream
tooling can lift it back out; keeps this change scoped to
language+static checks; lets us ship and integrate without
committing to a runtime design yet.

### Rollout: language → verifier → compiler, behind a parser flag

Implementation tasks break down so each step has a clean
verification signal. Parser first (with structured errors for
malformed forms), then verifier checks (against parser output),
then compiler annotations. No feature flag — the grammar is
syntactically new so existing files won't accidentally hit it.

## Risks / Trade-offs

- **[Risk]** Grammar accepts a form users expect to execute (mutate
  context between shots), but v1 doesn't execute it — someone
  writes a "training loop" in a machine and is surprised nothing
  runs. → **Mitigation:** compiler-emitted comments are explicit
  (`// context_update: (not executed in v1)`); the language spec
  scenario calls this out; the QPC research doc notes the runtime
  follow-up explicitly. Consider a verifier warning if a machine
  has both context-update actions and a `max_iter`-style loop
  guard — flags potential misuse until runtime lands.

- **[Risk]** Future need for richer RHS (e.g.,
  `theta[0] -= eta * bits[0]`) forces a second grammar rev. →
  **Mitigation:** accepted. The current shape is the research
  doc's verbatim need; widening later is a non-breaking addition
  (new `rhs_expr` variant alongside the current literal/field
  union).

- **[Trade-off]** Forbidding mixed gate+context-update actions is
  cleaner but forces users to split "measure + update" into two
  actions on two transitions. For the QPC pattern this is what
  the research doc already does (`measure_ancilla` → `gradient_step`
  on separate transitions), so no practical cost today.

- **[Trade-off]** Putting the verifier logic in a new file rather
  than threading it through the quantum stage doubles the number
  of files the verifier module imports. Small cost; pays for
  itself in separation-of-concerns.

## Migration Plan

No migration. Existing machines don't use the new grammar and
behave identically. New machines that adopt it verify/compile
cleanly but the context-update effects don't execute between
shots until the runtime follow-up change lands.

Rollback: revert this change's commits. Any machine using the new
grammar would then fail to parse, which is the intended signal
that the feature was rolled back.

## Open Questions

1. **Runtime follow-up scope.** How big is the simulator work to
   actually execute context updates between shots? Probably a
   `run-context-updates` OpenSpec change that touches the Qiskit
   runner in `q_orca/compiler/qiskit.py` plus any demo script.
   Answer informs how urgently we pursue that after this change
   lands. Not a blocker.

2. **Warning for "looks like a training loop but won't run".** If
   a machine has both `context_update` actions and a guard like
   `ctx.iteration < max_iter`, should the verifier emit a warning
   flagging that the loop is a no-op under v1? Leaning yes — it's
   cheap to detect and protects users from silent confusion — but
   deciding during implementation is fine.

3. **Unicode normalization on context-field identifiers.** The
   language spec already requires NFC normalization on state
   names; should the same rule extend to LHS identifiers in
   context updates? Leaning yes, for consistency. Will default to
   yes in the implementation unless a case against surfaces.
