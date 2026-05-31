## ADDED Requirements

### Requirement: QASM Noise Annotation

The QASM backend SHALL emit the `## noise_model` section as a `// noise:` comment block at the top of the generated program, one comment line per channel row, with no semantic effect on the circuit.

Because QASM 3 has no native noise grammar, the channels cannot be simulated from the QASM output; the comment block preserves the declaration for human readers and round-trip tooling, and pairs with the verifier's `NOISE_DROPPED_FOR_BACKEND` warning.

#### Scenario: Section emitted as comments

- **WHEN** a machine with a two-row `## noise_model` section is compiled with `--target=qasm3`
- **THEN** the generated QASM begins with a `// noise:` comment block containing one line per channel row, and the circuit body is otherwise the noiseless program

## MODIFIED Requirements

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
