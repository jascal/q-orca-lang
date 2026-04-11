# Language Capability

## Purpose

The Q-Orca language is a Markdown-hosted DSL for describing quantum
state machines. A Q-Orca source file is a normal Markdown document
whose headings and tables are interpreted as an executable machine
definition. This spec captures the syntax the parser at
`q_orca/parser/markdown_parser.py` currently accepts.

## Requirements

### Requirement: Machine Heading

A Q-Orca source file SHALL introduce a machine with a level-1 heading
whose text begins with `machine` (case-insensitive), followed by the
machine name. Multiple machines in a single file SHALL be separated by
horizontal rules (`---`).

#### Scenario: Single machine

- **WHEN** a file begins with `# machine Toggle`
- **THEN** the parser emits one `QMachineDef` whose `name` is `Toggle`

#### Scenario: Two machines separated by `---`

- **WHEN** a file contains `# machine Alice`, then `---`, then `# machine Bob`
- **THEN** the parser emits two `QMachineDef` objects in declaration order

### Requirement: Context Section

The parser SHALL accept a `## context` section containing a Markdown
table with `Field`, `Type`, and optional `Default` columns.
Column matching SHALL be case-insensitive.

#### Scenario: Qubit list field

- **WHEN** `## context` contains a row `| qubits | list<qubit> | [q0, q1] |`
- **THEN** the resulting machine has a `ContextField` named `qubits` with
  type `QTypeList(element_type="qubit")` and default value `[q0, q1]`

### Requirement: Events Section

The parser SHALL accept a `## events` section as a Markdown bullet list.
Each item SHALL produce an `EventDef`. Trailing comments (after `#`) and
parameter lists (after `(`) SHALL be stripped from the event name.

#### Scenario: Simple event list

- **WHEN** `## events` contains bullets `- prepare`, `- measure # terminal`
- **THEN** the machine has events named `prepare` and `measure`

### Requirement: State Headings

Each state SHALL be introduced by its own `## state <name>` heading. The
state name SHALL be Unicode NFC normalized. The parser SHALL accept
optional `[initial]` and `[final]` annotations on the heading and an
optional blockquote description immediately following it.

#### Scenario: Named ket state with annotations

- **WHEN** a heading reads `## state |ψ> = (|00> + |11>)/√2 [final]`
- **THEN** the resulting `QStateDef` has name `|ψ>`, `state_expression`
  of `(|00> + |11>)/√2`, and `is_final=True`

#### Scenario: Implicit initial state

- **WHEN** a machine has multiple `## state` headings but none is
  marked `[initial]`
- **THEN** the first state in declaration order SHALL be treated as
  initial

### Requirement: Transitions Table

The parser SHALL accept a `## transitions` section containing a table
whose columns match (case-insensitively) `Source`, `Event`, `Guard`,
`Target`, `Action`. Rows missing `Source`, `Event`, or `Target` SHALL
be skipped. Guard cells SHALL be parsed as either a guard reference
(optionally negated with `!`) or an inline comparison expression.

#### Scenario: Simple transition row

- **WHEN** a transitions table row is `| |0> | prepare | | |+> | apply_H |`
- **THEN** the machine gains a `QTransition` with source `|0>`, event
  `prepare`, target `|+>`, action `apply_H`, and no guard

### Requirement: Guards Section

The parser SHALL accept a `## guards` section whose table maps a guard
`Name` to an `Expression`. Expression forms recognized SHALL include
`true`, `false`, `fidelity(|a>, |b>)**2 <op> <value>`, `prob('<bits>') <op> <value>`,
and simple field comparisons `<var> <op> <value>`.

#### Scenario: Probability guard

- **WHEN** a guards table row is `| collapses_zero | prob('0') ≈ 0.5 |`
- **THEN** the machine gains a `QGuardDef` whose expression is a
  `QGuardProbability` with outcome bitstring `0` and probability `0.5`

### Requirement: Actions Section

The parser SHALL accept a `## actions` section whose table has
`Name`, optional `Signature`, and optional `Effect` columns. The
signature SHALL be parsed as `(<params>) -> <return_type>`. The effect
string SHALL be parsed into a `QuantumGate` and/or a `Measurement`
where the grammar matches.

#### Scenario: Hadamard action

- **WHEN** an actions table row is `| apply_H | (qs) -> qs | Hadamard(qs[0]) |`
- **THEN** the resulting `QActionSignature` has one parameter `qs`,
  return type `qs`, and a `QuantumGate(kind="H", targets=[0])`

### Requirement: Verification Rules

The parser SHALL accept a `## verification rules` bullet list. Each
bullet SHALL be parsed as `<kind>: <description>`. Known kinds SHALL
include `unitarity`, `entanglement`, `completeness`, `no_cloning`. All
other kinds SHALL be preserved as custom rules.

#### Scenario: Opting into unitarity

- **WHEN** `## verification rules` contains `- unitarity: all gates preserve norm`
- **THEN** the machine has a `VerificationRule(kind="unitarity")` that
  causes the Stage-4 quantum check to run

### Requirement: Invariants

The parser SHALL accept a `## invariants` bullet list and SHALL
recognize two forms: `entanglement(qN, qM) = True` and
`schmidt_rank(qN, qM) <op> <number>`. Unrecognized forms SHALL be
silently ignored.

#### Scenario: Schmidt rank invariant

- **WHEN** `## invariants` contains `- schmidt_rank(q0, q1) >= 2`
- **THEN** the machine has an `Invariant(kind="schmidt_rank",
  qubits=[0, 1], op="ge", value=2.0)`

### Requirement: Gate Effect Grammar

Effect strings SHALL be parsed into `QuantumGate` values. The parser's
`_parse_gate_from_effect` function SHALL recognize the following source
syntaxes and map them to gate kinds:

- `Hadamard(qs[i])` or `H(qs[i])` → `H`
- `CNOT(qs[c], qs[t])` → `CNOT`
- `X(qs[i])`, `Y(qs[i])`, `Z(qs[i])`, `T(qs[i])`, `S(qs[i])`
- `measure(qs[i, ...])` or `M(qs[i])` → `Measurement`

#### Scenario: CNOT effect

- **WHEN** an action's effect is `CNOT(qs[0], qs[1])`
- **THEN** the parsed `QuantumGate` has `kind="CNOT"`, `targets=[1]`,
  `controls=[0]`

#### Scenario: Rotation gates not yet recognized by AST parser (known limitation)

- **WHEN** an action's effect is `Rx(qs[0], 1.5708)`
- **THEN** `_parse_gate_from_effect` returns `None` and the action's
  `gate` field is `None`, even though the compiler's separate effect
  parser handles the same syntax. This is the target of the scheduled
  change `add-parameterized-gates`.

### Requirement: Unicode Normalization

State names SHALL be normalized to Unicode NFC before lookup so that
headings and table cells referring to the same state agree regardless
of source encoding.

#### Scenario: Greek letter state

- **WHEN** a `## state |ψ>` heading uses the NFC codepoint for ψ and a
  transitions table uses a visually identical but decomposed form
- **THEN** the normalized names match and the transition resolves

### Requirement: File-Level Parsing Behavior

The parser SHALL ignore fenced code blocks, ordinary paragraph text,
and any content outside recognized sections. Horizontal rules (`---`)
SHALL act as machine separators. Only level-1 and level-2 headings,
Markdown tables, bullet lists, and blockquotes SHALL be significant.

#### Scenario: Fenced code ignored

- **WHEN** a Q-Orca file has a ```` ``` ```` fenced code block in the
  middle of the machine definition
- **THEN** the fence contents are not parsed as machine content
