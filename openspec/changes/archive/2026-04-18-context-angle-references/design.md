## Context

Today the angle grammar in `q_orca/angle.py::evaluate_angle` accepts only
literals and `pi`-based forms. The parser, the Qiskit compiler's effect
parser, and the dynamic verifier's effect parser all delegate to it, and
all three reject bare identifiers. Authors of QAOA / VQE machines work
around this by hardcoding `pi/4`, `pi/8`, etc. in their action effects,
making the declared `gamma`, `beta`, `theta` context fields decorative
rather than functional.

The fix is small: `evaluate_angle` needs an optional context map, the
markdown parser needs to assemble that map and pass it down, and the
example files need to switch to the new form.

## Goals / Non-Goals

**Goals:**

- Let users write `Rx(qs[0], theta)` and have it resolve to the value of
  the `theta` context field's default.
- Support a small but useful set of compound forms: `-theta`, `2*theta`,
  `theta/2`, `theta*pi`, `pi*theta`. These cover Trotter steps and
  unit-conversion of normalized angles.
- Keep one canonical evaluator shared by parser, compiler, and dynamic
  verifier — preserving the spec invariant that the three sites parse
  identically.
- Produce a clear parser error when an identifier is used but the field
  is missing or has a non-numeric default.

**Non-Goals:**

- Full expression parsing (`gamma + pi/4`, `sin(theta)`, `theta**2`).
  Useful, but a real expression grammar is out of scope here. We pick a
  small extensible set and add a placeholder error for the rest.
- Runtime parameter binding. The default value in the context table is
  the only source of truth for the angle. Sweeping parameters at
  simulation time is a separate change.
- Symbolic-only AST representation. We resolve to a `float` at parse
  time so the rest of the pipeline (verifier, compiler) sees the same
  `QuantumGate.parameter` shape it sees today.

## Decisions

### Decision 1 — Resolve at parse time, not at compile time

Rotation gates already store `parameter: Optional[float]`. Resolving
identifiers at parse time means we don't need a new AST shape for
"symbolic angle." The trade-off is that authors can't change a rotation
angle without re-parsing, but Q-Orca is not currently a runtime DSL —
every backend already re-runs the pipeline from source.

Alternative considered: introduce `QuantumGate.parameter_expr: str` and
defer resolution to the compiler. Rejected because it duplicates state
(angle as both float and string), forces every backend to add a fallback
path, and gives no user-visible benefit until we have runtime parameter
binding.

### Decision 2 — Reuse `evaluate_angle` rather than introducing a new entry point

`evaluate_angle(text, context=None)` keeps backwards compatibility
(existing callers pass no context and behave identically) and means the
parser, Qiskit compiler, and dynamic verifier all migrate by passing the
same map.

Alternative considered: add `evaluate_angle_with_context`. Rejected
because three call sites would need updating regardless, and a single
function with an optional argument is simpler to reason about.

### Decision 3 — Compound grammar via small fixed set, not real parser

We add four explicit regexes for `-name`, `int*name`, `name/int`,
`name*pi` / `pi*name`. This keeps the implementation under ~30 lines
and matches what the literal grammar already does (a flat fallthrough
of regex cases).

Alternative considered: switch to `ast.parse(...)` with a whitelist of
node types. Rejected because (a) the literal grammar deliberately
rejects e.g. `pi*pi` today and switching to a real parser would either
loosen that or require complex validation, (b) the compound forms we
need for QAOA / VQE all fit the small fixed set, (c) a real expression
grammar is a bigger feature deserving its own change.

### Decision 4 — Build context map only from numeric defaults

We collect `{field.name: float(field.default_value)}` for every context
field whose `type.kind in {"float", "int"}` and whose default parses as
a number. Fields without defaults (`int outcome` with no default) and
non-numeric fields (`list<qubit>`, `noise_model`) are excluded. This
keeps the resolution rule precise: an identifier is only valid if its
field has a value the gate could have used directly.

### Decision 5 — Thread context through the action-table parser

`_parse_actions_table` currently takes `(table, errors)`. We extend it
to `(table, errors, angle_context)`. `_parse_machine_chunk` builds the
map from already-parsed context fields before calling the actions
parser. The Qiskit compiler and dynamic verifier build the same map
from `machine.context` when they invoke their own effect parsers.

## Risks / Trade-offs

- **Risk:** A user declares `theta` as `int` with default `1` expecting
  it to mean "1 radian," then is surprised it isn't `pi`.
  **Mitigation:** documentation. The angle is taken as-is; no implicit
  `*pi` happens unless written.

- **Risk:** Fields named `pi` shadow the literal `pi` form.
  **Mitigation:** `pi` is treated as a literal first; context lookup
  only happens when the literal pass fails. A field literally named
  `pi` is silently shadowed (this is fine — users can rename).

- **Risk:** Compound grammar diverges from what users expect.
  **Mitigation:** the error message lists the accepted compound forms
  explicitly. Future expression-grammar work is unblocked because the
  regex fallthrough makes adding a new form a one-liner.

- **Risk:** The Qiskit compiler and dynamic verifier currently have
  their own effect-string parsers. If we miss one, behaviour diverges.
  **Mitigation:** the spec already requires the three sites to share
  `evaluate_angle`; we audit each in tasks.md and add a regression test
  that compiles and dynamically simulates the same machine, asserting
  they agree.

## Open Questions

None for v1. A follow-up change can add a real expression grammar once
we have a use case for `gamma + pi/4` style expressions.
