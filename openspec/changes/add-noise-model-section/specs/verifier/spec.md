## ADDED Requirements

### Requirement: Noise Channel Well-Formedness

The verifier SHALL validate each `NoiseChannel` row against its per-channel parameter schema and emit `NOISE_CHANNEL_INVALID` at error severity for any row that is missing a required parameter, carries an out-of-range value, or is dimensionally inconsistent.

Per-channel schemas: `depolarizing`/`bit_flip`/`phase_flip` require `p ∈ [0, 1]`; `amplitude_damping`/`phase_damping` require either `gamma ∈ [0, 1]` or a time parameter (`T1`/`T2`); `thermal` requires `T1` and `T2` (optional `n_bar`); `readout_error` requires `p0given1` and `p1given0`; `pauli` requires a `probabilities` list of 4 entries (single-qubit) or 16 (two-qubit) summing to 1. A row that supplies both a probability-domain and a time-domain parameter for the same effect SHALL be rejected as `NOISE_PARAMETER_AMBIGUOUS` (no silent auto-conversion). A time-domain parameter without a time unit, or a probability-domain parameter with one, SHALL be rejected as dimensionally inconsistent.

#### Scenario: Out-of-range probability rejected

- **WHEN** a row is `depolarizing | all_gates | p=1.4`
- **THEN** the verifier emits `NOISE_CHANNEL_INVALID` at error severity

#### Scenario: Mixed time and probability parameters rejected

- **WHEN** a row is `amplitude_damping | all_qubits | gamma=0.05, T1=100us`
- **THEN** the verifier emits `NOISE_PARAMETER_AMBIGUOUS` at error severity

#### Scenario: Well-formed Kandala-shaped rows pass

- **WHEN** rows are `depolarizing | single_qubit_gates | p=0.001` and `depolarizing | two_qubit_gates | p=0.012` and `readout_error | all_measurements | p0given1=0.02, p1given0=0.04`
- **THEN** the verifier reports no `NOISE_CHANNEL_INVALID` for any row

### Requirement: Noise Target Resolution

The verifier SHALL resolve each row's target selector against the machine and emit `NOISE_TARGET_NO_MATCH` at warning severity when a selector matches no extant gate, qubit, or measurement (a no-op row).

A `qs[role:R]` selector SHALL resolve against qubit roles when the `qubit-role-types` capability is present; until then it SHALL be reported as unresolved via `NOISE_TARGET_NO_MATCH` with a message stating it requires `qubit-role-types`. `gates[...]` selectors naming gates that never appear in the machine, and `qs[N]` indices beyond the declared qubit count, SHALL also produce `NOISE_TARGET_NO_MATCH`.

#### Scenario: Role selector resolves to matching qubits

- **GIVEN** roles are available and `## context` declares qubits with roles `[q0:data, q1:ancilla, q2:ancilla]`
- **WHEN** a row targets `qs[role:ancilla]`
- **THEN** the selector resolves to qubit indices `[1, 2]` and no `NOISE_TARGET_NO_MATCH` is emitted

#### Scenario: Non-matching selector warns

- **WHEN** a row targets `qs[role:nonexistent]` (or `gates[TOFFOLI]` in a machine with no Toffoli gate)
- **THEN** the verifier emits `NOISE_TARGET_NO_MATCH` at warning severity

### Requirement: Coherence Budget Check

The verifier SHALL, when the noise model declares `thermal`/`T1`/`T2` and `## resources` declares per-gate durations, estimate the worst-case path duration through the transition graph and emit `COHERENCE_BUDGET_EXCEEDED` at warning severity when that duration exceeds the declared `T2`.

The duration estimate SHALL reuse the depth/gate-duration infrastructure from the resource-estimation pipeline. When gate durations are absent the check SHALL be skipped (not an error), and the diagnostic message SHALL include the estimated circuit duration and the `T2` it exceeded.

#### Scenario: Circuit longer than T2 warns

- **WHEN** a machine declares `thermal` with `T2=8ns` and a 20-gate path with per-gate duration `2ns` (40ns > 8ns)
- **THEN** the verifier emits `COHERENCE_BUDGET_EXCEEDED` whose message names both 40ns and 8ns

#### Scenario: No declared durations skips the check

- **WHEN** a noise model declares `T1`/`T2` but `## resources` declares no per-gate durations
- **THEN** the verifier emits no `COHERENCE_BUDGET_EXCEEDED` (the check is skipped, not failed)

### Requirement: Backend Noise Compatibility

The verifier SHALL check the declared noise channels against the selected compile target and report channels a target cannot simulate, without silently dropping them.

When the target is QASM 3 (which has no native noise grammar), every declared channel SHALL produce a `NOISE_DROPPED_FOR_BACKEND` warning naming the channel and the backend, and the compiler SHALL emit the channels as comments (see the compiler spec) and still succeed. When the target is a stabilizer/Stim backend, any non-Pauli channel (`amplitude_damping`, `phase_damping`, `thermal`, `readout_error`, general `pauli`) SHALL be rejected with `STABILIZER_BACKEND_NOISE_INCOMPATIBLE` at error severity (this branch is dormant until the stabilizer backend ships). When the target is Qiskit/Aer, all channels are accepted.

#### Scenario: Non-Pauli channel rejected on stabilizer target

- **WHEN** a machine declares `amplitude_damping` and is compiled with `--target=stabilizer`
- **THEN** the verifier emits `STABILIZER_BACKEND_NOISE_INCOMPATIBLE` at error severity and the machine does not compile

#### Scenario: Channels dropped on QASM target warn but compile

- **WHEN** a machine with any `## noise_model` rows is compiled with `--target=qasm3`
- **THEN** the verifier emits `NOISE_DROPPED_FOR_BACKEND` listing the channels and the backend, and compilation still succeeds
