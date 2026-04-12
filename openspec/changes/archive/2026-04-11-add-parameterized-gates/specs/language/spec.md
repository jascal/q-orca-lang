## MODIFIED Requirements

### Requirement: Gate Effect Grammar

Effect strings SHALL be parsed into `QuantumGate` values. The parser's
`_parse_gate_from_effect` function SHALL recognize the following source
syntaxes and map them to gate kinds:

- `Hadamard(qs[i])` or `H(qs[i])` → `H`
- `CNOT(qs[c], qs[t])` → `CNOT`
- `X(qs[i])`, `Y(qs[i])`, `Z(qs[i])`, `T(qs[i])`, `S(qs[i])`
- `Rx(qs[i], <angle>)`, `Ry(qs[i], <angle>)`, `Rz(qs[i], <angle>)` → `Rx`/`Ry`/`Rz`
- `measure(qs[i, ...])` or `M(qs[i])` → `Measurement`

The canonical rotation-gate argument order SHALL be qubit-first,
angle-second. `<angle>` SHALL be parsed by the symbolic angle
evaluator, which accepts: decimal literals, `pi`, `pi/<int>`,
`<int>*pi`, `<int>*pi/<int>`, and a leading minus sign on any of the
above. Any rotation-gate effect whose argument order or angle does not
match SHALL produce a parser error rather than silently coercing to
`0.0`.

#### Scenario: CNOT effect

- **WHEN** an action's effect is `CNOT(qs[0], qs[1])`
- **THEN** the parsed `QuantumGate` has `kind="CNOT"`, `targets=[1]`,
  `controls=[0]`

#### Scenario: Rotation with decimal angle

- **WHEN** an action's effect is `Rx(qs[0], 1.5708)`
- **THEN** the parsed `QuantumGate` has `kind="Rx"`, `targets=[0]`,
  and `parameter ≈ 1.5708`

#### Scenario: Rotation with symbolic angle

- **WHEN** an action's effect is `Ry(qs[1], pi/4)`
- **THEN** the parsed `QuantumGate` has `kind="Ry"`, `targets=[1]`,
  and `parameter == math.pi / 4`

#### Scenario: Rotation with compound symbolic angle

- **WHEN** an action's effect is `Rz(qs[0], 3*pi/4)`
- **THEN** the parsed `QuantumGate` has `kind="Rz"`, `targets=[0]`,
  and `parameter == 3 * math.pi / 4`

#### Scenario: Wrong argument order produces an error

- **WHEN** an action's effect is `Rx(1.5708, qs[0])` (angle-first)
- **THEN** the parser emits a parse error and does not produce a
  `QuantumGate` silently populated with `parameter=0.0`

#### Scenario: Unrecognized symbolic form produces an error

- **WHEN** an action's effect is `Rx(qs[0], theta_custom)`
- **THEN** the parser emits a parse error referencing the symbolic
  angle grammar, because the context-reference form is not yet
  supported
