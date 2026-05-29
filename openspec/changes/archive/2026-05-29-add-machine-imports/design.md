## Context

`add-parameterized-invoke` (merged) added `invoke: Child(...)` and a composition
verifier (`q_orca/verifier/composition.py`) that resolves the child against
`{m.name: m for m in file.machines}` — same-file only. Multi-machine files are
produced by `_split_by_separator` on `---` boundaries. The parser
(`parse_q_orca_markdown`) is the single entry point producing a `QOrcaFile`.
There is no notion of a project root, no file loader beyond the caller reading a
string, and no caching. This change adds the one missing resolution source —
other files — without disturbing the same-file fast path.

## Goals / Non-Goals

**Goals:**

- Resolve `invoke: Child(...)` against machines in other files, declared via an
  explicit `## imports` table, with optional aliasing.
- A small re-export form so a curated index file can collect primitives.
- Deterministic resolution order and clear diagnostics for the failure modes
  authors will actually hit (not found, cycle, ambiguous, typo).
- Parse each imported file exactly once per resolution; detect cycles.
- No change to single-file behavior (absent `## imports` → today's behavior).

**Non-Goals:**

- **Runtime execution** of composed/imported machines — orthogonal, parked as
  `add-composed-runtime`.
- **Glob imports** (`./lib/*.q.orca.md`), **hash/content pinning**, and **LSP /
  goto-definition** — all deferred.
- A new config file. Project root is discovered, not declared.

## Decisions

### Decision 1: Parser records imports; a separate resolver loads files

The parser stays pure (string → AST) and filesystem-free: it parses the
`## imports` / `## reexports` tables into `QImport` / `QReexport` nodes on the
file def and validates only table *shape*. A new
`q_orca/loader/import_resolver.py` owns all disk I/O and graph walking. This
keeps `parse_q_orca_markdown` testable without a filesystem and confines path
resolution, memoisation, and cycle detection to one module.

**Alternative considered:** parser loads imports inline. Rejected — it would
make the parser stateful, filesystem-coupled, and hard to unit-test, and would
duplicate cycle/memo logic that belongs in one place.

### Decision 2: AST placement — file-level, not machine-level

Imports are a property of the *file*, not any single machine. But the current
AST has no file-level node carrying sections — `QOrcaFile` is just
`machines: list[QMachineDef]`. Rather than introduce a heavier
`QMachineFileDef`, attach `imports: list[QImport]` and `reexports:
list[QReexport]` to `QOrcaFile`. The parser already assembles `QOrcaFile`; the
`## imports` / `## reexports` sections live in the *first* chunk (before the
first `## machine`/`# machine` heading) and are parsed at the file level.

**Alternative considered:** per-machine imports. Rejected — imports scope to the
file (every machine in a file shares the import set), matching how Q# scopes a
namespace per file.

### Decision 3: Resolution order and ambiguity

For an `invoke: Child`, the verifier consults, in order: (1) same-file
`## machine` blocks, (2) `## imports` aliases binding `Child`, (3)
`## reexports` reachable through the import graph. A name resolvable from more
than one *distinct* source is `AMBIGUOUS_CHILD_MACHINE` — except a same-file
machine always wins over an import (local shadowing is intentional and common),
so ambiguity is only flagged among non-local sources, or when an import alias
collides with another import alias for a different file.

**Alternative considered:** first-source-wins silently. Rejected — silent
shadowing across files is the kind of bug imports are supposed to prevent.

### Decision 4: Path resolution — relative and project-relative only

`./` and `../` resolve against the importing file's directory. `q_orca:foo/bar`
resolves against the project root, discovered by walking up from the importing
file to the nearest directory containing `pyproject.toml` (falling back to the
cwd if none is found). Absolute paths are rejected (`IMPORT_NOT_FOUND` with a
"absolute paths are not permitted" message) — they make specs non-portable.

**Alternative considered:** an explicit `q_orca.toml` project marker (Q#-style
`qsharp.json`). Deferred — `pyproject.toml` already exists in this repo and
needs no new file; the resolver isolates discovery so a marker can be added
later without touching call sites.

### Decision 5: BFS with memoisation and an in-flight set

`resolve_imports(file_def, base_path, project_root)` walks imports
breadth-first. Each absolute path is parsed once and cached; an in-flight set
detects cycles (`IMPORT_CYCLE`, reported as a path list). Re-export chains are
followed transitively but capped at 4 hops (`IMPORT_CHAIN_TOO_DEEP`) so error
messages stay debuggable. The resolver returns a `ResolvedImportGraph` exposing
`lookup_machine(alias)` and the set of all known aliases (for edit-distance
suggestions).

### Decision 6: Diagnostics live in the verifier, resolution in the loader

The resolver raises typed errors / returns structured results; the composition
verifier translates them into `QVerificationError`s with the existing severity
convention, so the diagnostic surface stays in one place. `UNRESOLVED_CHILD_
MACHINE` gains a suggestion list ranked by Levenshtein distance over the union
of same-file machine names and import-graph aliases. `--no-follow-imports`
makes the verifier skip the resolver entirely and treat every non-local invoke
as unresolved (with a hint that the flag is active) — useful for verifying a
file in isolation.

## Risks / Trade-offs

- **[Risk] Filesystem access from the verifier.** Resolution reads arbitrary
  relative paths off disk. → Mitigation: absolute paths rejected; `q_orca:` is
  confined to under the discovered project root; the CLI flag
  `--no-follow-imports` disables disk access entirely.
- **[Risk] A malformed imported file's parse errors are confusing out of
  context.** → Mitigation: `IMPORT_PARSE_FAILED` re-prefixes the delegated parse
  error with the import chain that reached it.
- **[Risk] Project-root discovery via `pyproject.toml` is implicit.** → A repo
  with no `pyproject.toml` falls back to cwd; documented, and isolated in the
  resolver so an explicit marker can replace it later.
- **[Trade-off] No caching across `verify` invocations.** Each top-level verify
  re-parses imported files. Acceptable — the parser is fast and the import graphs
  are small; cross-invocation caching is a future optimisation.

## Migration Plan

Additive. Files with no `## imports` section parse and verify exactly as before.
Rollback is reverting the commits; files using the new sections then fail to
parse, the expected rollback signal.

## Open Questions

1. **Project root marker.** `pyproject.toml`-walk vs. an explicit `q_orca.toml`.
   Defaulting to `pyproject.toml`-walk for v1; the resolver isolates discovery.
2. **Import a file vs. a named machine.** v1 imports a file and aliases named
   machines from it (Python `from x import Foo` shape). A per-machine
   `import Foo from ./x` form is a possible future ergonomic addition.
