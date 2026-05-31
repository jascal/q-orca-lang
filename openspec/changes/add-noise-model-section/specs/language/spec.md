## ADDED Requirements

### Requirement: Noise Model Section

The parser SHALL recognize a top-level `## noise_model` section declared as a markdown table with columns `Channel`, `Target`, and `Parameters`, producing a `NoiseModelSection` whose `channels` is a list of `NoiseChannel(kind, target, parameters)` in row order.

The `Channel` column SHALL be one of the closed set `depolarizing | amplitude_damping | phase_damping | thermal | readout_error | bit_flip | phase_flip | pauli`. The `Target` column SHALL be one of the closed selector set `all_gates | single_qubit_gates | two_qubit_gates | all_measurements | all_qubits | qs[N] | qs[role:R] | gates[A,B,...]`, parsed into a tagged selector value (`AllGates | SingleQubitGates | TwoQubitGates | AllMeasurements | AllQubits | QubitIndex(int) | QubitRole(str) | GateList(list)`). The `Parameters` column SHALL be parsed as free-form `k=v` pairs into a dict; time-domain values accept the SI suffixes `ns | us | ms` and a bare number SHALL be interpreted as `ns`. The parser SHALL NOT enforce per-channel parameter schemas (that is the verifier's job); it preserves the parsed rows for verification.

#### Scenario: Multi-row section parses into ordered channels

- **WHEN** a machine declares a `## noise_model` table with rows `depolarizing | single_qubit_gates | p=0.001`, `depolarizing | two_qubit_gates | p=0.012`, and `readout_error | all_measurements | p0given1=0.02, p1given0=0.04`
- **THEN** `machine.noise_model.channels` has length 3 in that order, with kinds `depolarizing`, `depolarizing`, `readout_error` and targets `SingleQubitGates`, `TwoQubitGates`, `AllMeasurements`

#### Scenario: Time-domain parameter carries its unit

- **WHEN** a row is `thermal | all_qubits | T1=100us, T2=80us`
- **THEN** the channel's parameters resolve `T1` and `T2` to times of 100 microseconds and 80 microseconds (a bare number would be interpreted as nanoseconds)

#### Scenario: Role and gate-list selectors parse

- **WHEN** rows target `qs[role:ancilla]` and `gates[H,CNOT]`
- **THEN** the parsed selectors are `QubitRole("ancilla")` and `GateList(["H", "CNOT"])` (schema validity is checked by the verifier, not the parser)

## MODIFIED Requirements

### Requirement: Noise Model Context Field

The parser SHALL recognize a context field with type `noise_model` as a valid `QType`, retained as a **deprecated alias** for the `## noise_model` section. The field's default value string SHALL be parsed by the compiler's `_parse_noise_model_string` helper and wrapped into a single-row `NoiseModelSection` whose one `NoiseChannel` targets `all_gates` (preserving the historical "attach to all gates" semantics). Accepted forms are:

- `depolarizing(<float>)` — depolarizing probability p ∈ [0, 1]
- `amplitude_damping(<float>)` — damping rate γ ∈ [0, 1]
- `phase_damping(<float>)` — dephasing rate γ ∈ [0, 1]
- `thermal(<float>)` — T1 relaxation time in ns; T2 defaults to T1
- `thermal(<float>, <float>)` — T1 and T2 relaxation times in ns

The field name SHALL be `noise` by convention, but the parser does not enforce the name. An unrecognized kind string SHALL result in a `None` noise model (no noise applied), not a parse error, to preserve forward compatibility. When a machine uses this field form, the verifier SHALL emit exactly one `NOISE_CONTEXT_FIELD_DEPRECATED` diagnostic (warning severity) pointing at the `## noise_model` section form; the field is slated for removal in v0.8.

#### Scenario: Depolarizing field parses to a single-row section

- **WHEN** a context table contains `| noise | noise_model | depolarizing(0.01) |`
- **THEN** the field's `type` is `QTypeScalar(kind="noise_model")` and it resolves to a `NoiseModelSection` with one `NoiseChannel(kind="depolarizing", target=AllGates, parameters={"p": 0.01})`

#### Scenario: Thermal field with two parameters

- **WHEN** a context table contains `| noise | noise_model | thermal(50000, 70000) |`
- **THEN** it resolves to a single-row section whose channel is `thermal` with T1 = 50000 ns and T2 = 70000 ns targeting `all_gates`

#### Scenario: Unrecognized noise kind is a no-op

- **WHEN** a context table contains `| noise | noise_model | custom_noise(0.1) |`
- **THEN** `_parse_noise_model_string` returns `None`, no noise model is applied, and no parse error is raised

#### Scenario: Using the field emits a deprecation diagnostic

- **WHEN** a machine declares the `noise` context field in any accepted form
- **THEN** the verifier emits exactly one `NOISE_CONTEXT_FIELD_DEPRECATED` diagnostic at warning severity naming the `## noise_model` section as the replacement
