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

#### Scenario: CNOT translation across backends

- **WHEN** an action's effect is `CNOT(qs[0], qs[1])`
- **THEN** QASM emits `cx q[0], q[1];`, Qiskit emits `qc.cx(0, 1)`,
  and Mermaid renders the action as a transition label `... / apply_CNOT`

#### Scenario: Bell-pair QASM output structure

- **WHEN** `compile_to_qasm` is called on the Bell-pair machine
- **THEN** the output contains `OPENQASM 3.0;`, `qubit[2] q;`, `h q[0];`,
  and `cx q[0], q[1];` in that order

#### Scenario: Bell-pair Mermaid output structure

- **WHEN** `compile_to_mermaid` is called on the Bell-pair machine
- **THEN** the output begins with `stateDiagram-v2`, contains `direction LR`,
  has a `[*] -->` transition for the initial state, and includes at least one
  transition label containing `apply_CNOT`

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
`run`, and `seed_simulator: int | None` (default `None`). In analytic
mode the script SHALL produce a probability dictionary keyed by
bitstrings via `Statevector`. In shots mode the script SHALL run
`BasicSimulator` by default and, when a noise model is present and
`qiskit_aer` is available, `AerSimulator`.

When `seed_simulator` is set, the compiler SHALL emit
`seed_simulator=<n>` as a keyword argument on both the `BasicSimulator`
and `AerSimulator` `.run(...)` calls in the generated script, producing
deterministic shot counts across repeated executions. When
`seed_simulator` is `None`, no seed kwarg SHALL appear in the emitted
script.

#### Scenario: Analytic mode output

- **WHEN** compiled with `QSimulationOptions(analytic=True)`
- **THEN** the generated script's `result` dict contains a
  `probabilities` key mapping bitstrings to floats

#### Scenario: Seeded shots mode emits seed_simulator kwarg

- **WHEN** compiled with `QSimulationOptions(analytic=False, shots=1024, seed_simulator=42)`
- **THEN** the generated script contains
  `backend.run(qc_shots, shots=shots, seed_simulator=42)` and, on the
  noise-model branch,
  `noisy_backend.run(qc_shots, shots=shots, seed_simulator=42)`

#### Scenario: Unseeded shots mode omits seed_simulator kwarg

- **WHEN** compiled with `QSimulationOptions(analytic=False, shots=1024)`
  (default `seed_simulator=None`)
- **THEN** the generated script contains no `seed_simulator=` occurrence

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

### Requirement: Concept Gram Matrix Analysis Helper

The compiler package SHALL expose an optional analysis helper
`compute_concept_gram(machine, concept_action_label: str =
"query_concept") -> numpy.ndarray[complex]` that returns the
`N × N` concept-overlap matrix for machines following the
polysemantic product-state preparation convention.

The helper SHALL assume the following convention is in effect:

1. The named parametric action has signature
   `(qs, a: angle, b: angle, c: angle) -> qs` (exactly three angle
   parameters, no int parameters).
2. The action's effect is a product-state preparation (or inverse
   preparation) of the form
   `Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)` (or its inverse with
   reversed order and negated signs) — three single-qubit `Ry`
   rotations, one per concept-register qubit.
3. The machine's transitions table contains `N ≥ 1` call sites to
   this action, each with a literal angle triple.

Given this convention, `compute_concept_gram` SHALL enumerate the
call sites in transition-declaration order, build the product-state
`|c_i> = Ry(q_0, a_i) Ry(q_1, b_i) Ry(q_2, c_i) |000>` for each
call-site index `i`, and return the matrix with
`gram[i, j] = <c_i | c_j>` (complex-valued inner product; values
are real for the canonical `Ry`-only encoding).

The helper is an analysis utility and SHALL NOT be part of the
main compile / verify / simulate pipeline. It has no effect on any
compiler entry point other than being importable from the
`q_orca.compiler.concept_gram` module (and re-exported from the
top-level `q_orca` package).

#### Scenario: Happy path on polysemantic-clusters example

- **GIVEN** the parsed machine from
  `examples/larql-polysemantic-clusters.q.orca.md`, which has 12
  call sites to a `query_concept` action meeting the convention
- **WHEN** `compute_concept_gram(machine)` is invoked (default label
  `"query_concept"`)
- **THEN** the return value is a `(12, 12)` NumPy complex array
- **AND** `|gram[i, i]| == 1` for all diagonal entries
- **AND** `|gram[i, j]|² ∈ [0.65, 0.75]` for all `(i, j)` pairs
  where `i ≠ j` and `i, j` share a cluster
- **AND** `|gram[i, j]|² < 0.10` for all `(i, j)` pairs
  where `i, j` are in different clusters (clean tier separation;
  many cross-cluster pairs are near-orthogonal, well below the
  intra-cluster tier)

#### Scenario: Wrong signature shape raises structured error

- **GIVEN** a machine where the parametric action named
  `query_concept` has signature `(qs, c: int) -> qs` (single
  int parameter, not three angle parameters)
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the helper raises `ConceptGramConfigurationError`
  whose message names the action, the machine, and the required
  signature shape

#### Scenario: Missing action raises structured error

- **GIVEN** a machine with no parametric action named
  `query_concept`
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the helper raises `ConceptGramConfigurationError`
  whose message names the missing action and the machine, and
  lists the available parametric actions as a hint

#### Scenario: No call sites raises structured error

- **GIVEN** a machine with a `query_concept` action of the right
  shape but zero transitions that invoke it
- **WHEN** `compute_concept_gram(machine)` is invoked
- **THEN** the helper raises `ConceptGramConfigurationError`
  noting that `query_concept` has no call sites in the
  transitions table

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

