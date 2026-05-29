## ADDED Requirements

### Requirement: Imported Machine Rendering

`compile_to_mermaid` SHALL render an imported invoked child (one resolved
through the file's imports rather than a same-file machine) as a distinct nested
composite node — the same shape as a same-file invoked child — carrying the
import path so the diagram shows where the child came from. No imported child
SHALL introduce a new top-level state node or transition in the parent's own
state graph beyond the composite block. A standalone import-graph view SHALL be
obtainable (the `q-orca imports show <file>` command) that renders the
transitively-closed import graph as a Mermaid diagram of files and their import
edges.

#### Scenario: Mermaid renders an imported child with its path

- **WHEN** a parent invokes `PrepareBellPair` imported from
  `./lib/bell-pair.q.orca.md` and `compile_to_mermaid` is called with the
  resolved import graph
- **THEN** the diagram includes a nested composite block for `PrepareBellPair`
  labeled with its import path `./lib/bell-pair.q.orca.md`

#### Scenario: Import graph view renders files and edges

- **WHEN** `q-orca imports show parent.q.orca.md` is run on a file that imports
  two others
- **THEN** the emitted Mermaid diagram has one node per file in the transitive
  import closure and one edge per import relationship
