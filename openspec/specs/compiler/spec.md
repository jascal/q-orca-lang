# Compiler Capability

## Purpose

The Q-Orca compiler turns a parsed `QMachineDef` into one of three
artifacts: an OpenQASM 3.0 program, a runnable Qiskit Python script, or
a Mermaid state diagram. The three backends share effect-string parsing
via `q_orca/compiler/qiskit.py::_parse_effect_string`.

## Requirements

### Requirement: Three Backend Targets

The compiler SHALL expose three backend entry points:

- `compile_to_qasm(machine)` → OpenQASM 3.0 string
- `compile_to_qiskit(machine, options)` → Qiskit Python script string
- `compile_to_mermaid(machine)` → Mermaid `stateDiagram-v2` string

#### Scenario: Qiskit script with simulation options

- **WHEN** `compile_to_qiskit(machine, QSimulationOptions(analytic=True))`
  is called on a Bell-pair machine
- **THEN** the returned script contains `qc = QuantumCircuit(2)`, the
  necessary `qc.h(...)` and `qc.cx(...)` calls, and produces a
  probability dictionary on the final `print(json.dumps(result, ...))`

### Requirement: Shared Gate Kind Coverage

All three backends SHALL handle the same gate kinds by reading them
from the effect string:

- Single-qubit: `H`, `X`, `Y`, `Z`, `T`, `S`, `Rx`, `Ry`, `Rz`
- Two-qubit: `CNOT`/`CX`, `CZ`, `SWAP`
- Three-qubit: `CCNOT`/`CCX`, `CSWAP`

Measurements SHALL be parsed from `measure(qs[i, ...])` or `M(qs[i])`
and emitted as one measurement op per target.

#### Scenario: CNOT translation across backends

- **WHEN** an action's effect is `CNOT(qs[0], qs[1])`
- **THEN** QASM emits `cx q[0], q[1];`, Qiskit emits `qc.cx(0, 1)`,
  and Mermaid renders the action as a transition label `... / apply_CNOT`

### Requirement: Qubit Count Inference

All backends SHALL infer the total qubit count using the same
procedure: (1) `context` field `qubits: list<qubit>` with a default
like `[q0, q1, q2]` — use the list length; (2) `context` fields
`n: int` plus `ancilla: qubit` — return `n + 1`; (3) the maximum
length of a binary ket in any `## state` name or expression (e.g.
`|110>` → 3); (4) the maximum length of any probability-guard
bitstring; (5) fallback of 1.

#### Scenario: Qubit count from explicit list

- **WHEN** `## context` contains `| qubits | list<qubit> | [q0, q1, q2] |`
- **THEN** all three backends infer a qubit count of 3

#### Scenario: Qubit count from ket states

- **WHEN** a machine has a state `|110>` and no explicit qubits field
- **THEN** all three backends infer a qubit count of 3

### Requirement: OpenQASM 3.0 Output

The QASM backend SHALL emit `OPENQASM 3.0;` with
`include "stdgates.inc";`, declare `qubit[N] q;` sized to the inferred
qubit count, and additionally declare `bit[N] c;` whenever the machine
contains either an explicit measurement action or an event whose name
contains `measure` or `collapse`.

#### Scenario: Measurement triggers bit register

- **WHEN** a machine has an event named `measure`
- **THEN** the QASM output declares `bit[N] c;` and emits
  `c[i] = measure q[i];` for each qubit

### Requirement: Qiskit Script Simulation Options

The Qiskit backend SHALL accept a `QSimulationOptions` dataclass with
fields `analytic`, `shots`, `verbose`, `skip_qutip`, `skip_noise`,
`run`. In analytic mode the script SHALL produce a probability
dictionary keyed by bitstrings via `Statevector`. In shots mode the
script SHALL run `BasicSimulator` by default and, when a noise model
is present and `qiskit_aer` is available, `AerSimulator`.

#### Scenario: Analytic mode output

- **WHEN** compiled with `QSimulationOptions(analytic=True)`
- **THEN** the generated script's `result` dict contains a
  `probabilities` key mapping bitstrings to floats

### Requirement: Noise Model Compilation

The Qiskit backend SHALL recognize a `context` field named `noise`
with type `noise_model` and a default value in the form
`<kind>(<params>)`. Supported kinds SHALL be `depolarizing(p)`,
`amplitude_damping(γ)`, `phase_damping(γ)`, and `thermal(T1, T2)`.
The generated script SHALL attach the noise to all supported gates via
`noise_model.add_all_qubit_quantum_error(...)`.

Gate lists per kind:

- `depolarizing`, `amplitude_damping`, `phase_damping`: all gate kinds
  (`h, x, y, z, rx, ry, rz, t, s, cnot, cx, cz, swap`)
- `thermal`: single-qubit gates only (`h, x, y, z, rx, ry, rz, t, s`),
  because `thermal_relaxation_error` returns a single-qubit channel

For `thermal(T1, T2)`, T1 and T2 are relaxation times in nanoseconds.
The generated script SHALL use `noise.thermal_relaxation_error(T1, T2, 50)`
where 50 ns is the assumed gate time. If only one parameter is provided
(`thermal(T1)`), T2 SHALL default to T1 (the physical upper bound T2 ≤ T1).

#### Scenario: Depolarizing noise

- **WHEN** `## context` contains `| noise | noise_model | depolarizing(0.01) |`
- **THEN** the generated Qiskit script imports `qiskit_aer.noise`,
  constructs a `depolarizing_error(0.01, 1)`, and installs it on
  `['h', 'x', 'y', 'z', 'rx', 'ry', 'rz', 't', 's', 'cnot', 'cx', 'cz', 'swap']`

#### Scenario: Amplitude damping noise

- **WHEN** `## context` contains `| noise | noise_model | amplitude_damping(0.05) |`
- **THEN** the generated script constructs `amplitude_damping_error(0.05)` and
  installs it on the full gate list

#### Scenario: Phase damping noise

- **WHEN** `## context` contains `| noise | noise_model | phase_damping(0.02) |`
- **THEN** the generated script constructs `phase_damping_error(0.02)` and
  installs it on the full gate list

#### Scenario: Thermal relaxation noise

- **WHEN** `## context` contains `| noise | noise_model | thermal(50000, 70000) |`
- **THEN** the generated script constructs
  `thermal_relaxation_error(50000, 70000, 50)` and installs it on
  single-qubit gates only (`h, x, y, z, rx, ry, rz, t, s`)

#### Scenario: Thermal relaxation — single parameter defaults T2 to T1

- **WHEN** `## context` contains `| noise | noise_model | thermal(50000) |`
- **THEN** the generated script constructs
  `thermal_relaxation_error(50000, 50000, 50)` (T2 = T1)

### Requirement: Mermaid State Diagram Output

The Mermaid backend SHALL emit a `stateDiagram-v2` with
`direction LR`. State names SHALL be sanitized into Mermaid-safe
identifiers by stripping ket decorations and non-word characters.
Initial states SHALL be connected from `[*]` and final states SHALL
be connected to `[*]`. Transition labels SHALL be
`event [guard] / action` (guard and action omitted when absent).
Verification rules SHALL be attached as a `note right of <initial>`.

#### Scenario: Transition label formatting

- **WHEN** a transition has event `measure`, guard `collapses_zero`,
  and action `measure_q0`
- **THEN** the Mermaid label reads `measure [collapses_zero] / measure_q0`

### Requirement: Parameterized Gate Handling

The compiler SHALL use a single canonical rotation-gate syntax,
`R{X|Y|Z}(qs[N], <angle>)` (qubit first, angle second), across the
markdown parser, the Qiskit compiler's effect-string parser, and the
dynamic verifier's effect-string parser. All three sites SHALL share
a single symbolic angle evaluator (`q_orca.angle.evaluate_angle`) that
accepts the grammar defined in the language spec. Any rotation-gate
effect that does not match the canonical grammar SHALL produce a parser
error, not a silent `0.0` fallback.

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
