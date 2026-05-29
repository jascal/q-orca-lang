# Spec: Cross-File Machine Imports — `## imports` Section

**Status:** In flight — implemented under
`openspec/changes/add-machine-imports/`. Resolver lives at
`q_orca/loader/import_resolver.py`; the composition verifier consults it for
`invoke:` fall-through.
**Date:** 2026-05-15
**Priority:** High

> Generated: 2026-05-15 — weekly feature spec session

---

## Summary

Add a top-level `## imports` section to `.q.orca.md` files that
resolves child machines from other files on disk by relative or
project-relative path, optionally aliased into the importing
file's namespace. The in-flight `add-parameterized-invoke`
proposal introduces the `invoke: Child(...)` state annotation but
explicitly resolves child machines only within the same
multi-machine file; cross-file imports are parked as the
follow-up `add-machine-imports`. This change defines that
follow-up. Once shipped, a single `.q.orca.md` can declare a
`prepare_bell_pair`, a `qft_inverse_3`, or a
`grover_diffuser_n=4` machine once and have every example, demo,
and parent training-loop machine pull it in by import. Without
imports, every multi-machine workflow must inline every
sub-machine, which collapses the multi-machine composition story
back into "one giant file" the moment it leaves the toy stage.

---

## Motivation

**The user problem.** The `add-parameterized-invoke` change
(in-flight) gives q-orca an AST-level concept of a *child
machine*: a parent state can carry an `invoke: Child(arg=value,
…)` annotation, the child runs (classically run-to-completion or
quantum shot-batched), and typed return values flow back into the
parent's context. The verifier resolves `Child` to a sibling
`## machine` block in the same `.q.orca.md` file — and only the
same file. The proposal's "Scope boundary" section spells this
out:

> Cross-file imports of child machines from external
> `.q.orca.md` files (v1 resolves children only within the same
> multi-machine file; cross-file imports parked as
> `add-machine-imports`)

The shape this leaves the user in is the textbook "every program
is one file" problem from early-1970s scripting languages. The
moment a workflow has more than two child machines, the parent
file has to inline every child verbatim. The Quantum Predictive
Coder spec
(`docs/research/spec-quantum-predictive-coder.md`) names a
parent training loop with at least three child machines (forward
pass, gradient estimator, parameter update); the QKD
eavesdropping demo
(`openspec/roadmap/coverage-analysis-v0.4.md` §3.1) names three
parties (Alice, Bob, Eve) each defined as a separate machine.
Both workflows are unbuildable as single files past the
prototype stage.

**The current workaround.** Authors copy-paste sub-machine
definitions between files, or maintain a hand-written Python
shim that string-concatenates `.q.orca.md` fragments before
parsing. Both are fragile: copy-paste drifts, shims hide the
import graph from the verifier, and neither path lets the parser
report `UNRESOLVED_CHILD_MACHINE` with a useful "did you mean…?"
hint sourced from the actual import set.

**Why now.** Three forces converge in this release window:

- `add-parameterized-invoke` is in-flight and lands the AST
  concept of a child machine reference. Without imports it is
  marooned at the single-file boundary.
- Multiple drafted specs assume a library of reusable
  primitives. Protocol state annotations
  (`spec-protocol-state-annotations.md` §Cross-machine) wants
  paired Alice/Bob machines; `spec-quantum-predictive-coder.md`
  wants a forward-pass child reused across training iterations;
  the QKD demo
  (`openspec/roadmap/coverage-analysis-v0.4.md` §3.1) wants
  three machines composed.
- The `q_orca/parser/markdown_parser.py` parser already handles
  multi-machine files (one `## machine` block resolves another
  by name) and the new
  `q_orca/verifier/composition.py` from
  `add-parameterized-invoke` already has the resolution
  surface — imports adds *one more place to look* before
  declaring a child unresolved.

**KB grounding.** Q# treats every `.qs` file as a namespace and
resolves `import MyTeleportLib.Teleport` against an explicit
project file (Microsoft Quantum docs,
`how-to-work-with-qsharp-projects`). OpenQASM 3 has an `include
"stdgates.inc"` directive and the Qiskit `qasm3.load(file_name)`
loader. Both languages settled on the "one file = one namespace,
explicit import" pattern after early "everything in one file"
attempts; q-orca should not re-derive this lesson.

---

## Proposed Syntax / API

### `## imports` section

A new optional top-level section, recognised between `## context`
and the first `## machine` block:

```markdown
## imports

| Path                                  | Aliases                              |
|---------------------------------------|--------------------------------------|
| ./lib/bell-pair.q.orca.md             | PrepareBellPair                      |
| ./lib/qft.q.orca.md                   | QFTInverse                           |
| ../shared/grover-diffuser.q.orca.md   | GroverDiffuser, Diffuser             |
```

Semantics:

- **Path** — relative to the importing file (`./`, `../`
  permitted) or project-relative (`q_orca:lib/...`,
  resolved against the project's `pyproject.toml` directory if
  one is found, otherwise the cwd). Absolute paths are rejected.
- **Aliases** — comma-separated list of names to bind. Each
  alias must match a `## machine: <name>` heading in the
  imported file. The same machine may be aliased twice (`Diffuser`
  in the row above is a shorthand for `GroverDiffuser`).
- Multiple `## imports` rows may target the same file with
  disjoint alias sets.
- Section is **optional**; absence yields the current behavior
  (children resolve only against same-file `## machine` blocks).

### Re-exports

A pure re-export form lets a curated `lib/index.q.orca.md` file
collect primitives from many files into one alias namespace:

```markdown
## imports

| Path                              | Aliases                              |
|-----------------------------------|--------------------------------------|
| ./bell-pair.q.orca.md             | PrepareBellPair                      |
| ./qft.q.orca.md                   | QFT, QFTInverse                      |

## reexports

| Alias            | From                |
|------------------|---------------------|
| PrepareBellPair  | (this file)         |
| QFT              | (this file)         |
| QFTInverse       | (this file)         |
```

A consumer can then `./lib/index.q.orca.md` once and pull all
three primitives. Re-exports are resolved transitively but not
recursively — a re-export chain longer than 4 hops is rejected
as `IMPORT_CHAIN_TOO_DEEP` to keep error messages debuggable.

### Resolution order in `invoke:`

When the verifier resolves `invoke: Child(...)` it consults, in
order:

1. Same-file `## machine: Child` blocks (current
   `add-parameterized-invoke` behavior).
2. `## imports` aliases binding the name `Child`.
3. `## reexports` from any imported file that re-exports
   `Child`.

A name appearing in more than one source is rejected as
`AMBIGUOUS_CHILD_MACHINE` with the conflicting source paths.

### CLI

`q-orca verify ./parent.q.orca.md` follows imports automatically.
A new `--no-follow-imports` flag short-circuits resolution at the
file boundary and reports `UNRESOLVED_CHILD_MACHINE` for any
non-local reference, useful when verifying a file in isolation
during editor refactors. A new `q-orca imports show
./parent.q.orca.md` prints the transitively-closed import graph
as a Mermaid diagram suitable for embedding in docs.

---

## Implementation Sketch

**Parser** — `q_orca/parser/markdown_parser.py`:

- Recognise `## imports` and `## reexports` headings, parse the
  pipe-delimited tables. New AST nodes `QImport(path: str,
  aliases: list[str])` and `QReexport(alias: str, source:
  str)` on `QMachineFileDef`. ~80 LOC plus tests.
- The parser **does not** load imported files itself — that is
  the resolver's job. The parser only validates the table shape
  and records the unresolved import list.

**Resolver** — new module `q_orca/loader/import_resolver.py`:

- `resolve_imports(file_def, project_root)` walks the import
  graph breadth-first. Each new file is parsed exactly once
  (memoised by absolute path), with an in-flight set used to
  detect cycles. Returns a `ResolvedImportGraph` exposing
  `lookup_machine(alias) -> QMachineDef`.
- Cycle detection: if a file imports (transitively) one of its
  ancestors, raise `IMPORT_CYCLE` with the cycle as a path
  list. Cycles are not recoverable; the verifier refuses to run
  on a cyclic graph.
- ~200 LOC plus tests.

**Verifier** — `q_orca/verifier/composition.py` (new in
`add-parameterized-invoke`):

- After resolving same-file `## machine` blocks for an
  `invoke:`, fall through to `ResolvedImportGraph.lookup_machine`.
- New diagnostic codes: `UNRESOLVED_CHILD_MACHINE` (extended
  message lists all import-graph aliases as suggestions
  ranked by edit distance), `AMBIGUOUS_CHILD_MACHINE`,
  `IMPORT_CYCLE`, `IMPORT_NOT_FOUND` (path doesn't resolve to a
  file), `IMPORT_PARSE_FAILED` (delegated parse error,
  re-prefixed with the import chain), `IMPORT_CHAIN_TOO_DEEP`.
- ~80 LOC plus tests.

**Compiler** — `q_orca/compiler/mermaid.py`:

- Imported child machines render as a distinct subgraph node
  with the import path as a tooltip. Same as `add-parameterized-
  invoke` rendering, but with a small import-arrow glyph.
- ~30 LOC.

**CLI** — `q_orca/cli/__init__.py`:

- `--no-follow-imports` flag plumbed through `verify`.
- New `q-orca imports show <file>` subcommand emits the import
  graph as Mermaid.
- ~60 LOC plus tests.

**Specs** — `openspec/specs/language/spec.md`,
`openspec/specs/verifier/spec.md`,
`openspec/specs/compiler/spec.md` get delta sections.

**Total estimate:** ~450 LOC of code + ~400 LOC of tests. One
new file (`import_resolver.py`), modifications to ~5 existing
files.

---

## Test Cases

1. **Happy path** — parent imports `./lib/bell-pair.q.orca.md`,
   aliases the contained `PrepareBellPair` machine, invokes it
   from a state, verifier resolves and type-checks the
   arg/return bindings end-to-end.

2. **Project-relative resolution** — parent imports
   `q_orca:examples/bell-entangler.q.orca.md`, the loader
   correctly walks up to find `pyproject.toml` and resolves
   the path against the project root rather than cwd.

3. **Cycle detection** — file A imports B, B imports A. Verifier
   reports `IMPORT_CYCLE` with the cycle as `[A → B → A]`.

4. **Ambiguous child** — file A defines local `## machine:
   Child` and also imports a `Child` alias from file B. Verifier
   reports `AMBIGUOUS_CHILD_MACHINE` naming both source
   locations and suggests renaming the import alias.

5. **Re-export chain depth** — a chain `A → B → C → D → E → F`
   re-exporting the same machine each hop fails at hop 5 with
   `IMPORT_CHAIN_TOO_DEEP` and prints the chain.

6. **`--no-follow-imports` flag** — verifier reports the same
   unresolved-child error for every non-local invoke even when
   the imports table is well-formed, with a hint that the flag
   is active.

7. **Edit-distance suggestions** — `invoke: Diffser(...)` (typo)
   resolves nothing locally; the error message lists
   `Diffuser, Disperser, Defuser` from the import graph in
   distance order.

---

## Dependencies

**Sequenced after** `add-parameterized-invoke` (in-flight):
this change extends that proposal's resolver. The
`add-parameterized-invoke` proposal's "Scope boundary" section
already names this work as the deferred follow-up
`add-machine-imports`.

**Composes with:**

- `spec-protocol-state-annotations.md` (drafted) — the paired
  `[send: q -> Bob]` / `[receive: q <- Alice]` cross-machine
  consistency check assumes Alice and Bob can live in
  separate files; this change makes that physical separation
  expressible.
- `spec-quantum-predictive-coder.md` (drafted) — the QPC
  parent training loop wants to import a `forward_pass` child
  from a separate file so the same forward pass can be reused
  across QPC variants.

**Does not block:** the runtime-execution follow-up
`add-composed-runtime` (separately parked in `add-parameterized-
invoke`'s scope boundary) is orthogonal — imports affect static
resolution only.

---

## Open Questions

1. **Project root discovery.** Walking up to find
   `pyproject.toml` is one choice; an explicit `q_orca.toml` at
   the project root (with an `[imports] root = "..."` key)
   would be more robust but adds a config file. Q# uses an
   explicit `qsharp.json`; OpenQASM has no notion of a project.
   Which convention fits better?

2. **Import a *file* vs. import a *named machine*.** The
   proposed grammar imports the file and aliases all named
   machines from it. An alternative — `import Foo from
   ./lib/x.q.orca.md` — names the machine at the import site.
   The latter is more verbose but catches typos earlier; the
   former is more like Python's `from x import Foo`.

3. **Glob imports** (`./lib/*.q.orca.md`) — easy to specify,
   easy to abuse. Probably reject for v1 and revisit if a real
   library wants them.

4. **Versioning / hash pinning.** Long-term, an imported file
   should be content-pinned so a stale cached parse cannot
   sneak a behavior change in. Out of scope for v1 (the parser
   has no caching today), but the spec should note that the
   import row may grow a third column `Hash` later.

5. **Editor / language-server integration.** Goto-definition
   on `invoke: Child` should jump into the imported file. The
   current MCP `parse_skill` tool would need to expose the
   resolved import graph; LSP integration is out of scope for
   v1 but the resolver API should be designed so an LSP can
   layer on top.
