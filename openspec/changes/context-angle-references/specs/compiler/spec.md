## MODIFIED Requirements

### Requirement: Parameterized Gate Handling

The compiler SHALL use a single canonical rotation-gate syntax,
`R{X|Y|Z}(qs[N], <angle>)` (qubit first, angle second), across the
markdown parser, the Qiskit compiler's effect-string parser, and the
dynamic verifier's effect-string parser. All three sites SHALL share
a single symbolic angle evaluator (`q_orca.angle.evaluate_angle`) that
accepts the grammar defined in the language spec, INCLUDING
context-field references resolved against the current machine's
`## context` table. Any rotation-gate effect that does not match the
canonical grammar SHALL produce a parser error, not a silent `0.0`
fallback.

The shared evaluator SHALL receive the same context map at all three
sites: a mapping `{name: float}` built from context fields whose type
is `float` or `int` and whose default value parses as a number. This
guarantees that the same machine source produces identical
`parameter` values whether reached via the parser, the Qiskit
compiler, or the dynamic verifier.

The emitted artifacts SHALL remain:

- QASM: `rx(<float>) q[i];`, `ry(<float>) q[i];`, `rz(<float>) q[i];`
- Qiskit: `qc.rx(<float>, i)`, `qc.ry(<float>, i)`, `qc.rz(<float>, i)`

The AST's `QuantumGate.parameter` field SHALL be populated with the
evaluated float for every rotation-gate action.

#### Scenario: Rotation gate argument order is canonical across stages

- **WHEN** a user writes `Rx(qs[0], pi/4)` in an action effect
- **THEN** the parser, the Qiskit compiler's effect parser, and the
  dynamic verifier's effect parser all recognize it identically and
  produce `QuantumGate(kind="Rx", targets=[0], parameter=math.pi/4)`

#### Scenario: Parser populates AST rotation-gate field

- **WHEN** a machine contains an action with effect `Ry(qs[2], pi/2)`
- **THEN** after parsing, `action.gate` is `QuantumGate(kind="Ry",
  targets=[2], parameter=math.pi/2)` — not `None`

#### Scenario: QASM emission for symbolic angle

- **WHEN** the compiler encounters a `QuantumGate(kind="Rz",
  targets=[0], parameter=math.pi/4)`
- **THEN** `compile_to_qasm` emits a line containing
  `rz(0.7853981633974483) q[0];`

#### Scenario: Qiskit emission for symbolic angle

- **WHEN** the compiler encounters a `QuantumGate(kind="Rx",
  targets=[1], parameter=math.pi/2)`
- **THEN** `compile_to_qiskit` emits a line containing
  `qc.rx(1.5707963267948966, 1)`

#### Scenario: Dynamic verifier uses canonical grammar

- **WHEN** the dynamic verifier extracts gates from
  `Rx(qs[0], 1.5708)`
- **THEN** the QuTiP path produces the correct rotated state for that
  angle (not the identity produced by a silent `0.0` fallback)

#### Scenario: All three sites resolve context references identically

- **WHEN** a machine declares `| gamma | float | 0.5 |` in `## context`
  and an action's effect is `Rx(qs[0], gamma)`
- **THEN** the parsed AST, the Qiskit-compiled script's
  `qc.rx(0.5, 0)` line, and the dynamic verifier's QuTiP simulation
  all use `parameter == 0.5` for that gate
