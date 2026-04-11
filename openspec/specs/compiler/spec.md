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
`amplitude_damping(γ)`, `phase_damping(γ)`, and `thermal(p[, q])`.
The generated script SHALL attach the noise to all supported gates
(`h, x, y, z, rx, ry, rz, t, s, cnot, cx, cz, swap`) via
`noise_model.add_all_qubit_quantum_error(...)`.

#### Scenario: Depolarizing noise

- **WHEN** `## context` contains `| noise | noise_model | depolarizing(0.01) |`
- **THEN** the generated Qiskit script imports `qiskit_aer.noise`,
  constructs a `depolarizing_error(0.01, 1)`, and installs it on the
  gate list above

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

The markdown parser's `_parse_gate_from_effect` SHALL be extended (in
the scheduled `add-parameterized-gates` change) so that rotation gates
appear on the AST's `action.gate` field. Until that change lands, the
compiler's effect-string parser SHALL continue to handle rotations
directly, but the AST gate field SHALL be `None` for rotation gates
and no end-to-end example currently exercises them. Additionally, the
Qiskit compiler's `_parse_single_gate` and the dynamic verifier's
`_parse_single_gate_to_dict` SHALL be reconciled onto a single
canonical argument order.

#### Scenario: Rotation gate argument order divergence

- **WHEN** a user writes `Rx(qs[0], 1.5708)` in an action effect
- **THEN** the dynamic verifier parses this as qubit 0 with
  theta=1.5708, but the Qiskit compiler's parser does not match
  (it expects angle-first) — scoped for `add-parameterized-gates` to reconcile
