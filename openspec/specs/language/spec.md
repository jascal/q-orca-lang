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

