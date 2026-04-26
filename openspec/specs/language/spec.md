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

### Requirement: Noise Model Context Field

The parser SHALL recognize a context field with type `noise_model` as a
valid `QType`. The field's default value string SHALL be parsed by the
compiler's `_parse_noise_model_string` helper into a `NoiseModel` AST
node. Accepted forms are:

- `depolarizing(<float>)` — depolarizing probability p ∈ [0, 1]
- `amplitude_damping(<float>)` — damping rate γ ∈ [0, 1]
- `phase_damping(<float>)` — dephasing rate γ ∈ [0, 1]
- `thermal(<float>)` — T1 relaxation time in ns; T2 defaults to T1
- `thermal(<float>, <float>)` — T1 and T2 relaxation times in ns

The field name SHALL be `noise` by convention, but the parser does not
enforce the name. An unrecognized kind string SHALL result in a `None`
noise model (no noise applied), not a parse error, to preserve forward
compatibility.

#### Scenario: Depolarizing field parses to NoiseModel

- **WHEN** a context table contains `| noise | noise_model | depolarizing(0.01) |`
- **THEN** the field's `type` is `QTypeScalar(kind="noise_model")` and
  the compiler resolves it to `NoiseModel(kind="depolarizing", parameter=0.01)`

#### Scenario: Thermal field with two parameters

- **WHEN** a context table contains `| noise | noise_model | thermal(50000, 70000) |`
- **THEN** the compiler resolves it to
  `NoiseModel(kind="thermal", parameter=50000.0, parameter2=70000.0)`

#### Scenario: Thermal field with one parameter defaults T2

- **WHEN** a context table contains `| noise | noise_model | thermal(50000) |`
- **THEN** the compiler resolves it to
  `NoiseModel(kind="thermal", parameter=50000.0, parameter2=50000.0)`

#### Scenario: Unrecognized noise kind is a no-op

- **WHEN** a context table contains `| noise | noise_model | custom_noise(0.1) |`
- **THEN** `_parse_noise_model_string` returns `None` and no noise model
  is applied — no parse error is raised

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
- `Rx(qs[i], <angle>)`, `Ry(qs[i], <angle>)`, `Rz(qs[i], <angle>)` → `Rx`/`Ry`/`Rz`
- `CCX(qs[c0], qs[c1], qs[t])` or `CCNOT(...)` or `Toffoli(...)` → `CCNOT`
- `CCZ(qs[c0], qs[c1], qs[t])` → `CCZ`
- `MCX(qs[c0], qs[c1], ..., qs[t])` (≥ 3 args, last is target) → `MCX`
- `MCZ(qs[c0], qs[c1], ..., qs[t])` (≥ 3 args, last is target) → `MCZ`
- `measure(qs[i, ...])` or `M(qs[i])` → `Measurement`

The canonical rotation-gate argument order SHALL be qubit-first,
angle-second. `<angle>` SHALL be parsed by the symbolic angle evaluator,
which accepts: decimal literals, `pi`, `pi/<int>`, `<int>*pi`,
`<int>*pi/<int>`, and a leading minus sign on any of the above. Any
rotation-gate effect whose argument order or angle does not match SHALL
produce a parser error rather than silently coercing to `0.0`.

The qubit-list subscript inside any of the recognized gate forms SHALL
accept either a literal non-negative integer (`qs[0]`, `qs[10]`) or a
bound parameter identifier (`qs[c]`) drawn from the enclosing action's
signature. Identifier subscripts whose name does not appear in the
action's signature SHALL produce a parser error referencing the
unbound name.

For `MCX` and `MCZ` the parser SHALL require at least three arguments
(at least two controls and one target). Two-control invocations of `X`
and `Z` SHALL be written as `CCX` and `CCZ`, not `MCX(qs[c0], qs[c1])`,
`MCZ(qs[c0], qs[c1])`, which fail to parse.

#### Scenario: CNOT effect

- **WHEN** an action's effect is `CNOT(qs[0], qs[1])`
- **THEN** the parsed `QuantumGate` has `kind="CNOT"`, `targets=[1]`,
  `controls=[0]`

#### Scenario: CCNOT effect

- **WHEN** an action's effect is `CCNOT(qs[0], qs[1], qs[2])`
- **THEN** the parsed `QuantumGate` has `kind="CCNOT"`, `targets=[2]`,
  `controls=[0, 1]`

#### Scenario: CCZ effect

- **WHEN** an action's effect is `CCZ(qs[0], qs[1], qs[2])`
- **THEN** the parsed `QuantumGate` has `kind="CCZ"`, `targets=[2]`,
  `controls=[0, 1]`

#### Scenario: MCX with three controls

- **WHEN** an action's effect is `MCX(qs[0], qs[1], qs[2], qs[3])`
- **THEN** the parsed `QuantumGate` has `kind="MCX"`, `targets=[3]`,
  `controls=[0, 1, 2]`

#### Scenario: MCZ with three controls

- **WHEN** an action's effect is `MCZ(qs[0], qs[1], qs[2], qs[3])`
- **THEN** the parsed `QuantumGate` has `kind="MCZ"`, `targets=[3]`,
  `controls=[0, 1, 2]`

#### Scenario: MCX with too few arguments fails

- **WHEN** an action's effect is `MCX(qs[0], qs[1])` (only one control)
- **THEN** the parser emits a parse error referencing the minimum-arity
  requirement, and does not silently fall through to `CNOT`

#### Scenario: Identifier subscript with bound parameter

- **WHEN** an action `query | (qs, c: int) -> qs | Hadamard(qs[c])` is
  parsed
- **THEN** the parser accepts the effect string and records the
  subscript as an identifier reference `c`, not a literal int

#### Scenario: Identifier subscript with unbound parameter

- **WHEN** an action `query | (qs) -> qs | Hadamard(qs[c])` is parsed
- **THEN** the parser emits a structured error naming `c` as an
  unbound subscript identifier

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

### Requirement: Structured Polysemantic Example Pattern

The example library SHALL include at least one *structured-overlap*
polysemantic machine that demonstrates block-structured concept
geometry as distinct from uniform-overlap geometry. The canonical
file is `examples/larql-polysemantic-clusters.q.orca.md`.

A structured-polysemantic example SHALL satisfy these invariants:

1. **Compact concept register.** The `## context` declares a
   fixed-size `qubits: list<qubit>` with `n` qubits where `2^n ≥ N`
   and `N` is the number of concepts. The canonical example uses
   `n = 3, N = 12`.
2. **Product-state concept encoding.** Each concept `c_i` is prepared
   from `|0^n>` by a product-state unitary (one single-qubit rotation
   per qubit) with hand-picked per-concept angles. The canonical
   rotation family is `Ry`; future variants MAY substitute other
   single-qubit rotations.
3. **Single parametric preparation action.** Exactly one parametric
   action with signature
   `(qs, <n angle-typed params>) -> qs` and a matching product-state
   effect. The N concepts are 1-to-1 with the N angle-typed call
   sites to this action, not with N copy-pasted actions.
4. **Single parametric query action.** Exactly one parametric action
   with the same angle-typed signature as the prepare action and an
   effect that is the inverse of the prepare effect (gate order
   reversed, angle signs negated).
5. **Documented clustered Gram matrix.** The example's leading
   paragraph SHALL tabulate the analytic `|<c_i | c_j>|²` matrix
   and SHALL call out at least two tiers (intra-cluster overlap and
   cross-cluster overlap). Uniform-overlap examples like
   `larql-polysemantic-12.q.orca.md` do NOT satisfy this invariant
   and are categorized separately.
6. **Documented polysemy column for a loaded cluster.** The example
   SHALL identify a specific cluster `S ⊂ {0..N-1}` and tabulate the
   analytic `P(|0^n> | query_i)` values when the feature state is
   `|f> = normalize(Σ_{i ∈ S} |c_i>)`. The tabulated values SHALL
   exhibit the same tier structure as the Gram matrix (an
   in-cluster tier and an out-of-cluster tier).

The existing `larql-polysemantic-2.q.orca.md` and
`larql-polysemantic-12.q.orca.md` examples remain valid and
unchanged; they demonstrate the parametric-action *mechanism* with
uniform overlap. The new `larql-polysemantic-clusters.q.orca.md`
demonstrates the *phenomenon* on top of the same mechanism.

#### Scenario: Canonical example parses and verifies

- **WHEN** `parse_q_orca_markdown(open(
  "examples/larql-polysemantic-clusters.q.orca.md").read())` is
  invoked
- **THEN** `parsed.errors == []`
- **AND** `verify(parsed.file.machines[0]).valid == True`

#### Scenario: Canonical example compiles to expected register size

- **GIVEN** the canonical example has `n = 3, N = 12`
- **WHEN** `compile_to_qasm(machine)` and `compile_to_qiskit(machine)`
  are invoked
- **THEN** the QASM output contains `qubit[3] q;`
- **AND** the Qiskit script contains `QuantumCircuit(3)`
- **AND** the Qiskit script contains 12 separate sub-sequences
  corresponding to the 12 query call sites, each of which emits one
  `qc.ry(...)` per concept-register qubit after the prepare segment

#### Scenario: Structured invariants are checkable via concept_gram

- **GIVEN** the canonical example
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the returned matrix's `|gram[i,j]|²` values exhibit the
  block structure documented in the example's Gram-matrix table,
  within a numerical tolerance of `1e-6` on each entry

### Requirement: Action Signature Parameters

The actions table's `Signature` cell SHALL accept zero or more typed
positional parameters after the leading `qs` parameter. The grammar is
`(qs, name1: type1, name2: type2, ...) -> qs`. Supported initial types
SHALL be `int` (used in qubit-list subscripts) and `angle` (used in
rotation-gate angle slots). Parameter names SHALL be unique within a
signature. Whitespace around `:` and `,` SHALL not be significant.

The existing zero-parameter form `(qs) -> qs` SHALL continue to parse
unchanged. Actions whose signature parses as parameterized SHALL have a
new `parameters: list[ActionParameter]` field populated on the AST,
with `ActionParameter(name: str, type: Literal["int", "angle"])`.

#### Scenario: Zero-parameter action remains valid

- **WHEN** an action signature is `(qs) -> qs`
- **THEN** the parsed `QActionSignature` has empty `parameters`

#### Scenario: Single-int-parameter action

- **WHEN** an action signature is `(qs, c: int) -> qs`
- **THEN** the parsed `QActionSignature` has `parameters` of length 1
  with `name="c"`, `type="int"`

#### Scenario: Mixed int and angle parameters

- **WHEN** an action signature is `(qs, c: int, theta: angle) -> qs`
- **THEN** the parsed `QActionSignature` has `parameters` of length 2,
  in declaration order

#### Scenario: Duplicate parameter name

- **WHEN** an action signature is `(qs, c: int, c: int) -> qs`
- **THEN** the parser emits a structured error naming `c` as a
  duplicate parameter

#### Scenario: Unknown parameter type

- **WHEN** an action signature is `(qs, c: float) -> qs`
- **THEN** the parser emits a structured error naming `float` as an
  unsupported parameter type

### Requirement: Transition Action Call Form

The transitions table's `Action` cell SHALL accept either the existing
bare-name form (`apply_h`) or a new call form (`query_concept(0)`,
`query_concept(11)`, `rotate_q0(pi/4)`). In the call form the action
name SHALL refer to a declared action whose signature has matching
arity. Each argument SHALL be a literal of the corresponding declared
type: integer literals for `int`, angle expressions (per the symbolic
angle grammar) for `angle`. Whitespace inside the parenthesized list
SHALL not be significant.

The parsed `QTransition.action` field SHALL gain a sibling
`bound_arguments: list[BoundArg] | None` field. `bound_arguments` is
`None` for the bare-name form, and a list of typed values in
declaration order for the call form.

Bare-name references to a parameterized action SHALL produce a
structured error: a parametric action MUST be invoked with its
arguments. Call-form references to a non-parameterized action SHALL
also produce a structured error.

#### Scenario: Bare-name reference to a non-parametric action

- **WHEN** a transitions row's Action cell is `apply_h` and `apply_h`
  has signature `(qs) -> qs`
- **THEN** the parsed `QTransition.action` is `"apply_h"` and
  `bound_arguments` is `None`

#### Scenario: Call-form reference with a literal int argument

- **WHEN** a transitions row's Action cell is `query_concept(3)` and
  `query_concept` has signature `(qs, c: int) -> qs`
- **THEN** `QTransition.action` is `"query_concept"` and
  `bound_arguments` is `[BoundArg(name="c", value=3)]`

#### Scenario: Call-form reference with an angle expression

- **WHEN** a transitions row's Action cell is `rotate(pi/4)` and
  `rotate` has signature `(qs, theta: angle) -> qs`
- **THEN** `bound_arguments` is `[BoundArg(name="theta",
  value=math.pi/4)]`

#### Scenario: Bare-name reference to a parametric action fails

- **WHEN** a transitions row's Action cell is `query_concept` and
  `query_concept` has signature `(qs, c: int) -> qs`
- **THEN** the parser emits a structured error indicating that
  `query_concept` requires arguments

#### Scenario: Call-form arity mismatch fails

- **WHEN** a transitions row's Action cell is `query_concept(0, 1)`
  and `query_concept` has signature `(qs, c: int) -> qs`
- **THEN** the parser emits a structured error naming the expected and
  actual argument counts

#### Scenario: Call-form type mismatch fails

- **WHEN** a transitions row's Action cell is `query_concept(pi/4)`
  and `query_concept` has signature `(qs, c: int) -> qs`
- **THEN** the parser emits a structured error indicating that an `int`
  argument was expected

