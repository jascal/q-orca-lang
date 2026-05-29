## 1. AST

- [x] 1.1 Add `QImport(path: str, aliases: list[str])` and
  `QReexport(alias: str, source: str)` dataclasses to `q_orca/ast.py`.
- [x] 1.2 Add `imports: list[QImport] = []` and
  `reexports: list[QReexport] = []` fields to `QOrcaFile`.

## 2. Parser

- [x] 2.1 Recognise a top-level `## imports` section and parse its
  `Path | Aliases` table into `QImport` nodes. Reject absolute paths
  (`import_absolute_path`).
  Parsed at the file level (`_parse_file_imports`), position-independent, so the
  machine-chunk parser leaves the heading untouched.
- [x] 2.2 Recognise a top-level `## reexports` section and parse its
  `Alias | From` table into `QReexport` nodes.
- [x] 2.3 Attach parsed imports/reexports to `QOrcaFile` (file-level). The
  parser does NOT load any imported file.
- [x] 2.4 Unit tests: relative + multi-alias rows, absent section,
  absolute-path rejection, reexport rows. Covered by `tests/test_import_resolver.py`
  (which parses these fixtures end-to-end); dedicated `test_parser.py` cases TODO.

## 3. Resolver

- [x] 3.1 Create `q_orca/loader/import_resolver.py` with
  `resolve_imports(file_def, base_path, project_root) -> ResolvedImportGraph`.
  DFS over the import graph with a path-stack for cycle detection; each file
  parsed once (memoised by absolute path).
- [x] 3.2 Project-root discovery (`find_project_root`): walk up to the nearest
  `pyproject.toml`, else cwd. `q_orca:` paths resolve against it; `./`/`../`
  against the importing file's directory.
- [x] 3.3 `lookup_machine`, `known_aliases`, `is_ambiguous`; re-exports followed
  transitively, capped at 4 hops.
- [x] 3.4 Structured `ImportDiagnostic`s: `IMPORT_NOT_FOUND`,
  `IMPORT_PARSE_FAILED` (chain-prefixed), `IMPORT_CYCLE` (path), `IMPORT_CHAIN_TOO_DEEP`.
- [x] 3.5 `tests/test_import_resolver.py`: happy, project-relative, cycle,
  missing file, reexport-via-index, chain-too-deep (6 tests).

## 4. Verifier — composition fall-through

- [x] 4.1 `check_composition` consults `import_graph` after same-file resolution;
  same-file machine shadows imports.
- [x] 4.2 `AMBIGUOUS_CHILD_MACHINE` when a name resolves from ≥2 distinct
  sources, naming the source paths.
- [x] 4.3 `UNRESOLVED_CHILD_MACHINE` extended with `difflib`-based "did you
  mean…?" suggestions over same-file names + import-graph aliases.
- [x] 4.4 Resolver `IMPORT_*` diagnostics merged into the result once.
- [x] 4.5 `--no-follow-imports`: the CLI/skill layer simply passes
  `import_graph=None`, so every non-local invoke is unresolved. (CLI flag itself
  is §6.1.)
- [x] 4.6 `tests/test_verifier.py::TestCompositionImports`: imported resolution,
  edit-distance suggestion, no-follow (3 tests).

## 5. Compiler — Mermaid

- [ ] 5.1 In `q_orca/compiler/mermaid.py`, render an imported child as a nested
  composite block carrying its import path (resolved via the import graph).
- [ ] 5.2 Add an import-graph view helper that renders the transitive import
  closure as a Mermaid diagram of files + import edges (used by `imports show`).
- [ ] 5.3 Unit tests in `tests/test_compiler.py`.

## 6. CLI

- [ ] 6.1 Add `--no-follow-imports` to `q-orca verify`, plumbed into
  `VerifyOptions` and the resolver dispatch; pass the surrounding file/base path.
- [ ] 6.2 Add a `q-orca imports show <file>` subcommand emitting the import-graph
  Mermaid view.
- [ ] 6.3 Wire `verify_skill` / CLI verify to resolve imports (build the
  `ResolvedImportGraph` from the parsed file + its path) and pass it to the
  composition stage.

## 7. End-to-end + docs

- [ ] 7.1 Fixture: a `lib/` primitive file + a parent that imports and invokes
  it; confirm parse + verify + Mermaid render end-to-end (`tests/test_machine_imports.py`).
- [ ] 7.2 Run the full suite and `q-orca verify --strict` on all examples; no
  regressions.
- [ ] 7.3 Update `docs/research/spec-machine-imports.md` status header to
  in-flight and link to this change.

## 8. Spec sync

- [ ] 8.1 At archive time, sync the three delta specs into
  `openspec/specs/{language,verifier,compiler}/spec.md`.
