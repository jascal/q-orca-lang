## Context

This change records two pieces of work that surfaced together while
building LARQL-flavored quantum demos:

1. **Multi-controlled gate support (already implemented).** Building a
   4-qubit Grover gate-KNN demo (the smallest instance that meaningfully
   exercises the Grover diffusion + oracle pattern) revealed that
   `_parse_single_gate` in `q_orca/compiler/qiskit.py` only recognized
   `CNOT`, `CZ`, and a single 3-qubit `CCNOT`. The Grover oracle for
   `N=16, M=1` requires `MCZ` on 3 controls + 1 target, and the
   diffusion operator wraps the same MCZ in `H` and `X` sandwiches. We
   extended the parser, both compilers, the verifier whitelist, and
   the Qiskit-script emission to handle CCX/CCNOT/Toffoli/CCZ/MCX/MCZ
   end-to-end, plus a `transpile()` pass to satisfy
   Qiskit's `BasicSimulator` basis. The change is in code; this
   document promotes it to a spec-level commitment.

2. **Parametric action signatures (newly proposed).** The follow-on
   demo is a polysemantic-feature concept-projection machine over 12
   non-orthogonal LARQL concepts in a 3-qubit register. With the
   current language each concept needs its own `query_concept_X`
   action even though all twelve differ only in which qubit gets a
   Hadamard. The state machine swells from O(states + concepts) to
   O(states × concepts) and pushes past the "one screen of markdown"
   affordance the language otherwise preserves. Allowing actions to
   declare typed positional parameters and transitions to invoke them
   with bound literal values reduces the bloat back to one action per
   *kind* of gate sequence, plus N call sites in the transitions
   table.

The two halves go together because the parametric expansion produces
gate-effect strings that immediately pass through the gate-effect
parser, so the recognized gate set must be closed under the kinds the
templates emit. Adding parametric actions while leaving `MCX` out of
the parser would create a class of "templates that only work for some
gate kinds" that is exactly the friction this change exists to remove.

## Goals / Non-Goals

**Goals:**

- Lock in the multi-controlled gate set (`CCX`/`CCNOT`/`Toffoli`/`CCZ`,
  `MCX`, `MCZ`) as a spec-level capability across language, compiler,
  and verifier — not just an in-tree fix.
- Define the parametric action signature grammar narrowly enough that
  it is a small, well-bounded extension: typed positional parameters,
  literal arguments at the call site, compile-time substitution into
  the effect string. No runtime parameter binding, no defaults, no
  variadics.
- Preserve the existing zero-parameter signature form unchanged: every
  example currently in the tree continues to parse and verify
  identically.
- Make per-call-site verification the contract: verifier errors point
  at the transition that triggered them, not at the action template.

**Non-Goals:**

- Expression languages inside subscripts. `qs[c]` works; `qs[c+1]` and
  `qs[2*c]` do not. If we need them later it is a separate change.
- Runtime-evaluated parameters from context fields. Quantum circuits
  are static at compile time except via mid-circuit measurement; that
  is governed by the existing mid-circuit-measurement spec and is out
  of scope here.
- Default parameter values, variadic parameters (`*args`), or
  named-argument call syntax. Initial scope is positional, fully-bound
  calls only.
- Generalizing `parameter` on `QuantumGate` to mean "action parameter".
  `parameter` stays a rotation angle on the AST; "action parameter" is
  a sibling concept on `QActionSignature` / `QTransition`.
- New backends or new simulator integrations. The transpile pass is a
  property of the existing Qiskit-script emission path, not a new
  backend.

## Decisions

### Decision 1 — `MCX`/`MCZ` over generic `MC<gate>`

Q-Orca recognizes `MCX` and `MCZ` as named gate kinds, not a generic
`MC(<gate>, controls, target)` family. The two cases we have evidence
for in actual demos are X-flavored and Z-flavored multi-controlled
operators (Grover oracle and diffusion); other multi-controlled gates
(`MCRy`, `MCSWAP`, etc.) have no in-tree call site.

Naming follows Qiskit convention (`qc.mcx(controls, target)`) so the
mental model carries over for users coming from there. The QASM 3.0
form `ctrl(N) @ x` is general but harder to read at a glance; we keep
`MCX` as the source-form name and lower it to `ctrl(N) @ x` in the
QASM emitter.

`CCZ` is its own gate (not `MCZ` with 2 controls) because the parser
restricts `MC*` to ≥3 args (≥2 controls). The split makes the parser's
disambiguation trivial and forces the user to write the more readable
form when one exists.

Alternative considered: a single `MC(<gate>, ...)` parser branch with
the inner gate name as an argument. Rejected because the argument
shape would shift between gate kinds (some take an angle, some don't),
forcing the parser to special-case every gate kind anyway.

### Decision 2 — H-sandwich lowering for `*Z` gates

`CCZ` and `MCZ` are lowered uniformly to `H(target); MC<X>; H(target)`
in both QASM and Qiskit emitters. This avoids depending on Qiskit's
optional `qc.ccz` alias (not always available across versions) and
sidesteps the `BasicSimulator`'s lack of native `mcz` support without
needing a second basis-gate entry. It also keeps the verifier's
unitarity check on a single MCX/CCX implementation.

The trade-off is that the emitted circuit is two extra Hadamards
deep, which matters for noise simulation but not for the unitarity
check or analytic statevector simulation. For demos that need the
tighter physical depth, a future change can introduce a backend hint
to skip the sandwich on backends that natively support `ccz` / `mcz`.

### Decision 3 — Transpile *only* in the shots branch

`Statevector` accepts the un-decomposed circuit and runs faster
without the transpile pass. The shots branch (`BasicSimulator`,
`AerSimulator`) cannot, because their internal gate dispatchers reject
`mcx` outright. We isolate the `transpile()` call to the shots branch
of the generated script and pin the basis to the gates the simulators
implement, plus the rotation primitives we already emit.

Alternative considered: transpile unconditionally, accept the
analytic-mode overhead. Rejected because `Statevector`-based
verification is the primary path for unit tests; doubling its compile
time per-test is a real cost that buys nothing.

Alternative considered: skip the transpile and require users to pre-
decompose multi-controlled gates in their effect strings. Rejected
because it pushes a backend concern into the language layer — exactly
the inversion the compiler is supposed to prevent.

### Decision 4 — Parametric expansion at the *call site*, not the template

When `query_concept(c=3)` is reached during BFS gate-sequence
extraction, the compiler resolves the action by name, copies its
effect string, substitutes `3` for `c` in the copy, then runs the
existing gate-effect parser on the resulting fully-literal string.
The action template itself is never compiled to gates directly; only
its expansions are.

This keeps every existing single-gate-extraction code path unchanged.
The compiler's BFS over transitions already calls
`_parse_effect_string` per transition; the only new step is "if this
transition's action is parameterized, build a substituted effect
string first, then parse that." No new AST node for
"parameterized gate", no new emitter for "deferred substitution".

Alternative considered: store the parameterized action as a single AST
node with a `parameters` slot, generate a Qiskit `Gate` subclass with
a `__call__` per call site. Rejected as massive over-engineering for
the use case (compile-time integer substitution into a string).

Alternative considered: macro-expand at parse time, eagerly producing
N copies of the action with bound names. Rejected because it loses the
"one source-form action, N call sites" symmetry in error messages and
in Mermaid output, which is the entire user-facing payoff.

### Decision 5 — Identifier subscript grammar limited to bare identifiers

The parser accepts `qs[c]` where `c` is a single identifier matching
a parameter name in the enclosing action's signature. `qs[c+1]`,
`qs[c*2]`, `qs[c, 0]` all fail to parse with a structured error.

The constraint keeps the parser regex simple and keeps expansion a
literal string substitution rather than a tiny expression evaluator.
If a use case for arithmetic in subscripts emerges, it is a separate
change with its own design decision about the expression language to
support.

The same restriction applies to angle parameters: `Rx(qs[0], theta)`
accepts a bare identifier; `Rx(qs[0], theta + pi/4)` does not. The
existing symbolic angle grammar (`pi/4`, `3*pi/4`, etc.) only applies
to the literal angle form at the call site, not inside the action
template.

### Decision 6 — Parametric and parameterized are different words

The change documents two distinct concepts:

- **Parameterized gate**: a quantum gate that takes a numeric parameter
  (an angle). `Rx(qs[0], pi/4)` is a parameterized gate. The
  `parameter` field on `QuantumGate` already exists for this.
- **Parametric action**: an action whose definition takes typed
  positional parameters. `query_concept | (qs, c: int) -> qs |
  Hadamard(qs[c])` is a parametric action. The new `parameters` field
  on `QActionSignature` exists for this.

Specs, error messages, and field names use these two words
consistently. The two concepts compose: a parametric action whose
effect contains a parameterized gate (`rotate | (qs, theta: angle) ->
qs | Rx(qs[0], theta)`) is supported.

## Risks / Trade-offs

- **Risk:** The H-sandwich lowering for `*Z` gates increases circuit
  depth by 2 per use. For deep oracles this matters under noise.
  **Mitigation:** acceptable for the demos in scope (4-qubit Grover,
  3-qubit polysemy) where depth is dominated by the diffusion. A
  future change can introduce a per-backend "native CCZ/MCZ" flag if
  noise demos need it.

- **Risk:** Identifier subscripts make per-action effect-string
  parsing context-dependent: `Hadamard(qs[c])` is well-formed inside
  a parametric action and ill-formed outside one. The parser has to
  thread the action's signature through the subscript check.
  **Mitigation:** the parser already threads context (the angle
  evaluator carries `angle_context`); the parameter list is the same
  shape of carrier. Add `signature_context` next to `angle_context` in
  the shared parser entrypoint.

- **Risk:** Per-call-site verification multiplies error counts when a
  template has a bug. A wrong-by-one subscript in a template invoked
  12 times produces 12 errors.
  **Mitigation:** intentional. The user wants to see that all 12 call
  sites broke (so they correctly fix the template once and re-verify),
  not a single error that hides which call sites compiled and which
  didn't. We accept the count inflation.

- **Risk:** The `_basis` gate list in the Qiskit script is hardcoded
  inside the emitter. If `BasicSimulator` adds new native gates we
  miss the chance to drop the transpile for them.
  **Mitigation:** the basis list is small, and adding a gate to the
  list is a one-line patch. Alternative would be to query the backend
  for its basis at script-generation time, but that requires importing
  Qiskit at compile time, not just at script-run time. We keep the
  hardcoded basis for now.

- **Risk:** Mermaid labels for parametric calls. The transition's
  display label is `event [guard] / action`; for a parametric call the
  intuitive display is `query_concept(3)`. The Mermaid emitter today
  reads `t.action` (a string).
  **Mitigation:** the parser stores the source-form Action cell text
  on `QTransition.action_label` (a new field) so Mermaid can render
  the call form verbatim; the resolved action name plus
  `bound_arguments` go on separate fields for the compiler.

## Migration Plan

This change is additive in two senses:

1. The multi-controlled gate work is already shipped. No migration is
   needed for in-tree examples — they either use the new gates
   (`larql-gate-knn-grover.q.orca.md`) or do not (everything else).
2. The parametric action work has no in-tree consumer at the moment of
   this proposal. A new example
   `examples/larql-polysemantic-12.q.orca.md` will land alongside the
   parser/compiler/verifier changes in the same PR sequence so the
   feature has end-to-end coverage from day one.

External users with their own `.q.orca.md` files: zero-parameter
signatures (`(qs) -> qs`) continue to parse identically, so existing
files do not need changes. The bare-name action reference in the
transitions table remains valid; the call form is opt-in per row.

Rollback: the multi-controlled gate work is a series of additive
patches behind no feature flag; rollback means reverting the four
modified files (`qiskit.py`, `qasm.py`, `quantum.py`, plus the example
and demo). The parametric action work is the natural rollback unit
when its tasks are sequenced as proposed.

## Open Questions

- Should the call form support keyword arguments
  (`query_concept(c=3)`) in addition to positional (`query_concept(3)`)?
  **Tentative answer**: positional only for v1; keyword as a separate
  follow-up if multi-parameter actions get common enough to make
  positional ordering error-prone.

- Should the spec require that parametric actions appear before any
  transition that calls them, or allow forward references? The current
  parser is single-pass over the markdown. **Tentative answer**: allow
  forward references; collect all action definitions first, then
  resolve transition references in a second pass. The parser already
  tolerates ordering for state references; matching that behavior is
  the principle of least surprise.

- Should `int` parameters carry a range constraint
  (`c: int(0, 3)` or `c: qubit_index`)? The verifier already raises
  `QUBIT_INDEX_OUT_OF_RANGE` post-expansion, so a declared range would
  be a parser-time check rather than a verifier-time check. **Tentative
  answer**: defer. The post-expansion error is structurally fine; range
  declarations add grammar complexity for marginal benefit.
