## Why

Q-Orca can express the *forward* pass of a variational quantum
circuit — parametric gates on `list<qubit>`, mid-circuit measurement
into classical bits, and classical-feedforward conditional gates.
What it cannot express is the *reverse* pass: writing a new value
back into a numeric context field based on the measured outcome.
Without that, any machine that wants to iterate (train, adapt,
update) has to stop at the end of one shot and push the learning
loop out to Python.

The Quantum Predictive Coder research proposal
(`docs/research/spec-quantum-predictive-coder.md`) makes this
concrete: its `gradient_step` action is literally

```
if bits[0] == 1: theta[0] -= eta; else: theta[0] += eta; iteration += 1
```

— a binary Kalman-style update that cannot be written in today's
Effect grammar. The research doc calls this out as "the one
genuinely new primitive" and parks the learning-loop example until
it lands.

The goal of this change is to spec that primitive, scoped tightly
enough to unblock the QPC demo without opening the door to
arbitrary expression evaluation on context fields. Shape B from the
scope discussion: an `if <bit_ref>: <mutation> else: <mutation>`
form where the mutation is `<field>[+-=] <scalar>` on `int` or
`list<float>` context fields, with `<scalar>` being a literal or a
context-field reference. Arbitrary RHS expressions
(`theta[0] = f(bits, theta, eta)`) are **out of scope** for v1.

This is planning-only for now. No code in this PR — the deliverable
is the proposal, design, delta specs, and task list. The research
doc explicitly positions the QPC as the driver for this feature.

## What Changes

- **Language**: a new effect form in the Effect column of the
  `## actions` table — a *context-update effect*. Grammar sketch:
  ```
  <mutation> ::= <lhs> <op> <rhs>
              | if <bit_cond>: <mutation> (; <mutation>)*
                (else: <mutation> (; <mutation>)*)?
  <lhs>      ::= <ctx_field>            # int scalar
              | <ctx_field>[<idx>]      # list<float> element
  <op>       ::= = | += | -=
  <rhs>      ::= <literal>              # int or float literal
              | <ctx_field>             # scalar context ref
  <bit_cond> ::= bits[<idx>] == (0 | 1)
  ```
  Context-update actions SHALL be **disjoint** from gate/measurement
  effects: an action that mutates context cannot also apply a gate
  or measurement (v1 simplicity — can be relaxed later if a
  concrete use case demands it).

- **AST**: a new `QEffectContextUpdate` dataclass alongside
  `QEffectMeasure` and `QEffectConditional`. Stores an optional bit
  condition (`bit_idx`, `bit_value`) and one-or-more atomic
  mutations (`target_field`, `target_idx?`, `op`, `rhs_literal?`,
  `rhs_field?`) for the `then`-branch and optional `else`-branch.
  A new field `context_update: Optional[QEffectContextUpdate]` on
  `QActionSignature`.

- **Parser**: extend `_parse_actions_table` in
  `q_orca/parser/markdown_parser.py` to detect and parse the new
  grammar. Emit structured parse errors for malformed forms (e.g.,
  assigning to a qubit field, referencing an undeclared context
  field, non-numeric RHS).

- **Verifier**: two new checks, both in the quantum-static stage
  (or a new `classical_context` substage — design will decide):
  1. **Field-exists / typed correctly**: the LHS field must exist
     in the machine's context and be of type `int` or
     `list<float>`; list indices must be within default-length.
  2. **Feedforward completeness** (named after the research doc):
     any `bits[i]` referenced in a context-update condition must be
     *written* (by a prior `measure(...) -> bits[i]` in the
     machine's transition order) on every path that reaches the
     update. This is the same "assigned-before-use" discipline the
     existing conditional-gate check already applies.

- **Compiler**: the QASM and Qiskit backends SHALL treat
  context-update actions as *no-ops at circuit level* but SHALL
  emit them as structured comments / script-level annotations so
  downstream tooling (simulator runtime, external training loop)
  can see them. Full multi-shot execution of the update — i.e., the
  mutation actually mutating context between shots — is **out of
  scope for this change** and will be specced separately once the
  simulator runtime story is designed. v1 delivers: grammar, AST,
  parser, verifier, compiler annotations. v1 does NOT deliver:
  runtime shot-to-shot mutation.

- **Docs**: update `docs/research/spec-quantum-predictive-coder.md`
  to reference this change's ID as the blocker for the full
  learning-loop example (one-line back-reference, not a rewrite).

## Capabilities

### New Capabilities
None. This is a language/AST/verifier/compiler extension on
existing capabilities.

### Modified Capabilities

- **`language`**: the `Actions Section` requirement gains a new
  effect kind (context-update). Gate-effect grammar is unchanged.
- **`verifier`**: two new requirements (field-exists/type,
  feedforward completeness) land in the quantum-static stage. No
  change to existing requirements.
- **`compiler`**: the `Three Backend Targets` and
  `Shared Gate Kind Coverage` requirements are unchanged; a new
  requirement covers context-update annotation emission.

## Impact

- `q_orca/ast.py` — add `QEffectContextUpdate` dataclass, extend
  `QActionSignature` with `context_update: Optional[...]`. ~20 LOC.
- `q_orca/parser/markdown_parser.py` — add
  `_parse_context_update_from_effect`, hook it into
  `_parse_actions_table` alongside the existing
  measurement/conditional parsers. ~60–80 LOC + tests.
- `q_orca/verifier/` — new file `classical_context.py` with the
  two checks, wired into `verify()` orchestration. ~80 LOC + tests.
- `q_orca/compiler/qasm.py`, `q_orca/compiler/qiskit.py`,
  `q_orca/compiler/mermaid.py` — recognize context-update actions
  and emit structured comments. ~30 LOC per backend.
- `openspec/specs/language/spec.md`,
  `openspec/specs/verifier/spec.md`,
  `openspec/specs/compiler/spec.md` — delta specs.
- `tests/` — new `tests/test_context_updates.py` covering parser,
  verifier, and compiler behavior. ~300 LOC of test code.
- `docs/research/spec-quantum-predictive-coder.md` — one-line
  back-reference to this change.
- **No new runtime dependencies.** No changes to the
  simulator runtime — the shot-to-shot mutation semantics are
  explicitly deferred to a follow-up change.
