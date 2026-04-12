## MODIFIED Requirements

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
