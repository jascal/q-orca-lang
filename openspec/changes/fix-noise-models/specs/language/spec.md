## ADDED Requirements

### Requirement: Noise Model Context Field

The parser SHALL recognize a context field with type `noise_model` as a
valid `QType`. The field's default value string SHALL be parsed by the
compiler's `_parse_noise_model_string` helper into a `NoiseModel` AST
node. Accepted forms are:

- `depolarizing(<float>)` — depolarizing probability p ∈ [0, 1]
- `amplitude_damping(<float>)` — damping rate γ ∈ [0, 1]
- `phase_damping(<float>)` — dephasing rate γ ∈ [0, 1]
- `thermal(<float>)` — T1 relaxation time in ns; T2 defaults to T1
- `thermal(<float>, <float>)` — T1 and T2 relaxation times in ns

The field name SHALL be `noise` by convention, but the parser does not
enforce the name. An unrecognized kind string SHALL result in a `None`
noise model (no noise applied), not a parse error, to preserve forward
compatibility.

#### Scenario: Depolarizing field parses to NoiseModel

- **WHEN** a context table contains `| noise | noise_model | depolarizing(0.01) |`
- **THEN** the field's `type` is `QTypeScalar(kind="noise_model")` and
  the compiler resolves it to `NoiseModel(kind="depolarizing", parameter=0.01)`

#### Scenario: Thermal field with two parameters

- **WHEN** a context table contains `| noise | noise_model | thermal(50000, 70000) |`
- **THEN** the compiler resolves it to
  `NoiseModel(kind="thermal", parameter=50000.0, parameter2=70000.0)`

#### Scenario: Thermal field with one parameter defaults T2

- **WHEN** a context table contains `| noise | noise_model | thermal(50000) |`
- **THEN** the compiler resolves it to
  `NoiseModel(kind="thermal", parameter=50000.0, parameter2=50000.0)`

#### Scenario: Unrecognized noise kind is a no-op

- **WHEN** a context table contains `| noise | noise_model | custom_noise(0.1) |`
- **THEN** `_parse_noise_model_string` returns `None` and no noise model
  is applied — no parse error is raised
