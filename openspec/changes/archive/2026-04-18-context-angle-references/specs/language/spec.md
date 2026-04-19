## MODIFIED Requirements

### Requirement: Gate Effect Grammar

Effect strings SHALL be parsed into `QuantumGate` values. The parser's
`_parse_gate_from_effect` function SHALL recognize the following source
syntaxes and map them to gate kinds:

- `Hadamard(qs[i])` or `H(qs[i])` → `H`
- `CNOT(qs[c], qs[t])` → `CNOT`
- `X(qs[i])`, `Y(qs[i])`, `Z(qs[i])`, `T(qs[i])`, `S(qs[i])`
- `Rx(qs[i], <angle>)`, `Ry(qs[i], <angle>)`, `Rz(qs[i], <angle>)` → `Rx`/`Ry`/`Rz`
- `CRx(qs[c], qs[t], <angle>)`, `CRy(...)`, `CRz(...)` → `CRx`/`CRy`/`CRz`
- `RXX(qs[i], qs[j], <angle>)`, `RYY(...)`, `RZZ(...)` → `RXX`/`RYY`/`RZZ`
- `measure(qs[i, ...])` or `M(qs[i])` → `Measurement`

The canonical rotation-gate argument order SHALL be qubit-first,
angle-second. `<angle>` SHALL be parsed by the symbolic angle
evaluator, which accepts: decimal literals, `pi`, `pi/<int>`,
`<int>*pi`, `<int>*pi/<int>`, a leading minus sign on any of the
above, AND context-field references resolved against the current
machine's `## context` table. Supported context-reference forms are:

- bare identifier: `gamma`
- leading minus: `-gamma`
- integer scaling: `2*gamma`, `2gamma`, `gamma/2`
- π scaling: `gamma*pi`, `pi*gamma`

A context reference SHALL resolve only against context fields of type
`float` or `int` whose default value parses as a number. The literal
forms (`pi`, `pi/4`, etc.) SHALL be tried first, so a literal is never
shadowed by a same-named context field.

Any rotation-gate effect whose argument order or angle does not match
SHALL produce a parser error rather than silently coercing to `0.0`.
The error message for an unrecognized identifier SHALL name both the
identifier and (when known) whether the field exists but has a
non-numeric default.

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

#### Scenario: Bare context-field identifier

- **WHEN** the machine declares `| gamma | float | 0.5 |` in `## context`
  and an action's effect is `Rx(qs[0], gamma)`
- **THEN** the parsed `QuantumGate` has `kind="Rx"`, `targets=[0]`,
  and `parameter == 0.5`

#### Scenario: Negated context-field identifier

- **WHEN** the machine declares `| theta | float | 0.7 |` and an
  action's effect is `Ry(qs[1], -theta)`
- **THEN** the parsed `QuantumGate` has `parameter == -0.7`

#### Scenario: Integer scaling of a context field

- **WHEN** the machine declares `| beta | float | 0.25 |` and an
  action's effect is `Rz(qs[0], 2*beta)`
- **THEN** the parsed `QuantumGate` has `parameter == 0.5`

#### Scenario: Division of a context field by an integer

- **WHEN** the machine declares `| theta | float | 1.6 |` and an
  action's effect is `Rx(qs[0], theta/2)`
- **THEN** the parsed `QuantumGate` has `parameter == 0.8`

#### Scenario: π scaling of a context field

- **WHEN** the machine declares `| frac | float | 0.5 |` and an
  action's effect is `Rz(qs[0], frac*pi)`
- **THEN** the parsed `QuantumGate` has `parameter == math.pi / 2`

#### Scenario: Two-qubit parameterized gate uses context reference

- **WHEN** the machine declares `| gamma | float | 0.5 |` and an
  action's effect is `RZZ(qs[0], qs[1], gamma)`
- **THEN** the parsed `QuantumGate` has `kind="RZZ"`,
  `targets=[0, 1]`, and `parameter == 0.5`

#### Scenario: Unrecognized identifier produces a precise error

- **WHEN** an action's effect is `Rx(qs[0], theta_custom)` and no
  `theta_custom` field is declared in `## context`
- **THEN** the parser emits a parse error referencing the missing
  identifier and the accepted angle grammar

#### Scenario: Identifier with non-numeric default produces an error

- **WHEN** the machine declares `| qubits | list<qubit> | [q0, q1] |`
  and an action's effect is `Rx(qs[0], qubits)`
- **THEN** the parser emits a parse error explaining that `qubits` is
  not a numeric context field
