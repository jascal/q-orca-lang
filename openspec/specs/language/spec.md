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
optional `[initial]`, `[final]`, and `[assert: …]` annotations on the
heading and an optional blockquote description immediately following it.

The `[assert: …]` annotation SHALL carry one or more semicolon-separated
*category expressions* describing the expected quantum-register
configuration at that state. Recognized category expressions are:

- `classical(qs[k])`, `classical(qs[a..b])`
- `superposition(qs[k])`, `superposition(qs[a..b])`
- `entangled(qs[i], qs[j])`
- `separable(qs[i], qs[j])`

Each category expression SHALL be parsed into a `QAssertion` AST node
with fields `category`, `targets: list[QubitSlice]`, and `source_span`,
and collected into `QState.assertions: list[QAssertion]`. Multiple
bracketed annotations on the same heading SHALL be conjunctive — both
`[final]` and `[assert: classical(qs[3..4])]` may appear on the same
heading. The order of bracketed annotations SHALL NOT be significant.

Unrecognized category names inside `[assert: …]` SHALL produce a
structured `unknown_assertion_category` parser error referencing the
heading.

#### Scenario: Named ket state with annotations

- **WHEN** a heading reads `## state |ψ> = (|00> + |11>)/√2 [final]`
- **THEN** the resulting `QStateDef` has name `|ψ>`, `state_expression`
  of `(|00> + |11>)/√2`, and `is_final=True`

#### Scenario: Implicit initial state

- **WHEN** a machine has multiple `## state` headings but none is
  marked `[initial]`
- **THEN** the first state in declaration order SHALL be treated as
  initial

#### Scenario: Single-category assertion annotation

- **WHEN** a heading reads `## state |bell> [assert: entangled(qs[0], qs[1])]`
- **THEN** the resulting `QStateDef` has `assertions` of length 1 with
  `category="entangled"` and `targets=[QubitSlice(0), QubitSlice(1)]`

#### Scenario: Multi-category assertion annotation

- **WHEN** a heading reads `## state |encoded> [assert: superposition(qs[0..2]); entangled(qs[0], qs[1]); entangled(qs[1], qs[2])]`
- **THEN** the resulting `QStateDef` has `assertions` of length 3, in
  declaration order, each with the expected `category` and `targets`

#### Scenario: Slice form on a single qubit

- **WHEN** a heading reads `## state |coherent> [assert: superposition(qs[0])]`
- **THEN** the parsed `QAssertion` has
  `targets=[QubitSlice(start=0, end=0)]`

#### Scenario: Range form across multiple qubits

- **WHEN** a heading reads `## state |joint> [assert: classical(qs[3..4])]`
- **THEN** the parsed `QAssertion` has
  `targets=[QubitSlice(start=3, end=4)]`

#### Scenario: Conjunctive annotation with `[final]`

- **WHEN** a heading reads `## state |measured> [final, assert: classical(qs[3..4])]`
- **THEN** the resulting `QStateDef` has `is_final=True` AND
  `assertions` of length 1 with `category="classical"`

#### Scenario: Unknown assertion category produces a parse error

- **WHEN** a heading reads `## state |unsure> [assert: thermalised(qs[0])]`
- **THEN** the parser emits `unknown_assertion_category` referencing
  the heading and naming `thermalised` as the unrecognized category

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

The parser SHALL recognize a context field with type `noise_model` as a valid `QType`, retained as a **deprecated alias** for the `## noise_model` section. The field's default value string SHALL be parsed by the compiler's `_parse_noise_model_string` helper and wrapped into a single-row `NoiseModelSection` whose one `NoiseChannel` targets `all_gates` (preserving the historical "attach to all gates" semantics). Accepted forms are:

- `depolarizing(<float>)` — depolarizing probability p ∈ [0, 1]
- `amplitude_damping(<float>)` — damping rate γ ∈ [0, 1]
- `phase_damping(<float>)` — dephasing rate γ ∈ [0, 1]
- `thermal(<float>)` — T1 relaxation time in ns; T2 defaults to T1
- `thermal(<float>, <float>)` — T1 and T2 relaxation times in ns

The field name SHALL be `noise` by convention, but the parser does not enforce the name. An unrecognized kind string SHALL result in a `None` noise model (no noise applied), not a parse error, to preserve forward compatibility. When a machine uses this field form, the verifier SHALL emit exactly one `NOISE_CONTEXT_FIELD_DEPRECATED` diagnostic (warning severity) whose suggestion shows the equivalent `## noise_model` section for the author's actual channel (e.g. for `depolarizing(0.01)`, the suggestion renders the one-row table `| depolarizing | all_gates | p=0.01 |`); the field is slated for removal in v0.8.

#### Scenario: Depolarizing field parses to a single-row section

- **WHEN** a context table contains `| noise | noise_model | depolarizing(0.01) |`
- **THEN** the field's `type` is `QTypeScalar(kind="noise_model")` and it resolves to a `NoiseModelSection` with one `NoiseChannel(kind="depolarizing", target=AllGates, parameters={"p": 0.01})`

#### Scenario: Thermal field with two parameters

- **WHEN** a context table contains `| noise | noise_model | thermal(50000, 70000) |`
- **THEN** it resolves to a single-row section whose channel is `thermal` with T1 = 50000 ns and T2 = 70000 ns targeting `all_gates`

#### Scenario: Unrecognized noise kind is a no-op

- **WHEN** a context table contains `| noise | noise_model | custom_noise(0.1) |`
- **THEN** `_parse_noise_model_string` returns `None`, no noise model is applied, and no parse error is raised

#### Scenario: Using the field emits a deprecation diagnostic

- **WHEN** a machine declares the `noise` context field in any accepted form
- **THEN** the verifier emits exactly one `NOISE_CONTEXT_FIELD_DEPRECATED` diagnostic at warning severity whose suggestion contains the equivalent one-row `## noise_model` table for that channel

### Requirement: Verification Rules

The parser SHALL accept a `## verification rules` bullet list. Each
bullet SHALL be parsed as `<kind>: <description>`. Known kinds SHALL
include `unitarity`, `entanglement`, `completeness`, `no_cloning`, and
`state_assertions`. All other kinds SHALL be preserved as custom rules.

The `state_assertions` rule SHALL activate the
`check_state_assertions` verifier stage defined in the verifier spec.
Absence of the rule SHALL leave that stage skipped, even if `[assert:
…]` annotations are present on individual states.

#### Scenario: Opting into unitarity

- **WHEN** `## verification rules` contains `- unitarity: all gates preserve norm`
- **THEN** the machine has a `VerificationRule(kind="unitarity")` that
  causes the Stage-4 quantum check to run

#### Scenario: Opting into state assertions

- **WHEN** `## verification rules` contains `- state_assertions: …`
- **THEN** the machine has a `VerificationRule(kind="state_assertions")`
  that causes the assertion-checking stage to run

### Requirement: Invariants

The parser SHALL accept a `## invariants` bullet list and SHALL
recognize three forms:

- `entanglement(qN, qM) = True`
- `schmidt_rank(qN, qM) <op> <number>`
- `<resource_metric> <op> <integer>` where `<resource_metric>` is
  one of `gate_count`, `depth`, `cx_count`, `t_count`,
  `logical_qubits` and `<op>` is one of `<=`, `<`, `==`, `>=`, `>`.

Resource-form invariants SHALL produce
`Invariant(kind="resource", metric=<name>, op=<op>, value=<int>)`.
The existing `entanglement` and `schmidt_rank` forms SHALL continue
to produce the same AST as before (with `metric=None`).

Unrecognized forms SHALL be silently ignored, preserving
backwards-compatibility with existing files that may use a
not-yet-recognized invariant idiom.

#### Scenario: Schmidt rank invariant

- **WHEN** `## invariants` contains `- schmidt_rank(q0, q1) >= 2`
- **THEN** the machine has an `Invariant(kind="schmidt_rank",
  qubits=[0, 1], op="ge", value=2.0, metric=None)`

#### Scenario: Resource invariant — gate count

- **WHEN** `## invariants` contains `- gate_count <= 40`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="gate_count", op="le", value=40)`

#### Scenario: Resource invariant — T-count zero

- **WHEN** `## invariants` contains `- t_count == 0`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="t_count", op="eq", value=0)`

#### Scenario: Resource invariant — logical qubit ceiling

- **WHEN** `## invariants` contains `- logical_qubits <= 3`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="logical_qubits", op="le", value=3)`

#### Scenario: Resource invariant — depth bound

- **WHEN** `## invariants` contains `- depth <= 20`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="depth", op="le", value=20)`

#### Scenario: Resource invariant — CX count bound

- **WHEN** `## invariants` contains `- cx_count <= 12`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="cx_count", op="le", value=12)`

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

### Requirement: Resources Section

The parser SHALL accept an optional top-level `## resources` section
containing a 2- or 3-column markdown table. The first column is
`Metric`; the second is `Basis`; the optional third is `Notes`.

The first column SHALL contain one of the five recognized metric
names: `gate_count`, `depth`, `cx_count`, `t_count`,
`logical_qubits`. Unknown names SHALL produce a structured parser
error referencing the offending row.

The second and third columns are informational; the parser SHALL
NOT validate their contents beyond requiring the table to be
well-formed markdown.

The parsed metric names SHALL populate
`QMachine.resource_metrics: list[str]`. When the section is absent,
`resource_metrics` SHALL be an empty list, and downstream consumers
(the compiler's resource report, the verifier's
`check_resource_invariants` rule) SHALL fall back to the default
metric set: all five recognized names.

#### Scenario: Two-column resources section parses

- **WHEN** a machine contains
  ```
  ## resources

  | Metric         | Basis            |
  |----------------|------------------|
  | gate_count     | logical          |
  | cx_count       | native           |
  ```
- **THEN** `machine.resource_metrics == ["gate_count", "cx_count"]`

#### Scenario: Three-column resources section parses identically

- **WHEN** a machine contains
  ```
  ## resources

  | Metric         | Basis            | Notes                |
  |----------------|------------------|----------------------|
  | gate_count     | logical          | total before decomp  |
  | cx_count       | native           | NISQ-relevant        |
  ```
- **THEN** `machine.resource_metrics == ["gate_count", "cx_count"]`
  and the `Notes` column contents are ignored

#### Scenario: Unknown metric name in resources section

- **WHEN** a machine contains a `## resources` row with metric name
  `qubit_count` (not one of the five recognized names)
- **THEN** the parser appends a structured `unknown_resource_metric`
  error referencing the row and the unrecognized name, and the
  metric is not added to `resource_metrics`

#### Scenario: Resources section is optional

- **WHEN** a machine has no `## resources` section
- **THEN** `machine.resource_metrics == []` and parsing succeeds
  with no warnings

### Requirement: Hierarchical Polysemantic Example Pattern

The example library SHALL include at least one *hierarchical-
overlap* polysemantic machine that demonstrates a concept geometry
whose pairwise overlap matrix is **non-factorized** — that is,
`⟨c_i | c_j⟩` does NOT decompose as a product over per-qubit
cosines of single-angle differences. The canonical file is
`examples/larql-polysemantic-hierarchical.q.orca.md`.

A hierarchical-polysemantic example SHALL satisfy these invariants:

1. **Compact concept register.** The `## context` declares a
   fixed-size `qubits: list<qubit>` with `n` qubits where `2^n ≥ N`
   and `N` is the number of concepts. The canonical example uses
   `n = 3, N = 12`.

2. **Bond-2 MPS concept encoding with non-factorized Gram.** Each
   concept `c_i` is prepared from `|0^n⟩` by a CNOT-staircase
   circuit consisting of `n` single-qubit `Ry` rotations interleaved
   with `n-1` CNOTs between adjacent qubits. The angle bound to
   each `Ry` MAY be a single parameter or a *linear combination* of
   the action's angle parameters (e.g., `α + β`). At least one of
   the `Ry` rotations SHALL bind a multi-term linear combination so
   that the Gram matrix does not factorize. The canonical example
   uses the cross-coupled-by-sum encoding

       Ry(qs[0], a)
       ; CNOT(qs[0], qs[1])
       ; Ry(qs[1], a + b)
       ; CNOT(qs[1], qs[2])
       ; Ry(qs[2], b + c)

   Higher-bond-dim variants MAY add further 2-qubit gates per
   staircase step; this requirement addresses only the bond-dim-2
   canonical shape.

3. **Non-factorization criterion.** The encoding's Gram matrix
   SHALL differ measurably from the same-angle product-state Gram.
   Specifically: with `gram_prod[i, j] = ∏_k cos((θ_{i,k} −
   θ_{j,k})/2)` over the action's `n` angle parameters, the canonical
   example SHALL satisfy `max_{i ≠ j} | |gram[i,j]|² −
   |gram_prod[i,j]|² | ≥ 0.05`. The strict-staircase shape
   `Ry(qs[k], <single param>)` interleaved with CNOTs — used by
   `add-mps-concept-encoding` and shown to factorize in this
   change's design.md — does NOT satisfy the non-factorization
   criterion and is NOT a permitted shape for the canonical
   hierarchical example. (It remains a permitted shape for *future*
   examples that document the factorization explicitly as a
   teaching point.)

4. **Single parametric preparation action.** Exactly one parametric
   action with signature `(qs, <n angle-typed params>) -> qs` and a
   matching CNOT-staircase effect satisfying invariants 2 and 3.
   The N concepts are 1-to-1 with the N parametric call sites to
   this action, not with N copy-pasted actions.

5. **Single parametric query action.** Exactly one parametric
   action with the same angle-typed signature as the prepare action
   and an effect that is the exact inverse of the prepare effect
   (gate order reversed, angle-expression signs negated, CNOTs
   self-inverse so they reappear in reversed position). When the
   prepare effect binds a linear combination like `Ry(qs[k], a + b)`,
   the inverse is `Ry(qs[k], -(a + b))` (equivalently `Ry(qs[k], -a
   - b)`).

6. **Documented hierarchical Gram matrix.** The example's leading
   paragraph SHALL tabulate the analytic `|⟨c_i | c_j⟩|²` matrix
   and SHALL call out at least **four tiers**: self (1.0), sub-
   cluster-mate, super-group-sibling, and cross-group. Flat-tier
   examples like `larql-polysemantic-clusters.q.orca.md` (three
   tiers) do NOT satisfy this invariant and are categorized
   separately.

7. **Documented polysemy column for a loaded concept.** The example
   SHALL identify a specific concept `c_0` and tabulate the
   analytic `P(|0^n⟩ | query_i)` values when the feature state is
   `|f⟩ = |c_0⟩`. The tabulated values SHALL exhibit the same four-
   tier structure as row 0 of the Gram matrix.

The existing `larql-polysemantic-2`, `larql-polysemantic-12`, and
`larql-polysemantic-clusters` examples remain valid and unchanged;
they demonstrate the parametric-action mechanism with progressively
richer product-state geometry. The
`larql-polysemantic-hierarchical.q.orca.md` example demonstrates
the first non-product-state, non-factorized-Gram encoding in the
polysemantic example family.

#### Scenario: Canonical example parses and verifies

- **WHEN** `parse_q_orca_markdown(open(
  "examples/larql-polysemantic-hierarchical.q.orca.md").read())` is
  invoked
- **THEN** `parsed.errors == []`
- **AND** `verify(parsed.file.machines[0]).valid == True`

#### Scenario: Canonical example compiles to expected register size

- **GIVEN** the canonical example has `n = 3, N = 12`
- **WHEN** `compile_to_qasm(machine)` and `compile_to_qiskit(machine)`
  are invoked
- **THEN** the QASM output contains `qubit[3] q;`
- **AND** the Qiskit script contains `QuantumCircuit(3)`
- **AND** the Qiskit script contains both `qc.ry(` calls and
  `qc.cx(` calls in the expected staircase pattern, with the
  second and third `qc.ry(` calls receiving the linear combination
  *fully evaluated to a numeric float at compile time* (e.g.,
  `qc.ry(-0.85, 2)` for the bound triple `a=0.0, b=-0.5, c=-0.35`)
  rather than a symbolic `a_value + b_value` form or a single
  bound parameter
- **AND** the total number of `qc.ry(` calls matches the per-
  call-site expansion (3 for prepare + 3 × 12 = 36 for queries,
  total 39)
- **AND** the total number of `qc.cx(` calls matches the staircase
  CNOT expansion (2 for prepare + 2 × 12 = 24 for queries,
  total 26)

#### Scenario: Four-tier structure is checkable via compute_concept_gram_mps

- **GIVEN** the canonical example
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the returned matrix's `|gram[i,j]|²` values partition
  into exactly four tiers as documented in the example's leading
  paragraph, within a numerical tolerance of `1e-6` on each entry

#### Scenario: Encoding's Gram differs measurably from same-angle product-state Gram

- **GIVEN** the canonical example and its 12 angle triples `(a_i,
  b_i, c_i)`
- **WHEN** `gram_mps = compute_concept_gram_mps(machine)` and
  `gram_prod[i, j] = cos((a_i − a_j)/2) · cos((b_i − b_j)/2) ·
  cos((c_i − c_j)/2)` are computed
- **THEN** `max_{i ≠ j} | |gram_mps[i,j]|² − |gram_prod[i,j]|² |
  ≥ 0.05`

#### Scenario: Strict-staircase factorizing shape is rejected as canonical

- **GIVEN** a candidate hierarchical example whose prepare effect
  is the strict-staircase shape `Ry(qs[0], a); CNOT(qs[0], qs[1]);
  Ry(qs[1], b); CNOT(qs[1], qs[2]); Ry(qs[2], c)` (single-bound-
  param Ry rotations with no linear combinations)
- **WHEN** the encoding's Gram is compared against the same-angle
  product-state Gram
- **THEN** the two Grams are equal to within machine epsilon (the
  staircase factorizes), violating invariant 3 of this requirement
- **AND** the example does NOT satisfy this requirement as the
  canonical hierarchical example

### Requirement: Encoding Declaration Section

The parser SHALL recognize an optional top-level `## encoding`
section by which a `.q.orca.md` machine declares an explicit ansatz
shape. When present, the parser SHALL parse it as a key/value table
with the following keys:

| Key | Required | Type | Allowed values |
|-----|----------|------|----------------|
| `kind` | yes | string | `hea` |
| `depth` | yes | int | positive integer |
| `entangler` | yes | string | `ring` \| `chain` |
| `rotations` | yes | string | comma-separated subset of `{Rx, Ry, Rz}` (preserving declaration order) |
| `qubits` | no | string | name of a `## context` register field; defaults to `qubits` |

The parser SHALL produce an `EncodingDecl(kind, depth, entangler,
rotations, qubits)` AST node whose `rotations` field is a tuple in
the declared order.

Unknown keys, missing required keys, or out-of-range values SHALL
raise a structured parser error naming the offending row. Future
ansatz kinds (e.g. `alternating-layered`, `brick-wall`) MAY extend
the `kind` enumeration; this requirement covers `kind: hea` only.

#### Scenario: Minimal HEA encoding declaration parses

- **GIVEN** a machine containing
  ```
  ## encoding
  | key | value |
  |-----|-------|
  | kind | hea |
  | depth | 3 |
  | entangler | ring |
  | rotations | Ry, Rz |
  ```
- **WHEN** `parse_q_orca_markdown(...)` is invoked
- **THEN** `parsed.errors == []`
- **AND** `machine.encoding == EncodingDecl(kind="hea", depth=3,
  entangler="ring", rotations=("Ry", "Rz"), qubits=None)`

#### Scenario: Unknown encoding key surfaces a structured error

- **GIVEN** an encoding section containing `| frob | yes |`
- **WHEN** parsing
- **THEN** the parser emits an error naming the unknown key
  `frob` and the row number, and the machine's `encoding` field
  remains unset

#### Scenario: Unknown rotation kind is rejected

- **GIVEN** an encoding section with `rotations: Ry, Foo`
- **WHEN** parsing
- **THEN** the parser emits an error naming `Foo` as an
  unsupported rotation; supported values are `Rx`, `Ry`, `Rz`

#### Scenario: Non-positive depth is rejected

- **GIVEN** an encoding section with `depth: 0`
- **WHEN** parsing
- **THEN** the parser emits an error noting that `depth` SHALL be
  a positive integer

### Requirement: Theta Parameter Block Section

The `## theta` block parser SHALL accept either a 2-column form
`| concept | tensor |` (existing) or a 3-column form
`| concept | cluster | tensor |` (new). Per-row, `cluster` SHALL
be a non-empty trimmed string. When the cluster column is omitted
on the header line, every row SHALL be assigned the implicit
cluster label `_default`.

A machine SHALL NOT mix forms within a single `## theta` block —
either every row declares a cluster or none does. Mixed-form blocks
SHALL be rejected as a parse error.

#### Scenario: Two-column theta block parses with implicit cluster

- **WHEN** a machine's `## theta` is `| concept | tensor |` with N
  rows
- **THEN** the parser produces N `ThetaRow` instances each with
  `cluster == "_default"`

#### Scenario: Three-column theta block carries declared clusters

- **GIVEN** a machine's `## theta` block:
  ```
  | concept | cluster | tensor |
  |---------|---------|--------|
  | a | s1 | [[...]] |
  | b | s1 | [[...]] |
  | c | s2 | [[...]] |
  ```
- **WHEN** the parser runs
- **THEN** the resulting `ThetaRow`s have
  `cluster == "s1"`, `"s1"`, `"s2"` respectively

#### Scenario: Empty cluster value is rejected

- **WHEN** a 3-column theta row has an empty cluster cell
- **THEN** the parser raises a parse error naming the offending
  row index

### Requirement: Minimal HEA Example Pattern

The example library SHALL include at least one rung-2 (HEA)
polysemantic machine demonstrating the explicit `## encoding` /
`## theta` grammar. The canonical file is
`examples/larql-hea-minimal.q.orca.md`.

A minimal HEA example SHALL satisfy these invariants:

1. **Compact concept register.** The `## context` declares a
   fixed-size `qubits: list<qubit>` with `n` qubits. The canonical
   example uses `n = 3` and three concepts.

2. **HEA encoding.** The machine declares an `## encoding` section
   with `kind: hea`, `depth ≥ 2`, `entangler ∈ {ring, chain}`, and
   a `rotations` subset of `{Rx, Ry, Rz}` of size at least 1.

3. **Concept-aligned theta block.** The `## theta` block declares
   exactly one row per parametric call site referenced in the
   transitions table. Each tensor has shape
   `(|rotations|, depth, n)`.

4. **Documented Gram matrix.** The example's leading paragraph
   SHALL tabulate the analytic `|<c_i | c_j>|²` matrix and SHALL
   call out at least three tiers (self, sub-cluster, cross), with
   strict inter-tier separation greater than the Stage 4b
   tolerance of `0.025`.

#### Scenario: Canonical HEA example parses and verifies

- **WHEN** `parse_q_orca_markdown(open(
  "examples/larql-hea-minimal.q.orca.md").read())` is invoked
- **THEN** `parsed.errors == []`
- **AND** `verify(parsed.file.machines[0]).valid == True`
- **AND** `machine.encoding.kind == "hea"`
- **AND** `len(machine.theta.rows) == len(<query call sites>)`

#### Scenario: HEA Gram is checkable via compute_concept_gram_hea

- **GIVEN** the canonical example
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the returned matrix is `(N, N)` complex
- **AND** `|gram[i, i]| == 1` for all diagonal entries
- **AND** the off-diagonal `|gram[i, j]|²` entries partition into
  the documented tiers, each tier separated from the next by at
  least the Stage 4b tolerance of `0.025`

### Requirement: concept_gram_tier_separation invariant

The `## invariants` parser SHALL accept the resource-form bullet
`concept_gram_tier_separation <op> <decimal>` where `<op>` is one
of `<=`, `<`, `==`, `>=`, `>` and `<decimal>` is a real number in
`[0, 1]`. The parser SHALL produce
`Invariant(kind="resource", metric="concept_gram_tier_separation",
op=<op>, value=<float>)`.

Existing invariant forms (`entanglement`, `schmidt_rank`, and the
integer-valued resource metrics `gate_count`, `depth`, `cx_count`,
`t_count`, `logical_qubits`) SHALL continue to parse unchanged.

#### Scenario: Tier-separation invariant parses

- **WHEN** `## invariants` contains
  `- concept_gram_tier_separation >= 0.025`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="concept_gram_tier_separation", op="ge", value=0.025)`

#### Scenario: Tier-separation invariant accepts decimal value

- **WHEN** `## invariants` contains
  `- concept_gram_tier_separation > 0.5`
- **THEN** the machine has an `Invariant(kind="resource",
  metric="concept_gram_tier_separation", op="gt", value=0.5)`

#### Scenario: Out-of-range decimal value is rejected

- **WHEN** `## invariants` contains
  `- concept_gram_tier_separation >= 1.5`
- **THEN** the parser raises a parse error naming the
  out-of-range value

### Requirement: Conditional gate effects

A conditional gate effect SHALL be of the form
`if <condition> [and <condition> [and …]] : <gate>` where each
`<condition>` is `bits[<int>] == <0|1>`. The parser SHALL produce a
single `QEffectConditional` whose `conditions` attribute is the
ordered list of `(bit_idx, value)` pairs and whose `gate` attribute
is the parsed `<gate>`.

The legacy single-condition form (`if bits[i] == v: gate`) SHALL
parse to a `QEffectConditional` with a one-element `conditions`
list. The legacy `bit_idx` and `value` attributes SHALL remain
populated from `conditions[0]` for backward compatibility with
read-only consumers.

Whitespace around `==`, `and`, `:`, `[`, and `]` SHALL be flexible
(zero or more spaces). The keyword `and` SHALL be lowercase.

A conditional gate effect that lists the same `bits[i]` index twice
with conflicting values SHALL be rejected as a parse error citing
the offending bit index and both declared values.

#### Scenario: Single-condition form parses unchanged

- **WHEN** an action declares `if bits[0] == 1: X(qs[0])`
- **THEN** the parser produces a `QEffectConditional` with
  `conditions == [(0, 1)]`, `bit_idx == 0`, and `value == 1`

#### Scenario: AND-conjoined two-bit condition

- **WHEN** an action declares `if bits[0] == 1 and bits[1] == 1: X(qs[1])`
- **THEN** the parser produces a `QEffectConditional` with
  `conditions == [(0, 1), (1, 1)]` and the gate parsed normally

#### Scenario: Mixed-value AND-conjoined condition

- **WHEN** an action declares `if bits[0] == 1 and bits[1] == 0: X(qs[0])`
- **THEN** the resulting `conditions == [(0, 1), (1, 0)]`

#### Scenario: Three-bit AND-conjoined condition

- **WHEN** an action declares
  `if bits[0] == 1 and bits[1] == 0 and bits[2] == 1: X(qs[3])`
- **THEN** the resulting `conditions == [(0, 1), (1, 0), (2, 1)]`

#### Scenario: Conflicting clauses are rejected

- **WHEN** an action declares
  `if bits[0] == 1 and bits[0] == 0: X(qs[0])`
- **THEN** the parser raises a parse error naming `bits[0]` and the
  conflicting values `1` and `0`

#### Scenario: Whitespace flexibility

- **WHEN** an action declares
  `if bits[0]==1  and  bits[1] == 1: X(qs[1])`
- **THEN** the parser produces the same `QEffectConditional` as the
  canonical single-spaced form

### Requirement: Assertion Policy Section

The parser SHALL accept an optional `## assertion policy` section
containing a Markdown table whose first column is `Setting` and whose
second column is `Value`. Trailing columns (e.g. `Notes`) SHALL be
parsed and discarded. The recognized settings and their value types
are:

- `shots_per_assert: int` (default `512`)
- `confidence: float in [0, 1]` (default `0.99`)
- `on_failure: 'error' | 'warn'` (default `'error'`)
- `backend: 'auto' | <backend name>` (default `'auto'`)

Unknown setting names SHALL produce an `unknown_assertion_policy_setting`
parser error referencing the row. A value that fails type validation
SHALL produce an `assertion_policy_value_error` referencing the row,
the setting, and the offending value.

If the section is absent, the parser SHALL produce
`QMachine.assertion_policy = AssertionPolicy()` with the four defaults
above. If the section is present, the parser SHALL produce an
`AssertionPolicy` with the specified overrides applied to those
defaults.

#### Scenario: Default policy when section is absent

- **WHEN** a machine declares `[assert: …]` annotations but no
  `## assertion policy` section
- **THEN** the parsed `QMachine` has
  `assertion_policy = AssertionPolicy(shots_per_assert=512, confidence=0.99, on_failure='error', backend='auto')`

#### Scenario: Single-setting override

- **WHEN** the section contains a row `| shots_per_assert | 128 |`
- **THEN** the parsed `AssertionPolicy` has `shots_per_assert=128` and
  retains all other defaults

#### Scenario: All four settings overridden

- **WHEN** the section contains rows for all four recognized settings
- **THEN** the parsed `AssertionPolicy` has all four fields set to the
  declared values

#### Scenario: Unknown setting produces a parse error

- **WHEN** the section contains a row `| basis_pref | Z |`
- **THEN** the parser emits `unknown_assertion_policy_setting`
  referencing the row and naming `basis_pref`

#### Scenario: Out-of-range confidence produces a parse error

- **WHEN** the section contains a row `| confidence | 1.5 |`
- **THEN** the parser emits `assertion_policy_value_error` referencing
  `confidence` and the offending value `1.5`

#### Scenario: Notes column is accepted and ignored

- **WHEN** the section contains a header `| Setting | Value | Notes |`
  and a row `| shots_per_assert | 256 | fast for CI |`
- **THEN** the parsed `AssertionPolicy` has `shots_per_assert=256` and
  the notes content is not stored on the AST

### Requirement: Invoke State Annotation

The parser SHALL accept `invoke: <ChildMachineName>(<arg_bindings>)
[shots=<int>]` as a state-level annotation, alongside `[initial]`
and `[final]`. An invoke annotation marks a state as delegating to
another machine declared in the same file. Argument bindings take
the form `<child_param>=<parent_expr>`, comma-separated; the RHS
is either a bare parent-context-field identifier or an indexed
reference (`theta[0]`). Return bindings appear in the state's
body after a `returns:` line, with the analogous
`<parent_field>=<child_return>` form.

An invoke state SHALL NOT also be `[initial]` or `[final]`. A
state SHALL have at most one `invoke:` annotation. Transitions
out of an invoke state SHALL fire only after the child has
completed.

#### Scenario: Classical child with keyword args

- **WHEN** a state heading is
  `## state |train> [invoke: EpochRunner(epoch=iteration, lr=eta)]`
- **THEN** the resulting `QStateDef` has an `invoke` field of kind
  `QInvoke` with child `EpochRunner`, arg bindings
  `{epoch: iteration, lr: eta}`, and `shots=None`

#### Scenario: Quantum child with shots and returns

- **WHEN** a state body declares
  `## state |train> [invoke: QForward(theta=theta) shots=1024]` with a
  body line `> returns: bits_0_prob=prob_bits_0, bits_0_hist=hist_bits_0`
- **THEN** the state's `QInvoke` has `shots=1024`, return bindings
  `{bits_0_prob: prob_bits_0, bits_0_hist: hist_bits_0}`

#### Scenario: Invoke plus initial is a parse error

- **WHEN** a state heading is
  `## state |start> [initial] [invoke: Init()]`
- **THEN** the parser emits a structured error — an invoke state
  cannot also be initial or final

### Requirement: Returns Section

The parser SHALL accept an optional `## returns` section whose
table has `Name`, `Type`, and optional `Statistics` columns. Each
return row declares one value the machine exposes to a caller.
`Name` is a context-field identifier or an indexed reference
(`bits[0]`); `Type` uses the grammar from the `## context` section;
`Statistics` is a comma-separated list from the vocabulary
`{expectation, histogram, variance}`.

The `Statistics` column SHALL be populated only on machines that
also perform measurement (contain a transition with a
`measurement` or `mid_circuit_measure` effect). A non-empty
`Statistics` cell on a non-measurement machine is a parse error.

#### Scenario: Classical machine declares simple returns

- **WHEN** a machine has
  `## returns` with one row `| converged | bool | |`
- **THEN** the machine's `returns` list has one `QReturnDef` with
  `name="converged"`, `type=QTypeScalar(kind="bool")`, and empty
  `statistics`

#### Scenario: Quantum machine declares aggregate statistics

- **WHEN** a measurement-bearing machine declares a returns row
  `| bits[0] | bit | expectation, histogram |`
- **THEN** the `QReturnDef` has `name="bits[0]"`, `type=bit`, and
  `statistics=["expectation", "histogram"]`

#### Scenario: Statistics on a non-measurement machine rejected

- **WHEN** a machine with no measurement effects declares a
  returns row with `Statistics` = `expectation`
- **THEN** the parser emits a structured error — statistics
  annotations require a measurement-bearing machine

### Requirement: Execution Mode Flag

The parser SHALL accept an optional `shots=<int>` modifier on an
`invoke:` annotation. The integer SHALL be at least 1; otherwise
a parse error is emitted. Parse-time enforcement of
"classical-child-rejects-shots" is not possible because the
child's kind is unknown at parse time; that rule is enforced by
the verifier's composition stage.

#### Scenario: Shots=0 rejected at parse

- **WHEN** a state heading is
  `## state |s> [invoke: Child() shots=0]`
- **THEN** the parser emits a structured error — shots must be at
  least 1

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

### Requirement: Noise Model Section

The parser SHALL recognize a top-level `## noise_model` section declared as a markdown table with columns `Channel`, `Target`, and `Parameters`, producing a `NoiseModelSection` whose `channels` is a list of `NoiseChannel(kind, target, parameters)` in row order.

The `Channel` column SHALL be one of the closed set `depolarizing | amplitude_damping | phase_damping | thermal | readout_error | bit_flip | phase_flip | pauli`. The `Target` column SHALL be one of the closed selector set `all_gates | single_qubit_gates | two_qubit_gates | all_measurements | all_qubits | qs[N] | qs[role:R] | gates[A,B,...]`, parsed into a tagged selector value (`AllGates | SingleQubitGates | TwoQubitGates | AllMeasurements | AllQubits | QubitIndex(int) | QubitRole(str) | GateList(list)`). The `Parameters` column SHALL be parsed as free-form `k=v` pairs into a dict; time-domain values accept the SI suffixes `ns | us | ms` and a bare number SHALL be interpreted as `ns`. The parser SHALL NOT enforce per-channel parameter schemas (that is the verifier's job); it preserves the parsed rows for verification.

#### Scenario: Multi-row section parses into ordered channels

- **WHEN** a machine declares a `## noise_model` table with rows `depolarizing | single_qubit_gates | p=0.001`, `depolarizing | two_qubit_gates | p=0.012`, and `readout_error | all_measurements | p0given1=0.02, p1given0=0.04`
- **THEN** `machine.noise_model.channels` has length 3 in that order, with kinds `depolarizing`, `depolarizing`, `readout_error` and targets `SingleQubitGates`, `TwoQubitGates`, `AllMeasurements`

#### Scenario: Time-domain parameter carries its unit

- **WHEN** a row is `thermal | all_qubits | T1=100us, T2=80us`
- **THEN** the channel's parameters resolve `T1` and `T2` to times of 100 microseconds and 80 microseconds (a bare number would be interpreted as nanoseconds)

#### Scenario: Role and gate-list selectors parse

- **WHEN** rows target `qs[role:ancilla]` and `gates[H,CNOT]`
- **THEN** the parsed selectors are `QubitRole("ancilla")` and `GateList(["H", "CNOT"])` (schema validity is checked by the verifier, not the parser)

### Requirement: Qubit Role Tags

The parser SHALL accept an optional colon-delimited role tag on each element of a `## context` `list<qubit>` default, drawn from the closed vocabulary `data | ancilla | syndrome | communication`, and SHALL record a per-qubit role on the machine; an element without a tag SHALL default to role `data`.

Roles are stored as a per-qubit structure on the machine (one role per declared qubit, in declaration order) — not on the shared `QTypeQubit` type. A range shorthand `aN..aM:role` (shared alphabetic prefix, inclusive integer suffixes) SHALL expand to the flat per-element list with that role. A tag that is not in the closed vocabulary — including the reserved-but-not-yet-supported `coin` and `position` — SHALL raise `UNKNOWN_QUBIT_ROLE` naming the offending element. An untagged register SHALL parse and verify identically to today (all elements `data`).

#### Scenario: Inline role tags parse to per-qubit roles

- **WHEN** `## context` declares `| qubits | list<qubit> | [q0:data, q1:ancilla, q2:ancilla] |`
- **THEN** the machine records roles `["data", "ancilla", "ancilla"]` (one per qubit, in order)

#### Scenario: Untagged elements default to data (backward compatible)

- **WHEN** `## context` declares `| qubits | list<qubit> | [q0, q1] |`
- **THEN** both qubits have role `data` and the machine parses and verifies identically to before this change

#### Scenario: Range shorthand expands

- **WHEN** `## context` declares `| qubits | list<qubit> | [q0..q2:data, q3..q4:ancilla] |`
- **THEN** the machine records five qubits with roles `["data", "data", "data", "ancilla", "ancilla"]`

#### Scenario: Unknown or reserved role rejected

- **WHEN** an element is tagged with an unknown keyword, or with the reserved `coin` / `position` (not yet supported)
- **THEN** the parser raises `UNKNOWN_QUBIT_ROLE` naming the offending element

#### Scenario: Malformed range rejected

- **WHEN** a range is not a shared alphabetic prefix with inclusive integer suffixes (e.g. `q0..q5a:data`, `q0..x9:data`, or a descending `q5..q0:data`)
- **THEN** the parser raises a structured parse error for the offending element rather than silently producing a partial register

### Requirement: Bounded Loop Annotation

The parser SHALL recognize a `[loop <expr>]` or `[loop until: <predicate>]` annotation on a `## state` heading, filling the reserved `[loop …]` grammar slot, and SHALL attach a `QLoopAnnotation` (kind `fixed` or `adaptive`) to that state.

For `[loop <expr>]` (fixed), `<expr>` is a numeric literal, a context-field reference, or a closed-form expression over context fields and the standard math functions (`sqrt`, `ceil`, `floor`, `pi`), parsed by the existing classical-context expression parser and evaluated once at compile time to a fixed integer bound. For `[loop until: <predicate>]` (adaptive), `<predicate>` is a classical-context boolean expression (it may reference context fields and call a `## actions` function whose return type is `bool`). The annotation composes with `[initial]`/`[final]` on the same heading. A state with no `[loop …]` annotation behaves exactly as before this change.

The parser SHALL recognize two Action-column tags: `loop_done` (the transition that exits the loop) and `loop_back` (the back-edge that re-enters the body), each settable alongside a real action name (e.g. `measure_all, loop_done`), recorded as `loop_done` / `loop_back` flags on the `QTransition`.

#### Scenario: Fixed-count loop annotation parses

- **WHEN** a heading is `## state |amplified> [loop ceil(pi/4 * sqrt(N))]`
- **THEN** the state carries a `QLoopAnnotation` of kind `fixed` whose bound expression is `ceil(pi/4 * sqrt(N))`

#### Scenario: Adaptive loop annotation parses

- **WHEN** a heading is `## state |collected> [loop until: rank >= n - 1]`
- **THEN** the state carries a `QLoopAnnotation` of kind `adaptive` whose predicate is `rank >= n - 1`

#### Scenario: Loop transition tags recognized

- **WHEN** a transition's Action cell is `measure_all, loop_done` and another is `identity, loop_back`
- **THEN** the first transition has `loop_done = True` (with action `measure_all`) and the second has `loop_back = True`

#### Scenario: Unannotated state is unchanged

- **WHEN** a state heading carries no `[loop …]` annotation
- **THEN** its `QLoopAnnotation` is absent and the machine parses and compiles identically to before this change

