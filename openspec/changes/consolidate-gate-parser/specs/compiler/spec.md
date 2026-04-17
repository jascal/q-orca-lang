## MODIFIED Requirements

### Requirement: Parameterized Gate Handling

The compiler SHALL use a single canonical rotation-gate syntax,
`R{X|Y|Z}(qs[N], <angle>)` (qubit first, angle second), across the
markdown parser, the Qiskit compiler's effect-string parser, and the
dynamic verifier's effect-string parser. All three sites SHALL share
a single symbolic angle evaluator (`q_orca.angle.evaluate_angle`) and
a single shared gate-effect-string parser (`q_orca.effect_parser`).
All effect-string regexes SHALL be owned by the shared parser; call
sites SHALL NOT maintain their own regex blocks.

Any rotation-gate effect that does not match the canonical grammar
SHALL produce a parser error, not a silent `0.0` fallback.

The emitted artifacts SHALL remain:

- QASM: `rx(<float>) q[i];`, `ry(<float>) q[i];`, `rz(<float>) q[i];`
- Qiskit: `qc.rx(<float>, i)`, `qc.ry(<float>, i)`, `qc.rz(<float>, i)`

The AST's `QuantumGate.parameter` field SHALL be populated with the
evaluated float for every rotation-gate action.

#### Scenario: Shared parser is the single source of truth

- **WHEN** a gate-effect string is parsed by any site (markdown parser,
  Qiskit compiler, QASM compiler, or dynamic verifier)
- **THEN** parsing delegates to `q_orca.effect_parser.parse_single_gate`
  (or `parse_effect_string` for semicolon-separated effects) and the
  call site only adapts the returned `ParsedGate` into its preferred
  shape

#### Scenario: Regex ordering cannot demote controlled gates

- **WHEN** the shared parser receives `CRx(qs[0], qs[1], beta)`
- **THEN** it matches the two-qubit parameterized branch (because all
  patterns are anchored with `^` and two-qubit parameterized gates
  precede single-qubit rotation in the pattern table) and produces
  `ParsedGate(name="CRX", targets=(1,), controls=(0,), parameter=<beta>)`

#### Scenario: Two-qubit parameterized gates are never silently dropped

- **WHEN** the shared parser receives `RZZ(qs[0], qs[1], gamma)`
- **THEN** it produces `ParsedGate(name="RZZ", targets=(0, 1),
  controls=(), parameter=<gamma>)` and the dynamic verifier's gate
  sequence contains a corresponding gate-dict (not an empty step)

#### Scenario: Adding a new gate kind is a one-file change

- **WHEN** a developer adds a new gate kind
- **THEN** the change is a single new entry in the shared parser's
  pattern table and a single new entry in `tests/fixtures/effect_strings.py`;
  no edits to the markdown parser, the Qiskit/QASM compiler, or the
  dynamic verifier are required for parsing to work

#### Scenario: Rotation gate argument order is canonical across stages

- **WHEN** a user writes `Rx(qs[0], pi/4)` in an action effect
- **THEN** the parser, the Qiskit compiler's effect parser, and the
  dynamic verifier's effect parser all recognize it identically via
  the shared parser and produce a gate with `name` ≡ `"Rx"`,
  `targets ≡ (0,)`, `parameter ≡ math.pi/4`

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
