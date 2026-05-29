## 1. AST

- [ ] 1.1 Add `QImport(path: str, aliases: list[str])` and
  `QReexport(alias: str, source: str)` dataclasses to `q_orca/ast.py`.
- [ ] 1.2 Add `imports: list[QImport] = []` and
  `reexports: list[QReexport] = []` fields to `QOrcaFile`.

## 2. Parser

- [ ] 2.1 Recognise a top-level `## imports` section (in the first chunk,
  before the first machine) and parse its `Path | Aliases` table into
  `QImport` nodes. Reject absolute paths with a structured error.
- [ ] 2.2 Recognise a top-level `## reexports` section and parse its
  `Alias | From` table into `QReexport` nodes.
- [ ] 2.3 Attach parsed imports/reexports to `QOrcaFile` (file-level, not
  per-machine). The parser SHALL NOT load any imported file.
- [ ] 2.4 Unit tests in `tests/test_parser.py`: relative + project-relative
  paths, multi-alias rows, absent section, absolute-path rejection, reexport
  rows.

## 3. Resolver

- [ ] 3.1 Create `q_orca/loader/import_resolver.py` with
  `resolve_imports(file_def, base_path, project_root) -> ResolvedImportGraph`.
  BFS over the import graph; parse each absolute path once (memoised);
  in-flight set for cycle detection.
- [ ] 3.2 Project-root discovery: walk up from the importing file to the
  nearest `pyproject.toml`; fall back to cwd. Resolve `q_orca:` paths against
  it; resolve `./` / `../` against the importing file's directory.
- [ ] 3.3 `ResolvedImportGraph.lookup_machine(alias) -> QMachineDef | None` and
  `known_aliases() -> set[str]` (for edit-distance suggestions). Follow
  re-exports transitively, capped at 4 hops.
- [ ] 3.4 Raise/return structured results for `IMPORT_NOT_FOUND`,
  `IMPORT_PARSE_FAILED` (re-prefix delegated parse error with the chain),
  `IMPORT_CYCLE` (path list), `IMPORT_CHAIN_TOO_DEEP` (chain).
- [ ] 3.5 Unit tests in `tests/test_import_resolver.py`: happy path,
  project-relative resolution, cycle, missing file, parse failure, deep chain.

## 4. Verifier — composition fall-through

- [ ] 4.1 In `q_orca/verifier/composition.py`, after same-file resolution fails,
  consult the resolved import graph (import alias → re-export) in order.
  A same-file machine shadows imports.
- [ ] 4.2 Emit `AMBIGUOUS_CHILD_MACHINE` when a name resolves from ≥2 distinct
  non-local sources; name the conflicting source paths.
- [ ] 4.3 Extend `UNRESOLVED_CHILD_MACHINE` with edit-distance "did you mean…?"
  suggestions over same-file names + import-graph aliases.
- [ ] 4.4 Translate resolver diagnostics (`IMPORT_*`) into `QVerificationError`s.
- [ ] 4.5 Honour `--no-follow-imports`: skip the resolver; treat every non-local
  invoke as unresolved with a flag-active hint. Thread the flag via
  `VerifyOptions`.
- [ ] 4.6 Unit tests in `tests/test_verifier.py`: import-alias resolution,
  same-file shadowing, ambiguity, edit-distance suggestion, `--no-follow-imports`.

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
