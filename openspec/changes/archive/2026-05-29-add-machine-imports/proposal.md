## Why

`add-parameterized-invoke` gave q-orca an AST-level *child machine* concept, but
the composition verifier resolves `invoke: Child(...)` only against `## machine`
blocks in the *same file*. The moment a workflow has more than two child
machines (the Quantum Predictive Coder names three; the QKD demo names Alice /
Bob / Eve) every sub-machine must be inlined verbatim — the "every program is
one file" problem. Cross-file imports let a primitive be defined once and pulled
in by reference, which is the missing piece that makes multi-machine composition
usable past the prototype stage.

## What Changes

- **Language**: a new optional top-level `## imports` section (table:
  `Path | Aliases`) that binds machines from other `.q.orca.md` files into the
  importing file's namespace, and an optional `## reexports` section (table:
  `Alias | From`) so a curated index file can collect primitives. Paths are
  relative (`./`, `../`) or project-relative (`q_orca:...`, resolved against the
  nearest `pyproject.toml`); absolute paths are rejected. New AST nodes
  `QImport(path, aliases)` and `QReexport(alias, source)`.
- **Resolver**: a new `q_orca/loader/import_resolver.py` that walks the import
  graph breadth-first, parses each file once (memoised by absolute path),
  detects cycles, and exposes `lookup_machine(alias) -> QMachineDef`. Re-exports
  resolve transitively but a chain longer than 4 hops is rejected.
- **Verifier**: the composition stage resolves `invoke:` in order — same-file
  machine → import alias → re-export — and falls through to the resolved import
  graph. New diagnostics `AMBIGUOUS_CHILD_MACHINE`, `IMPORT_CYCLE`,
  `IMPORT_NOT_FOUND`, `IMPORT_PARSE_FAILED`, `IMPORT_CHAIN_TOO_DEEP`;
  `UNRESOLVED_CHILD_MACHINE` is extended with edit-distance "did you mean…?"
  suggestions sourced from the import graph.
- **Compiler**: Mermaid renders an imported child as a distinct node carrying
  its import path.
- **CLI**: `q-orca verify` follows imports automatically; a new
  `--no-follow-imports` flag short-circuits resolution at the file boundary; a
  new `q-orca imports show <file>` prints the transitively-closed import graph
  as Mermaid.
- **Out of scope (v1)**: glob imports (`./lib/*`), content/hash pinning, and
  LSP/goto-definition integration — all rejected for now.

## Capabilities

### New Capabilities

None. Imports extend the existing language, verifier, and compiler capabilities;
no new standalone capability is introduced.

### Modified Capabilities

- `language`: new `## imports` and `## reexports` sections, `QImport` /
  `QReexport` AST nodes, and the path grammar (relative / project-relative,
  absolute rejected).
- `verifier`: composition resolution order extended to consult the import graph;
  new import/ambiguity/cycle diagnostics and edit-distance suggestions on
  unresolved children.
- `compiler`: Mermaid renders imported child machines with their import path.

## Impact

- **Code**: new `q_orca/loader/import_resolver.py` (~200 LOC); parser additions
  in `q_orca/parser/markdown_parser.py` (~80 LOC); composition-stage fall-through
  in `q_orca/verifier/composition.py` (~80 LOC); Mermaid (~30 LOC); CLI
  (`--no-follow-imports` + `imports show`, ~60 LOC). New AST nodes in
  `q_orca/ast.py`.
- **Tests**: happy path, project-relative resolution, cycle detection, ambiguous
  child, re-export chain depth, `--no-follow-imports`, edit-distance suggestions.
- **Dependencies**: none new — pure-Python path resolution and BFS.
- **Sequenced after** `add-parameterized-invoke` (merged); extends its resolver.
- **Composes with** the drafted protocol-state-annotations and quantum-
  predictive-coder specs (both want machines in separate files). **Does not
  block** `add-composed-runtime` (runtime execution is orthogonal to static
  import resolution).
