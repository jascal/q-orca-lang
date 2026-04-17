## MODIFIED Requirements

### Requirement: Shared Gate Kind Coverage

All three backends SHALL handle the same gate kinds by reading them
from the effect string:

- Single-qubit: `H`, `X`, `Y`, `Z`, `T`, `S`, `Rx`, `Ry`, `Rz`
- Two-qubit: `CNOT`/`CX`, `CZ`, `SWAP`
- Three-qubit: `CCNOT`/`CCX`, `CCZ`, `CSWAP`
- Many-controlled: `MCX`, `MCZ` (variable arity, ≥ 3 args, last is target)

Two-qubit parameterized: `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ`.

Measurements SHALL be parsed from `measure(qs[i, ...])` or `M(qs[i])`
and emitted as one measurement op per target.

#### Scenario: CNOT translation across backends

- **WHEN** an action's effect is `CNOT(qs[0], qs[1])`
- **THEN** QASM emits `cx q[0], q[1];`, Qiskit emits `qc.cx(0, 1)`,
  and Mermaid renders the action as a transition label `... / apply_CNOT`

#### Scenario: CCZ translation across backends

- **WHEN** an action's effect is `CCZ(qs[0], qs[1], qs[2])`
- **THEN** QASM emits the H-CCX-H sandwich
  `h q[2]; ccx q[0], q[1], q[2]; h q[2];` and Qiskit emits
  `qc.h(2); qc.ccx(0, 1, 2); qc.h(2)`

#### Scenario: MCX with three controls

- **WHEN** an action's effect is `MCX(qs[0], qs[1], qs[2], qs[3])`
- **THEN** QASM emits `ctrl(3) @ x q[0], q[1], q[2], q[3];` and
  Qiskit emits `qc.mcx([0, 1, 2], 3)`

#### Scenario: MCZ with three controls

- **WHEN** an action's effect is `MCZ(qs[0], qs[1], qs[2], qs[3])`
- **THEN** QASM emits the H-sandwich
  `h q[3]; ctrl(3) @ x q[0], q[1], q[2], q[3]; h q[3];` and Qiskit
  emits `qc.h(3); qc.mcx([0, 1, 2], 3); qc.h(3)`

## ADDED Requirements

### Requirement: Multi-Controlled Gate Emission Conventions

All many-controlled `Z`-flavored gates (`CCZ`, `MCZ`) SHALL be lowered
to a Hadamard sandwich on the target qubit around the corresponding
`X`-flavored gate:

```
CCZ(c0, c1, t)         ≡ H(t); CCX(c0, c1, t); H(t)
MCZ(c0, c1, ..., t)    ≡ H(t); MCX(c0, c1, ..., t); H(t)
```

The Qiskit emitter SHALL use `qc.mcx([controls...], target)` (the list
form) for `MCX`. The QASM emitter SHALL use `ctrl(N) @ x` for `MCX`,
where `N` is the number of controls. Neither emitter SHALL depend on a
backend-specific `ccz` alias.

The CCNOT emitter MUST place the target as the third positional
argument (`qc.ccx(c0, c1, t)`), matching the parser's convention that
the last subscript is the target.

#### Scenario: CCNOT canonical control/target order

- **WHEN** an action's effect is `Toffoli(qs[0], qs[1], qs[2])`
- **THEN** the Qiskit emitter produces `qc.ccx(0, 1, 2)` — qubit 2 is
  the target, qubits 0 and 1 are controls

#### Scenario: MCX must have at least two controls

- **WHEN** the parser produces a `QuantumGate(kind="MCX", controls=[0],
  targets=[1])` (one control, the parser would normally reject this but
  it is constructed programmatically)
- **THEN** the Qiskit emitter raises a `ValueError` referencing the
  required minimum control count

### Requirement: Qiskit BasicSimulator Basis Transpilation

The Qiskit script's shots-mode emission SHALL run a `transpile()` pass
over the measurement-augmented circuit before invoking
`BasicSimulator`. The transpile basis SHALL include the gates the
`BasicSimulator` natively executes:

```
['h', 'x', 'y', 'z', 's', 'sdg', 't', 'tdg', 'cx', 'cz', 'ccx',
 'rx', 'ry', 'rz', 'crx', 'cry', 'crz', 'swap', 'measure']
```

The transpile pass SHALL run regardless of whether the circuit contains
many-controlled gates; circuits already in the basis become a no-op
through `transpile`. The analytic (`Statevector`) emission path SHALL
NOT include the transpile pass — `Statevector` accepts the un-decomposed
circuit directly.

When `qiskit_aer` is available and a noise model is present the
`AerSimulator` path SHALL also receive the transpiled circuit so that
noise model gate-key matching is unaffected.

#### Scenario: Shots-mode MCZ run

- **WHEN** a machine with an `MCZ` action is compiled with
  `QSimulationOptions(analytic=False, shots=1024, run=True)` and the
  generated script is executed
- **THEN** the simulator does not raise
  `'basic_simulator encountered unrecognized operation "mcx"'` and
  produces a `counts` dictionary

#### Scenario: Analytic-mode MCZ run skips transpile

- **WHEN** the same machine is compiled with
  `QSimulationOptions(analytic=True)`
- **THEN** the generated script reads probabilities from `Statevector`
  with no `transpile` call in the analytic branch

### Requirement: Parametric Action Expansion

The compiler SHALL expand each call-form transition (`name(arg1, ...)`)
by substituting the bound argument values into a copy of the
referenced action's effect string at the *point of use*, then parsing
the resulting fully-literal effect string with the standard
gate-effect parser into a list of `QuantumGate` values. Expansion
SHALL produce no remaining identifier subscripts and no unresolved
angle references.

Each call site SHALL produce its own independent gate sequence in the
emitted artifact. The same parameterized action SHALL be expandable
zero, one, or many times across a machine without altering the
underlying action definition.

Expansion errors (out-of-range integer subscript, unparseable
substituted angle, type mismatch) SHALL be reported at the
transition's source location with the action name and the offending
argument identified, not at the action definition.

#### Scenario: Twelve call sites of the same parametric action

- **WHEN** a machine declares
  `query_concept | (qs, c: int) -> qs | Hadamard(qs[c])` and twelve
  transitions invoke `query_concept(0)` ... `query_concept(11)`
- **THEN** the compiled QASM contains twelve distinct `h q[i];` lines
  for `i ∈ [0, 11]`, each emitted at its corresponding transition's
  position in the BFS-derived gate sequence

#### Scenario: Out-of-range subscript in expansion

- **WHEN** a machine has 4 qubits, a parametric action
  `query_concept | (qs, c: int) -> qs | Hadamard(qs[c])`, and a
  transition `query_concept(7)`
- **THEN** the compiler emits a structured error referencing the
  transition's source location, the action name `query_concept`, and
  the bound value `c=7` exceeding the inferred qubit count

#### Scenario: Bound angle expansion into rotation gate

- **WHEN** a parametric action
  `rotate | (qs, theta: angle) -> qs | Rx(qs[0], theta)` is invoked
  as `rotate(pi/4)`
- **THEN** the expanded effect string is `Rx(qs[0], pi/4)` and the
  resulting `QuantumGate` has `kind="Rx"`, `targets=[0]`,
  `parameter == math.pi/4`

#### Scenario: Mixed parametric and bare actions in the same machine

- **WHEN** a machine has both `apply_h | (qs) -> qs | Hadamard(qs[0])`
  and `query_concept | (qs, c: int) -> qs | Hadamard(qs[c])` with
  transitions referencing both
- **THEN** the bare action emits its single fixed gate, the parametric
  action emits one gate per call site, and Mermaid labels each
  transition with the source-form Action cell text (preserving the
  argument list for parametric calls)
