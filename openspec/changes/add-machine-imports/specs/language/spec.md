## ADDED Requirements

### Requirement: Imports Section

The parser SHALL accept an optional top-level `## imports` section whose table
has `Path` and `Aliases` columns. Each row binds one or more named machines from
another `.q.orca.md` file into the importing file's namespace. The section is
parsed into `QImport(path, aliases)` nodes on `QOrcaFile.imports`; absence
yields an empty list and today's same-file-only resolution behaviour.

`Path` SHALL be either relative to the importing file (`./…`, `../…`) or
project-relative (`q_orca:…`, resolved against the nearest enclosing
`pyproject.toml` directory, or the cwd if none is found). Absolute paths SHALL
be rejected. `Aliases` SHALL be a comma-separated list of names; each alias is a
name by which a machine from the imported file may be referenced in an
`invoke:`. The parser SHALL NOT load the imported file — it records the
unresolved import rows only; loading is the resolver's responsibility.

#### Scenario: Relative import with a single alias

- **WHEN** a file declares `## imports` with one row `| ./lib/bell-pair.q.orca.md | PrepareBellPair |`
- **THEN** the parsed `QOrcaFile` has one `QImport` with
  `path="./lib/bell-pair.q.orca.md"` and `aliases=["PrepareBellPair"]`

#### Scenario: Multiple aliases on one row

- **WHEN** a row reads `| ../shared/grover-diffuser.q.orca.md | GroverDiffuser, Diffuser |`
- **THEN** the parsed `QImport` has `aliases=["GroverDiffuser", "Diffuser"]`

#### Scenario: Absent section yields no imports

- **WHEN** a file declares no `## imports` section
- **THEN** the parsed `QOrcaFile` has an empty `imports` list and resolution is
  unchanged

#### Scenario: Absolute path is rejected

- **WHEN** an import row's `Path` is an absolute path (e.g. `/etc/x.q.orca.md`)
- **THEN** the parser emits a structured error stating that absolute import
  paths are not permitted

### Requirement: Reexports Section

The parser SHALL accept an optional top-level `## reexports` section whose table
has `Alias` and `From` columns, parsed into `QReexport(alias, source)` nodes on
`QOrcaFile.reexports`. A re-export republishes a machine (resolved through this
file's own imports) under an alias so a curated index file can collect
primitives from several files into one namespace.

#### Scenario: Reexport rows parse into QReexport nodes

- **WHEN** a file declares `## reexports` with a row `| PrepareBellPair | (this file) |`
- **THEN** the parsed `QOrcaFile` has a `QReexport` with
  `alias="PrepareBellPair"` and `source="(this file)"`
