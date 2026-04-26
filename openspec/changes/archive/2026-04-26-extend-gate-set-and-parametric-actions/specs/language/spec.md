## MODIFIED Requirements

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

## ADDED Requirements

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
