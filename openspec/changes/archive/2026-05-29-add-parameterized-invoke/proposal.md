## Why

Q-Orca machines today are *closed systems*: a machine defines its
own context, runs from initial to final, and has no way to delegate
work to another machine or be invoked by one. The classical orca
tool (the sibling project) already has `invoke: ChildMachine` for
sub-machine delegation, but the calling convention is limited —
it takes no arguments and the child's context is distinct from the
parent's. This means even classical orca→orca composition has a
"glue in Python" problem, and orca→q-orca composition has no
expressible form at all.

The Quantum Predictive Coder research
(`docs/research/spec-quantum-predictive-coder.md`) makes the need
concrete: a training loop is naturally a classical orca machine
(epoch counter, convergence check, parameter schedule) that
repeatedly dispatches a *per-iteration forward pass* to a q-orca
child machine, then reads back the measurement outcomes and
updates its own context. Without parameterized invocation +
declared returns, this workflow has to live in hand-written
Python glue, and the state-machine semantics can't verify or
document the composition.

Two complementary primitives have been scoped over recent
changes:
- `add-classical-context-updates` (merged, planning-only) — the
  quantum→classical bridge: mutate numeric context fields from
  measured bits.
- **This change** — the classical→quantum bridge AND the general
  machine-to-machine calling convention: parameterized invoke,
  typed returns, execution-mode flag (synchronous run-to-completion
  vs shot-batched), statistical-kind annotations for aggregate
  returns.

Together they close the loop: a parent machine can pass
parameters *into* a child, run the child (classically in-sequence
or quantum-by-shots), and receive typed values *back*. No more
Python glue between state machines.

This is planning-only. No code in this PR — the deliverable is
proposal + design + delta specs + tasks. Implementation follows
the same per-task cadence as earlier changes.

## What Changes

- **Language**: introduce a new state annotation `invoke: Child(...)`
  that marks a state as *delegating* to another machine. Parent
  machine declares positional or keyword arguments binding parent
  context fields to child argument names. On child completion,
  return values flow back into the parent's context via a parallel
  `returns:` binding.
- **Language**: introduce a new top-level section `## returns` that a
  machine uses to declare what it returns to its caller. Each
  return row has `Name`, `Type`, and — for quantum machines only —
  an optional `Statistics` column carrying one or more of
  `expectation`, `histogram`, `variance` annotations. Under
  `shots=N` execution mode, the named statistics appear as extra
  typed fields in the parent (e.g., a return `bits[0]: bit
  <expectation, histogram>` produces `prob_bits_0: float` and
  `hist_bits_0: dict[int, int]` in the parent context).
- **Language**: execution-mode flag on invoke — `invoke: Child(...)
  shots=1024`. Required for q-orca children whose work is
  intrinsically stochastic (measurement-bearing); forbidden for
  classical children (parse error). If omitted on a q-orca child,
  defaults to `shots=1` (single-shot run-to-completion).
- **AST**: new `QInvoke` dataclass on `QStateDef` capturing child
  machine reference, arg bindings, return bindings, and
  shot count. New `QReturnDef` dataclass for the `## returns`
  table. New `QMachineDef.returns: list[QReturnDef]`.
- **Parser**: extend state heading parsing to accept
  `invoke: ChildName(...)` as a state-body annotation. Extend
  `## returns` section parsing. Handle the `<expectation,
  histogram, ...>` statistics annotations in return-type cells.
- **Verifier**: new composition-verifier stage that, for each
  `invoke:`, (a) resolves the child machine (in the same
  multi-machine file, or reports `UNRESOLVED_CHILD_MACHINE`),
  (b) type-checks arg bindings against child's context field
  types, (c) type-checks return bindings against child's
  `## returns` declarations, (d) enforces the shots-flag rules
  (required/forbidden/default), (e) for quantum children in
  shot-batched mode, resolves statistical-kind annotations and
  emits the aggregate field names into the parent's expected
  context. Errors bubble up with a `child-name.state.event` path
  prefix.
- **Compiler**: QASM and Qiskit backends SHALL refuse to compile a
  multi-machine invoke graph in v1 (emit a structured error asking
  the user to compile child machines individually and compose via
  the Python runtime). Mermaid rendering SHALL show invoke states
  as a distinct node kind with an arrow to the child's
  subdiagram. The runtime-level dispatching (how a Python harness
  actually walks a composed machine) is **out of scope for this
  change** and is parked as `add-composed-runtime`.
- **Docs**: `docs/research/spec-quantum-predictive-coder.md` gets a
  one-line back-reference to this change (alongside the existing
  back-reference to `add-classical-context-updates`), noting that
  the full composed QPC requires both primitives plus the runtime
  follow-up.

## Capabilities

### New Capabilities
None. This is a language/AST/verifier extension on existing
capabilities.

### Modified Capabilities

- **`language`**: three new requirements — `invoke:` state
  annotation, `## returns` section, and statistics annotations on
  quantum return types.
- **`verifier`**: new requirement covering multi-machine
  composition checks (resolution, arg/return typing, shots-flag
  rules). No change to existing requirements.
- **`compiler`**: one new requirement — multi-machine-aware Mermaid
  rendering + structured refusal in QASM/Qiskit backends until the
  composed-runtime change lands.

## Impact

- `q_orca/ast.py` — add `QInvoke`, `QReturnDef`, extend `QStateDef`
  and `QMachineDef`. ~40 LOC.
- `q_orca/parser/markdown_parser.py` — parse the `invoke:`
  state-body line (grammar detailed in design), parse `## returns`,
  parse the `<expectation, histogram>` annotation syntax. ~100 LOC
  + tests.
- `q_orca/verifier/` — new file `composition.py` with the
  composition checks. Wire into the pipeline after classical-context
  (from `add-classical-context-updates`) and before quantum-static.
  ~150 LOC + tests.
- `q_orca/compiler/mermaid.py` — render invoke states distinctly.
  ~20 LOC + tests.
- `q_orca/compiler/qasm.py`, `q_orca/compiler/qiskit.py` —
  structured refusal on multi-machine input. ~10 LOC each.
- `openspec/specs/language/spec.md`,
  `openspec/specs/verifier/spec.md`,
  `openspec/specs/compiler/spec.md` — delta specs.
- `tests/test_parser.py`, `tests/test_verifier.py`,
  `tests/test_compiler.py` — new coverage. ~400 LOC of test code.
- `docs/research/spec-quantum-predictive-coder.md` — one-line
  back-reference.
- **No new runtime dependencies.** The composed runtime is out of
  scope and will ship as `add-composed-runtime` once this change's
  grammar and verifier contract are settled.

## Scope boundary

In scope:
- Grammar for parameterized invoke + typed returns
- AST + parser for the new syntax
- Verifier checks for composition correctness
- Mermaid rendering of composed machines
- Structured QASM/Qiskit refusal (until runtime lands)

Explicitly **out of scope**:
- Actual runtime execution of composed machines (parked:
  `add-composed-runtime`)
- Classical-orca adopting this protocol on its side (requires work
  in the orca repo; this change defines the protocol that orca can
  implement against)
- Aggregate statistics beyond `expectation`, `histogram`,
  `variance` (can extend the annotation vocabulary later)
- Cross-file imports of child machines from external `.q.orca.md`
  files (v1 resolves children only within the same multi-machine
  file; cross-file imports parked as `add-machine-imports`)
