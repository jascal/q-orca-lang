## MODIFIED Requirements

### Requirement: Composition — Child Resolution and Typing

The verifier SHALL statically check every invoke state unless
`VerifyOptions.skip_composition` is set: the child machine must
resolve to a machine reachable from the importing file, argument bindings
must type-unify with the child's context, return bindings must
type-unify with the child's `## returns` declarations. For each
invoke state:

- The child machine name SHALL resolve in the following order:
  (1) a `QMachineDef` in the same `QOrcaFile`; (2) an alias declared in this
  file's `## imports`; (3) a re-export reachable through the import graph.
  A same-file machine SHALL shadow any import of the same name. If the name
  resolves from two or more distinct non-local sources it is
  `AMBIGUOUS_CHILD_MACHINE`. If it resolves from none it is
  `UNRESOLVED_CHILD_MACHINE` at error severity, whose message SHALL list the
  closest known names (same-file machines plus import-graph aliases) ranked by
  edit distance as "did you mean…?" suggestions.
- Each argument binding SHALL have a LHS that matches a declared
  context field on the child; otherwise: `INVOKE_ARG_UNDECLARED`.
- Each argument binding's RHS parent-side type SHALL unify with
  the child-side field type; otherwise:
  `INVOKE_ARG_TYPE_MISMATCH`.
- Each return binding's RHS SHALL match a name declared in the
  child's `## returns` section; otherwise: `INVOKE_RETURN_UNDECLARED`.
- Each return binding's LHS parent-side field type SHALL unify
  with the child-side return type (for `shots=1`) or with the
  synthesized-aggregate type (for `shots>1`); otherwise:
  `INVOKE_RETURN_TYPE_MISMATCH`.

When `--no-follow-imports` is set the verifier SHALL skip import resolution
entirely and treat every non-local invoke as `UNRESOLVED_CHILD_MACHINE`, with a
message noting that import-following is disabled.

#### Scenario: Unresolved child machine

- **WHEN** an invoke state references `Missing` but no machine
  named `Missing` exists in the file or its import graph
- **THEN** the verifier emits `UNRESOLVED_CHILD_MACHINE` at error
  severity

#### Scenario: Child resolved through an import alias

- **WHEN** an invoke state references `PrepareBellPair`, the file imports
  `./lib/bell-pair.q.orca.md` aliasing `PrepareBellPair`, and that file defines
  a `PrepareBellPair` machine
- **THEN** the child resolves and its arg/return bindings are type-checked
  against the imported machine

#### Scenario: Same-file machine shadows an import

- **WHEN** a file defines a local `## machine Child` and also imports a `Child`
  alias from another file
- **THEN** the local machine is used and no `AMBIGUOUS_CHILD_MACHINE` is emitted

#### Scenario: Ambiguous child across two imports

- **WHEN** a name resolves to a `Child` alias from two different imported files
- **THEN** the verifier emits `AMBIGUOUS_CHILD_MACHINE` naming both source paths

#### Scenario: Edit-distance suggestion on a typo

- **WHEN** an invoke references `Diffser` and the import graph exposes
  `Diffuser`
- **THEN** the `UNRESOLVED_CHILD_MACHINE` message lists `Diffuser` as a suggestion

#### Scenario: Arg type mismatch

- **WHEN** a parent binds `theta=theta` but the parent's `theta`
  is `list<float>` and the child's `theta` parameter is `float`
- **THEN** the verifier emits `INVOKE_ARG_TYPE_MISMATCH` at error
  severity

#### Scenario: Return references undeclared aggregate

- **WHEN** a parent binds `hist=hist_bits_0` under `shots=1024`
  but the child's `## returns` row for `bits[0]` lists only
  `expectation` (no `histogram`)
- **THEN** the verifier emits `INVOKE_RETURN_UNDECLARED` at error
  severity

## ADDED Requirements

### Requirement: Import Graph Resolution

The verifier SHALL resolve a file's imports via a breadth-first walk of the
import graph that parses each file at most once (memoised by absolute path) and
detects cycles. Re-exports SHALL be followed transitively but a chain longer
than four hops SHALL be rejected. The resolver SHALL surface the following
diagnostics at error severity:

- `IMPORT_NOT_FOUND` — an import `Path` does not resolve to an existing file (or
  is an absolute path).
- `IMPORT_PARSE_FAILED` — an imported file fails to parse; the message SHALL
  re-prefix the delegated parse error with the import chain that reached it.
- `IMPORT_CYCLE` — a file imports one of its own ancestors; the message SHALL
  render the cycle as a path list.
- `IMPORT_CHAIN_TOO_DEEP` — a re-export chain exceeds four hops; the message
  SHALL render the chain.

#### Scenario: Import cycle is rejected

- **WHEN** file A imports B and B imports A
- **THEN** the verifier emits `IMPORT_CYCLE` rendering the cycle as `A → B → A`

#### Scenario: Missing import file

- **WHEN** an import row points at a path with no file on disk
- **THEN** the verifier emits `IMPORT_NOT_FOUND` naming the unresolved path

#### Scenario: Re-export chain too deep

- **WHEN** a machine is re-exported through a chain of more than four files
- **THEN** the verifier emits `IMPORT_CHAIN_TOO_DEEP` rendering the chain

#### Scenario: Imported file parse failure is re-prefixed

- **WHEN** an imported file contains a parse error
- **THEN** the verifier emits `IMPORT_PARSE_FAILED` whose message names the
  import chain and includes the underlying parse error
