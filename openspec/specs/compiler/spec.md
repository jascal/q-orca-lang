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

The Qiskit backend SHALL build a `qiskit_aer.noise.NoiseModel` from the machine's `NoiseModelSection`, iterating its channels in order and installing each according to its target selector and channel kind. A `--noise=off` flag SHALL strip noise and emit a noiseless circuit; `--noise=on` (the default when a section is present) SHALL apply it. The legacy `noise` context field is compiled via the single-row section it aliases into (preserving prior behaviour: one channel attached to all gates).

Per channel, the generated script SHALL select the install call by target:

- broad gate classes (`all_gates`, `single_qubit_gates`, `two_qubit_gates`, `gates[...]`) → `add_all_qubit_quantum_error(error, gate_list)` over the matching gate names;
- specific qubits (`qs[N]`, resolved `qs[role:R]`) → `add_quantum_error(error, gate, [qubit])`;
- measurement targets (`all_measurements`) for `readout_error` → `add_readout_error(ReadoutError([[1-p1given0, p1given0], [p0given1, 1-p0given1]]), [qubit])`.

Per channel, the error object SHALL be constructed as: `depolarizing` → `depolarizing_error(p, n)`; `amplitude_damping`/`phase_damping` → `amplitude_damping_error(γ)` / `phase_damping_error(γ)`, or from a time parameter via `thermal_relaxation_error`; `thermal` → `thermal_relaxation_error(T1, T2, gate_time)` using the per-gate duration from `## resources` (single-qubit channel; installed on single-qubit gates); `bit_flip`/`phase_flip` → `pauli_error([("X", p), ("I", 1-p)])` / `("Z", p)`; `pauli` → `PauliError`/`pauli_error` from the `probabilities` list. Time-domain parameters carrying SI suffixes SHALL be converted to nanoseconds before use. When `thermal` targets `all_qubits`, idle thermal-relaxation SHALL be inserted per gate-time on otherwise-idle qubits; otherwise it SHALL NOT.

#### Scenario: Asymmetric two-rate depolarizing model

- **WHEN** `## noise_model` declares `depolarizing | single_qubit_gates | p=0.001` and `depolarizing | two_qubit_gates | p=0.012`
- **THEN** the generated script installs `depolarizing_error(0.001, 1)` on the single-qubit gate list and `depolarizing_error(0.012, 2)` on the two-qubit gate list (`cnot`/`cx`/`cz`/`swap`)

#### Scenario: Readout error on measurements

- **WHEN** `## noise_model` declares `readout_error | all_measurements | p0given1=0.02, p1given0=0.04`
- **THEN** the generated script calls `add_readout_error` with a `ReadoutError` built from those conditional probabilities

#### Scenario: Thermal channel uses resource gate duration

- **WHEN** `## noise_model` declares `thermal | single_qubit_gates | T1=100us, T2=80us` and `## resources` declares a single-qubit gate duration
- **THEN** the generated script constructs `thermal_relaxation_error(100000.0, 80000.0, <gate_time_ns>)` (times converted to ns) and installs it on the single-qubit gate list

#### Scenario: Legacy context field compiles identically

- **WHEN** a machine uses `| noise | noise_model | depolarizing(0.01) |`
- **THEN** the generated noise-model code is byte-identical to the equivalent one-row section `depolarizing | all_gates | p=0.01`

#### Scenario: Noise stripped with --noise=off

- **WHEN** a machine with a `## noise_model` section is compiled with `--noise=off`
- **THEN** the generated circuit installs no noise model

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
  `ParsedGate(name="CRx", targets=(1,), controls=(0,), parameter=<beta>)`.
  The dynamic-verifier adapter uppercases `name` to `"CRX"` for the
  gate-dict shape; the AST adapter preserves source case.

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

### Requirement: Resource Estimation Backend

The compiler SHALL expose a resource-estimation entry point
`estimate_resources(machine) -> dict[str, int | str]` in
`q_orca/compiler/resources.py`. The function SHALL build the Qiskit
`QuantumCircuit` for the machine (reusing the existing Qiskit
compilation path) and compute five metrics:

- `gate_count` — total gate effects from the un-transpiled circuit
  (an honest count of what the user wrote).
- `depth` — circuit depth after `transpile(qc,
  optimization_level=1)`.
- `cx_count` — `transpile(qc, basis_gates=['u3','cx'],
  optimization_level=1).count_ops().get('cx', 0)`.
- `t_count` — `transpile(qc, basis_gates=['h','s','cx','t','tdg'],
  optimization_level=1).count_ops()`, summing the `t` and `tdg`
  entries.
- `logical_qubits` — length of the declared `qubits` list in
  `## context`.

The returned dict SHALL contain exactly the metric names listed in
`machine.resource_metrics` when that list is non-empty, and SHALL
contain all five metrics when the list is empty. Values SHALL be
non-negative integers, or the literal string `"unknown"` when the
metric depends on a runtime-bound construct that cannot be
statically evaluated.

The compiler SHALL memoize results per `id(machine)` so repeated
calls within one verify-or-compile invocation are free.

#### Scenario: Bell-pair resource counts

- **WHEN** `estimate_resources(bell_pair_machine)` is called
- **THEN** the returned dict satisfies `gate_count == 2`,
  `depth == 2`, `cx_count == 1`, `t_count == 0`,
  `logical_qubits == 2`

#### Scenario: GHZ resource counts

- **WHEN** `estimate_resources(ghz_machine)` is called
- **THEN** the returned dict satisfies `gate_count == 3`,
  `depth == 3`, `cx_count == 2`, `t_count == 0`,
  `logical_qubits == 3`

#### Scenario: Default metric set when section is absent

- **WHEN** `estimate_resources(machine)` is called on a machine with
  no `## resources` section
- **THEN** the returned dict contains all five metric keys
  (`gate_count`, `depth`, `cx_count`, `t_count`, `logical_qubits`)

#### Scenario: Subset metric set when section is present

- **WHEN** a machine declares `## resources` listing only
  `gate_count` and `logical_qubits`
- **THEN** `estimate_resources(machine)` returns a dict with
  exactly those two keys

#### Scenario: Memoization on repeated calls

- **WHEN** `estimate_resources(machine)` is called twice with the
  same machine within one verify-or-compile invocation
- **THEN** the second call returns the identical dict and does not
  re-invoke `qiskit.transpile`

### Requirement: Compile-with-Resources Entry Point

The compiler SHALL expose `compile_with_resources(machine, options)
-> tuple[str, dict[str, int | str]]` returning both the Qiskit
script and the resource dict in one call. The script SHALL be
identical to the output of `compile_to_qiskit(machine, options)`;
the resource dict SHALL be identical to
`estimate_resources(machine)`.

`q_orca/__init__.py` SHALL re-export both
`compile_with_resources` and `estimate_resources`.

#### Scenario: Compile-with-resources returns both artifacts

- **WHEN** `compile_with_resources(bell_pair_machine, default_options)`
  is called
- **THEN** the result is a 2-tuple where the first element is a
  Qiskit script string identical to `compile_to_qiskit(...)` and
  the second element is the resource dict from
  `estimate_resources(...)`

#### Scenario: Top-level re-export

- **WHEN** a user runs `from q_orca import estimate_resources,
  compile_with_resources`
- **THEN** both names resolve to the implementations in
  `q_orca/compiler/resources.py` and `q_orca/compiler/qiskit.py`
  respectively

### Requirement: Resource Report Rendering

The compiler SHALL render a one-screen resource report when
`compile_with_resources` is invoked or when the CLI is run with a
machine that has a `## resources` section or any resource
invariant. The report SHALL list one row per metric with: metric
name, measured value, and (when an invariant exists for the metric)
the comparison operator, the bound, and a pass/fail marker.

#### Scenario: Resource report contains all declared metrics

- **WHEN** the resource report is rendered for a machine with
  `gate_count <= 40` and `cx_count <= 12` invariants
- **THEN** the report contains rows for `gate_count` and `cx_count`
  that include the bound and a pass marker (when satisfied) or a
  fail marker (when violated)

#### Scenario: Resource report omits bound for metrics without invariants

- **WHEN** the resource report is rendered for a machine that
  declares `## resources` listing `t_count` but has no `t_count`
  invariant
- **THEN** the `t_count` row contains the measured value and no
  bound or pass/fail marker

### Requirement: MPS Concept Gram Matrix Analysis Helper

The compiler package SHALL expose an optional analysis helper
`compute_concept_gram_mps(machine, concept_action_label: str =
"query_concept", bond_dim: int = 2, method: Literal["statevector",
"contracted", "auto"] = "auto") -> numpy.ndarray[complex]`
that returns the `N × N` concept-overlap matrix for machines
following the MPS (matrix product state) concept-preparation
convention.

The helper SHALL assume the following convention is in effect:

1. The named parametric action has signature
   `(qs, <n angle parameters>) -> qs` where `n` matches the size of
   the `qubits` register declared in `## context`. The number of
   angle parameters is NOT fixed at three — it scales with the
   register size.

2. The action's effect is a CNOT-staircase of the form
   `Ry(qs[0], <expr_0>); CNOT(qs[0], qs[1]); Ry(qs[1], <expr_1>);
   CNOT(qs[1], qs[2]); ... Ry(qs[n-1], <expr_{n-1}>)` — exactly `n`
   single-qubit `Ry` rotations and `n-1` CNOTs between adjacent
   qubits, in staircase order. Each `<expr_k>` SHALL be a *linear
   combination of the action's bound angle parameters* — i.e., a
   sum of terms each of the form `c · p` where `c` is a numeric
   coefficient (defaulting to 1 when omitted) and `p` is one of the
   action's angle parameter names. A single-parameter expression
   like `Ry(qs[0], a)` is the degenerate case `1 · a` and SHALL be
   accepted. The inverse pattern (for query actions: reversed gate
   order, negated angle expressions, CNOTs self-inverse) is also
   accepted.

3. The machine's transitions table contains `N ≥ 1` call sites to
   this action, each with a literal angle tuple.

4. The `bond_dim` parameter is currently fixed at `2`. Values other
   than `2` SHALL raise `MpsGramConfigurationError` with a message
   indicating that higher bond dimensions are not yet implemented.

Given this convention, `compute_concept_gram_mps` SHALL enumerate
the call sites in transition-declaration order, build the MPS state
`|c_i⟩` per call by evaluating the staircase circuit on `|0^n⟩`
(substituting the bound argument values into each `Ry`'s linear-
combination angle expression to produce a float angle), and return
the matrix with `gram[i, j] = ⟨c_i | c_j⟩` (complex-valued inner
product; values are real for the canonical `Ry` + CNOT staircase
encoding).

The helper is an analysis utility and SHALL NOT be part of the
main compile / verify / simulate pipeline. It has no effect on any
compiler entry point other than being importable from the
`q_orca.compiler.concept_gram_mps` module (and re-exported from the
top-level `q_orca` package).

The helper coexists with `compute_concept_gram` (the product-state
helper from `add-polysemantic-clusters`) — the two are separate
entry points and the caller picks based on which preparation
convention their example uses. Automatic ansatz detection is out
of scope.

#### Scenario: Happy path on polysemantic-hierarchical example with cross-coupled angles

- **GIVEN** the parsed machine from
  `examples/larql-polysemantic-hierarchical.q.orca.md`, which has
  12 call sites to a `query_concept` action with a cross-coupled-
  by-sum staircase effect (e.g., `Ry(qs[0], a); CNOT(qs[0], qs[1]);
  Ry(qs[1], a + b); CNOT(qs[1], qs[2]); Ry(qs[2], b + c)`)
- **WHEN** `compute_concept_gram_mps(machine)` is invoked (default
  label `"query_concept"`, default `bond_dim = 2`)
- **THEN** the return value is a `(12, 12)` NumPy complex array
- **AND** `|gram[i, i]| == 1` for all diagonal entries
- **AND** the off-diagonal `|gram[i, j]|²` entries partition into
  exactly four tiers as documented in the example's leading
  paragraph, within a tolerance of `1e-6` per entry
- **AND** the helper successfully evaluates each Ry's linear-
  combination angle expression by substituting the call site's
  bound argument values

#### Scenario: Single-parameter Ry continues to parse (degenerate linear combination)

- **GIVEN** a machine with a strict single-bound-param staircase
  effect `Ry(qs[0], a); CNOT(qs[0], qs[1]); Ry(qs[1], b); CNOT(qs[1],
  qs[2]); Ry(qs[2], c)`
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper parses each Ry's angle as a 1-term linear
  combination (`1 · a`, `1 · b`, `1 · c`) and returns the same Gram
  matrix it produced before this change

#### Scenario: Non-linear angle expression raises structured error

- **GIVEN** a machine where one Ry's angle expression is non-linear
  in the bound parameters — e.g., `Ry(qs[1], a * b)`,
  `Ry(qs[1], sin(a))`, `Ry(qs[1], a^2)`, or `Ry(qs[1], 2.5)` (a
  bare numeric literal with no parameter reference)
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` with kind
  `unrecognized_angle_expression` whose message names the offending
  expression, the action, the machine, and lists the supported
  shape (linear combination of bound angle parameters with optional
  numeric coefficients)

#### Scenario: Wrong signature shape raises structured error

- **GIVEN** a machine where the parametric action named
  `query_concept` has signature `(qs, c: int) -> qs` (single int
  parameter, not n angle parameters)
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` whose
  message names the action, the machine, and the required
  signature shape (n angle parameters matching register size)

#### Scenario: Non-staircase effect raises structured error

- **GIVEN** a machine where `query_concept` has the right signature
  shape but an effect that is not a CNOT-staircase (e.g., product-
  state only — no CNOTs — or CNOTs between non-adjacent qubits)
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` whose
  message identifies the unexpected gate pattern and names the
  required staircase shape

#### Scenario: Missing action raises structured error

- **GIVEN** a machine with no parametric action named
  `query_concept`
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` whose
  message names the missing action and the machine, and lists the
  available parametric actions as a hint

#### Scenario: No call sites raises structured error

- **GIVEN** a machine with a `query_concept` action of the right
  shape but zero transitions that invoke it
- **WHEN** `compute_concept_gram_mps(machine)` is invoked
- **THEN** the helper raises `MpsGramConfigurationError` noting
  that `query_concept` has no call sites in the transitions table

#### Scenario: Unsupported bond dimension raises structured error

- **GIVEN** the canonical example
- **WHEN** `compute_concept_gram_mps(machine, bond_dim=4)` is
  invoked
- **THEN** the helper raises `MpsGramConfigurationError` with a
  message indicating that only `bond_dim=2` is currently
  implemented

### Requirement: compute_concept_gram_mps accepts a method parameter

`q_orca.compiler.concept_gram_mps.compute_concept_gram_mps` SHALL accept a new keyword argument `method: Literal["statevector", "contracted", "auto"] = "auto"`.

When `method="statevector"`, the function SHALL use the existing explicit-2ⁿ-statevector implementation. The result SHALL be bit-identical to the pre-change implementation on every input.

When `method="contracted"`, the function SHALL use the O(n · χ⁶) transfer-matrix contraction implementation. For every input on which both modes can run (e.g., n_qubits small enough that statevector doesn't OOM), the contracted result SHALL equal the statevector result to 1e-12 absolute tolerance.

When `method="auto"` (the default), the function SHALL dispatch to `"statevector"` when `n_qubits < STATEVECTOR_NQUBIT_THRESHOLD` and to `"contracted"` otherwise.

`STATEVECTOR_NQUBIT_THRESHOLD` SHALL be a module-level constant exposed for tuning, with initial value 20.

#### Scenario: method="statevector" preserves pre-change behaviour

- **WHEN** `compute_concept_gram_mps(machine, method="statevector")` is called on any shipped MPS example
- **THEN** the result is bit-identical to the result produced by the pre-change implementation on the same machine

#### Scenario: contracted equals statevector at small n

- **WHEN** `compute_concept_gram_mps(machine, method="contracted")` is called on a machine with `n_qubits ∈ {3, 4, 5, 6}`
- **THEN** the result equals `compute_concept_gram_mps(machine, method="statevector")` on the same machine to 1e-12 absolute tolerance

#### Scenario: auto dispatches to statevector below threshold

- **WHEN** `compute_concept_gram_mps(machine, method="auto")` is called with `n_qubits=3`
- **THEN** the function takes the statevector code path

#### Scenario: auto dispatches to contracted at threshold

- **WHEN** `compute_concept_gram_mps(machine, method="auto")` is called with `n_qubits=20`
- **THEN** the function takes the contracted code path

#### Scenario: unknown method value raises

- **WHEN** `compute_concept_gram_mps(machine, method="invalid")` is called
- **THEN** a `ValueError` is raised whose message contains the invalid value and the supported set `{"statevector", "contracted", "auto"}`

### Requirement: contracted path is constant in memory across n_qubits

The contracted-path implementation SHALL allocate intermediate state of size O(n · χ²) per MPS feature (not O(2ⁿ)). At χ=2 this is O(n) complex numbers per feature, regardless of how large `n_qubits` grows.

This requirement is testable by running the contracted path at large synthetic `n_qubits` (e.g., 24, 28) on a machine with N=2 call sites and confirming no out-of-memory error. Compare against the statevector path at the same n which OOMs at 28.

#### Scenario: contracted path runs at n_qubits=28 on a small synthetic machine

- **WHEN** a synthetic 28-qubit machine with N=2 call sites is built and `compute_concept_gram_mps(machine, method="contracted")` is invoked
- **THEN** the function returns a finite `(2, 2)` complex Gram without raising MemoryError

### Requirement: contracted Gram preserves Hermitian + unit-modulus-diagonal invariants

For any valid input, the contracted Gram `G` SHALL satisfy:

- Hermitian: `G[i, j] == G[j, i].conjugate()` to 1e-12 absolute tolerance for every (i, j).
- Unit-modulus diagonal: `abs(G[i, i]) == 1.0` to 1e-12 absolute tolerance for every `i` (the state vectors are normalised).
- Finite: no NaN or Inf entries.

#### Scenario: Hermitian invariant holds at n_qubits=16

- **WHEN** a synthetic 16-qubit machine with 8 random-seed call sites is built and run through `method="contracted"`
- **THEN** the resulting Gram satisfies `np.allclose(G, G.conj().T, atol=1e-12)` and `np.allclose(np.abs(np.diag(G)), 1.0, atol=1e-12)`

### Requirement: bond_dim != 2 continues to raise (no change)

The existing `bond_dim != 2` guard in `compute_concept_gram_mps` is preserved unchanged. The contracted path SHALL also enforce `bond_dim == 2` and SHALL raise the same `MpsGramConfigurationError` for any other value.

The χ>2 generalisation (multi-CNOT KAK + multi-rank transfer matrices) is explicitly out of scope for this change; the error message remains identical.

#### Scenario: bond_dim=4 raises on the contracted path

- **WHEN** `compute_concept_gram_mps(machine, method="contracted", bond_dim=4)` is called
- **THEN** the same `MpsGramConfigurationError` is raised as in the pre-change implementation, with a message naming `bond_dim=4` and pointing at the single-CNOT-per-step staircase constraint

### Requirement: HEA Concept Gram Matrix Analysis Helper

The compiler package SHALL expose an optional analysis helper
`compute_concept_gram_hea(machine, concept_action_label: str =
"query_concept") -> numpy.ndarray[complex]` that returns the `N × N`
concept-overlap matrix for machines following the rung-2
hardware-efficient ansatz (HEA) encoding.

The helper SHALL assume the following convention is in effect:

1. The machine has a parsed `EncodingDecl` with `kind == "hea"`,
   `depth ≥ 1`, `entangler ∈ {"ring", "chain"}`, and a non-empty
   `rotations` tuple over `{"Rx", "Ry", "Rz"}`.

2. The machine has a parsed `ThetaBlock` with one `ThetaRow` per
   parametric call site referenced in the transitions table. Each
   row's tensor has shape `(|rotations|, depth, n)` where `n` is
   the size of the encoding's resolved qubits register.

3. The transitions table contains `N` call sites to
   `concept_action_label`. The helper enumerates them in
   transition-declaration order and pairs each positionally with a
   theta row in declaration order (call site `i` ↔
   `theta.rows[i]`). The number of call sites SHALL equal the
   number of theta rows; mismatch raises
   `HeaGramConfigurationError`.

Given this convention, `compute_concept_gram_hea` SHALL build each
concept state `|c_i⟩` by simulating the HEA circuit on `|0^n⟩`
(per-layer single-qubit rotations from `rotations` in declared
order, then the entangler block — CNOT chain `(q, q+1)` for chain;
chain plus the wrap-around `(n-1, 0)` for ring), and SHALL return
the matrix with `gram[i, j] = ⟨c_i | c_j⟩`.

The helper is an analysis utility and SHALL NOT be part of the
main compile / verify / simulate pipeline. It is importable from
`q_orca.compiler.concept_gram_hea` and re-exported from the
top-level `q_orca` package alongside `compute_concept_gram` and
`compute_concept_gram_mps`.

QASM and Qiskit emit for HEA-encoded machines is **out of scope**
for this requirement — the helper builds states directly via numpy
without going through the QASM / Qiskit compilers.

#### Scenario: Happy path on minimal HEA example

- **GIVEN** the parsed machine from
  `examples/larql-hea-minimal.q.orca.md`, which has three
  concepts on a 3-qubit register with depth=3 ring-entangler HEA
  and rotation set `(Ry, Rz)`
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the return value is a `(3, 3)` NumPy complex array
- **AND** `|gram[i, i]| == 1` for all diagonal entries within
  `1e-9`
- **AND** the off-diagonal `|gram[i, j]|²` entries partition into
  the documented tiers within tolerance `1e-6`

#### Scenario: Missing encoding section raises structured error

- **GIVEN** a machine without an `## encoding` section
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` whose
  message names the machine and indicates that an `## encoding`
  section with `kind: hea` is required

#### Scenario: Wrong encoding kind raises structured error

- **GIVEN** a machine whose encoding has `kind: alternating-layered`
  (or any non-`hea` kind)
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` whose
  message names the actual kind and indicates that this helper
  handles `kind: hea` only

#### Scenario: Missing theta block raises structured error

- **GIVEN** a machine with an `## encoding` section but no
  `## theta` section
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` whose
  message names the machine and indicates that a `## theta` block
  is required

#### Scenario: Theta-shape mismatch raises structured error

- **GIVEN** an encoding declaring `rotations=(Ry, Rz)`, `depth=3`,
  `n=3` (expected per-row shape `(2, 3, 3)`) and a theta row
  whose tensor has shape `(2, 3, 4)` that survived initial
  parsing (e.g., loaded programmatically)
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` whose
  message names the concept, the actual shape, and the expected
  shape

#### Scenario: Call-site / theta-row count mismatch raises structured error

- **GIVEN** a machine whose transitions table has 4 call sites to
  `query_concept` but a `## theta` block declaring only 3 rows
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` naming
  the call-site count, the theta-row count, and listing the
  declared theta-row concept names as a hint

#### Scenario: No call sites raises structured error

- **GIVEN** a machine with valid `## encoding` and `## theta`
  sections but zero transitions invoking `query_concept`
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** the helper raises `HeaGramConfigurationError` noting
  that `query_concept` has no call sites in the transitions
  table

#### Scenario: All-zero theta produces an identity-like Gram

- **GIVEN** a machine with valid HEA encoding and a theta block
  where every row is the all-zero tensor of the correct shape
- **WHEN** `compute_concept_gram_hea(machine)` is invoked
- **THEN** every concept state equals `|0^n⟩` (zero rotations
  produce identities; CNOTs on `|0^n⟩` are identities)
- **AND** `gram` is the all-ones matrix within `1e-9`

### Requirement: Conditional gate compilation

The OpenQASM 3.0 emitter SHALL serialize a `QEffectConditional` with
N conditions as `if (<clause_1> && <clause_2> && … && <clause_N>) {
<gate>; }`, where each clause is `c[i]` for value `1` and `!c[i]`
for value `0` — matching the bare-bit / negated-bit shape already
used for single-condition emit. Single-condition effects SHALL emit
`if (c[i]) { <gate>; }` or `if (!c[i]) { <gate>; }` (unchanged).
Conditions SHALL appear in the order declared in the source.

The Qiskit emitter SHALL serialize a `QEffectConditional` with N
conditions as N nested `with qc.if_test((c[i_k], v_k)):` blocks,
with the gate call inside the innermost block. Single-condition
effects SHALL emit a single `with qc.if_test(...)` block (unchanged).

Resource estimation SHALL count a compound conditional gate as a
single gate of the underlying gate type — the conjunction is
classical control flow and SHALL NOT inflate `gate_count`,
`cx_count`, or `t_count` past the count of the gate inside the
conditional.

#### Scenario: OpenQASM emits compound condition

- **GIVEN** an action with effect
  `if bits[0] == 1 and bits[1] == 1: X(qs[1])`
- **WHEN** the OpenQASM compiler emits the action body
- **THEN** the output contains `if (c[0] && c[1]) { x q[1]; }`

#### Scenario: OpenQASM emits mixed-value compound condition

- **GIVEN** an action with effect
  `if bits[0] == 1 and bits[1] == 0: X(qs[0])`
- **WHEN** the OpenQASM compiler emits the action body
- **THEN** the output contains `if (c[0] && !c[1]) { x q[0]; }`

#### Scenario: OpenQASM emits single-condition unchanged

- **GIVEN** an action with effect `if bits[0] == 1: X(qs[0])`
- **WHEN** the OpenQASM compiler emits the action body
- **THEN** the output contains `if (c[0]) { x q[0]; }`

#### Scenario: Qiskit emits nested if_test blocks

- **GIVEN** an action with effect
  `if bits[0] == 1 and bits[1] == 1: X(qs[1])`
- **WHEN** the Qiskit compiler emits the action body
- **THEN** the output contains a `with qc.if_test((c[0], 1)):`
  block, nested inside which is `with qc.if_test((c[1], 1)):` whose
  body is `qc.x(q[1])`

#### Scenario: Resource estimation counts compound conditional as one gate

- **GIVEN** a machine where a single transition fires
  `if bits[0] == 1 and bits[1] == 0 and bits[2] == 1: X(qs[3])`
- **WHEN** resource estimation runs
- **THEN** the contribution to `gate_count` is 1, not 3

### Requirement: Assertion Metadata Pass-Through

The compiler SHALL carry per-state assertion annotations through to the
emitted artifact as out-of-band metadata. No assertion SHALL produce a
new instruction, gate, or measurement in any backend's emitted output —
real-device execution MUST be unaffected by the presence or absence of
`[assert: …]` annotations.

The Qiskit backend (`compile_to_qiskit`) SHALL attach an
`assertion_probe: list[QAssertion]` field to its existing per-state
metadata block at the point in the gate sequence corresponding to the
named state. The Stage 4b verifier consumes this field via
`q_orca.verifier.assertions.check_state_assertions`.

The QASM backend (`compile_to_qasm`) SHALL emit, immediately before the
gate sequence for the next transition out of an annotated state, one
comment line per assertion of the form:

```
// assert: <category>(<qubit-slice>[, <qubit-slice>]*) @ state <state-name>
```

QASM comment emission SHALL preserve the source order of assertions
within a single state. Comment lines SHALL be the only QASM artifact
produced by `[assert: …]` annotations.

The Mermaid backend (`compile_to_mermaid`) MAY annotate a state node's
description with a brief `assert:` summary but SHALL NOT introduce new
state nodes, transitions, or labels for assertions.

#### Scenario: Qiskit backend attaches assertion probe metadata

- **WHEN** a machine has a state declared
  `[assert: entangled(qs[0], qs[1])]` and `compile_to_qiskit` is called
- **THEN** the Qiskit script's per-state metadata for that state
  includes `assertion_probe` with one `QAssertion` whose
  `category="entangled"` and `targets=[QubitSlice(0), QubitSlice(1)]`

#### Scenario: Qiskit backend emits no new gates for assertions

- **WHEN** a Bell-pair machine with no assertions and the same machine
  with `[assert: entangled(qs[0], qs[1])]` are both compiled by
  `compile_to_qiskit`
- **THEN** the two scripts are identical except for the
  `assertion_probe` metadata field — the gate sequence
  (`qc.h(0); qc.cx(0, 1)`) is byte-identical

#### Scenario: QASM backend emits comment line per assertion

- **WHEN** a machine has a state `|encoded>` declared
  `[assert: superposition(qs[0..2]); entangled(qs[0], qs[1])]` and
  `compile_to_qasm` is called
- **THEN** the emitted QASM contains the lines
  `// assert: superposition(q[0..2]) @ state encoded` and
  `// assert: entangled(q[0], q[1]) @ state encoded` in source order,
  positioned before the gate sequence for the next outgoing transition

#### Scenario: QASM backend emits no instructions for assertions

- **WHEN** a machine with assertions is compiled by `compile_to_qasm`
  and the output is parsed by an OpenQASM 3.0 lint tool
- **THEN** the only assertion-related lines are comments and the
  instruction count matches the same machine compiled with assertions
  removed

#### Scenario: Mermaid backend renders without new states

- **WHEN** a machine with assertions is compiled by `compile_to_mermaid`
- **THEN** the emitted Mermaid diagram has the same node count and
  transition count as the same machine compiled with assertions
  removed

### Requirement: Composed-Machine Rendering and Backend Refusal

Each compiler backend SHALL have explicit behavior when given a
machine that contains invoke states: Mermaid SHALL render them;
QASM and Qiskit SHALL refuse and emit a structured error
directing the user to the composed-runtime follow-up. This
preserves diagramming and static analysis while preventing silent
compilation of a composition whose runtime semantics are not yet
specified.

- **Mermaid**: invoke states SHALL be rendered as a distinct node
  shape (rounded rectangle) labeled with the child machine name.
  The Mermaid diagram SHALL include a nested `state <ChildName>
  { ... }` block for each resolved child, so the composed diagram
  is self-contained.
- **QASM / Qiskit**: given a machine whose AST contains any
  invoke state, the compiler SHALL return a structured
  `COMPILE_COMPOSED_MACHINE` error whose message reads
  "cannot compile a machine with invoke states directly. Compile
  child machines individually and compose via the runtime
  (planned as `add-composed-runtime`)."

#### Scenario: Mermaid with invoke

- **WHEN** a parent machine has
  `## state |train> [invoke: QChild(theta=theta) shots=1024]` and
  `QChild` is a sibling machine in the same file
- **THEN** the Mermaid output shows `|train>` as a rounded
  rectangle labeled `invoke: QChild` and includes a nested
  `state QChild { ... }` block rendering QChild's own states and
  transitions

#### Scenario: QASM refuses composed machine

- **WHEN** `compile_to_qasm(parent_machine)` is called and
  `parent_machine` has any invoke state
- **THEN** the compiler returns a structured
  `COMPILE_COMPOSED_MACHINE` error rather than an incomplete QASM
  program

#### Scenario: Qiskit refuses composed machine

- **WHEN** `compile_to_qiskit(parent_machine, options)` is called
  and `parent_machine` has any invoke state
- **THEN** the compiler returns the same structured
  `COMPILE_COMPOSED_MACHINE` error as QASM — the Qiskit backend
  does not fall back to any partial compilation

### Requirement: Imported Machine Rendering

`compile_to_mermaid` SHALL render an imported invoked child (one resolved
through the file's imports rather than a same-file machine) as a distinct nested
composite node — the same shape as a same-file invoked child — carrying the
import path so the diagram shows where the child came from. No imported child
SHALL introduce a new top-level state node or transition in the parent's own
state graph beyond the composite block. A standalone import-graph view SHALL be
obtainable (the `q-orca imports show <file>` command) that renders the
transitively-closed import graph as a Mermaid diagram of files and their import
edges.

#### Scenario: Mermaid renders an imported child with its path

- **WHEN** a parent invokes `PrepareBellPair` imported from
  `./lib/bell-pair.q.orca.md` and `compile_to_mermaid` is called with the
  resolved import graph
- **THEN** the diagram includes a nested composite block for `PrepareBellPair`
  labeled with its import path `./lib/bell-pair.q.orca.md`

#### Scenario: Import graph view renders files and edges

- **WHEN** `q-orca imports show parent.q.orca.md` is run on a file that imports
  two others
- **THEN** the emitted Mermaid diagram has one node per file in the transitive
  import closure and one edge per import relationship

### Requirement: QASM Noise Annotation

The QASM backend SHALL emit the `## noise_model` section as a `// noise:` comment block at the top of the generated program, one comment line per channel row in a stable machine-parseable `key=value` format, with no semantic effect on the circuit. Each line SHALL have the form `// noise: channel=<kind> target=<selector> <param>=<value> ...` so downstream tooling can recover the section without re-reading the source.

Because QASM 3 has no native noise grammar, the channels cannot be simulated from the QASM output; the comment block preserves the declaration for human readers and round-trip tooling, and pairs with the verifier's `NOISE_DROPPED_FOR_BACKEND` warning.

#### Scenario: Section emitted as comments

- **WHEN** a machine with a two-row `## noise_model` section is compiled with `--target=qasm3`
- **THEN** the generated QASM begins with a `// noise:` comment block of two `key=value` lines (`channel=… target=… …`), and the circuit body is otherwise the noiseless program

### Requirement: Loop Compilation

The compiler SHALL emit a real control-flow loop for a `[loop …]`-annotated body instead of unrolling it. For a fixed bound `N`: QASM 3 `for k in [0:N-1] { … }` and Qiskit `ForLoopOp`. For an adaptive predicate `P`: QASM 3 emits `while (!(P)) { … }` — a `[loop until: P]` iterates *while `P` is not yet satisfied*, so the QASM `while` condition is the negation of the predicate. A `--unroll-loops` flag SHALL retain the previous N-times-unrolled emission.

Adaptive predicates are host-computed (e.g. Simon's `rank` over GF(2)) and are not expressible over QASM classical registers, so the Qiskit backend emits the adaptive body **once** under a structured host-driven marker rather than a literal `WhileLoopOp`; faithful adaptive iteration is host-driven.

The fixed bound `N` is the compile-time evaluation of the `[loop <expr>]` expression against the machine's context defaults. Under `--qasm-version=2` (no native loops) the loop is unrolled with a `QASM2_DOWNGRADE_LOOP` warning. Under a stabilizer/Stim backend (no `for`) the loop is silently unrolled with an info-level `LOOP_UNROLLED_FOR_BACKEND` diagnostic. The Mermaid renderer SHALL render a loop-annotated state with a back-edge label — `×N` for fixed, a condensed predicate (≤ 30 chars) for adaptive — rather than an unrolled linear chain.

#### Scenario: Fixed loop emits a single for block

- **WHEN** a machine with `## context | N | int | 16 |` has `## state |amplified> [loop ceil(pi/4 * sqrt(N))]` and is compiled to QASM 3
- **THEN** the output contains exactly one `for k in [0:2]` block wrapping the body (not the body repeated three times)

#### Scenario: Adaptive loop emits a negated while block

- **WHEN** a `[loop until: P]` machine is compiled to QASM 3
- **THEN** the output contains a `while (!(P)) { … }` block over the body (iterate while the predicate is not yet satisfied)

#### Scenario: --unroll-loops reproduces prior emission

- **WHEN** the same fixed-loop machine is compiled with `--unroll-loops`
- **THEN** the body is emitted N times with no `for` block (the pre-change shape)

### Requirement: Loop-Aware Resource Estimation

The compiler's resource estimation SHALL multiply a fixed `[loop N]` body's per-action cost contributions by `N` once (so `gate_count`/`cx_count`/`depth` are faithful rather than the body's single-iteration cost), and SHALL report an adaptive loop's cost as the range `[body_cost, body_cost × MAX_LOOP_BOUND]` (default `MAX_LOOP_BOUND = 1000`) with a `RESOURCE_ESTIMATE_LOOP_ADAPTIVE` diagnostic.

#### Scenario: Fixed loop multiplies the body cost

- **WHEN** a 4-state body annotated `[loop 100]` has a per-iteration `gate_count` of 12
- **THEN** the reported `gate_count` is 1200 (and the emitted code is a single `ForLoopOp`, so estimate and emission agree)

#### Scenario: Adaptive loop reports a range

- **WHEN** a `[loop until: P]` body has per-iteration `gate_count` 12
- **THEN** the resource report gives a range up to `12 × MAX_LOOP_BOUND` and emits `RESOURCE_ESTIMATE_LOOP_ADAPTIVE`

