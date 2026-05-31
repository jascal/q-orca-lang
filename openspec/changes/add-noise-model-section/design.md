## Context

Noise lives in one place today: a `noise` context field of type `noise_model` whose default string (`depolarizing(0.01)`, `thermal(T1, T2)`, …) is regex-parsed by `q_orca/compiler/qiskit.py::_parse_noise_model_string` into a flat `NoiseModel(kind, parameter, parameter2)` and attached to *all* gates via `add_all_qubit_quantum_error`. The `fix-noise-models` change corrected the `thermal` path but did not change the shape: one channel, one rate, applied uniformly, no readout error, no per-target control. The live specs carry this as `language/Noise Model Context Field` and `compiler/Noise Model Compilation`.

`add-resource-estimation` (merged) now exposes per-gate durations and `gate_count`/`cx_count`/`t_count`/`depth`, which this change consumes for time-domain (T1/T2) → Kraus conversion and for the coherence-budget check.

## Goals / Non-Goals

**Goals:**
- A declarative `## noise_model` table that expresses asymmetric per-target channels, readout error, and T1/T2 — the minimum faithful NISQ model (Kandala et al. `1704.05018`).
- The verifier validates channels, resolves targets, and warns on coherence-budget violations; the Qiskit Aer compiler builds the corresponding `NoiseModel` automatically.
- A clean, deprecation-gated migration off the context-field hack with byte-identical compile output for the equivalent single channel.

**Non-Goals:**
- The `error_rate(...)` / `coherence_time(...)` / `fidelity(...)` invariants — a later `extended-invariants` change consumes this section's output.
- Hardware calibration import (`from_calibration_file:`) — deferred (Open Question 1); per-qubit inhomogeneity is expressible one row per qubit for v1.
- A Stim/stabilizer noise path — co-designed here (the rejection diagnostic) but dormant until `stabilizer-fast-path-backend` ships.
- Auto-conversion when a row mixes time-domain and probability-domain parameters — rejected as ambiguous (Decision D5).

## Decisions

### D1 — Channel enum and per-channel parameter schemas
Closed channel set: `depolarizing | amplitude_damping | phase_damping | thermal | readout_error | bit_flip | phase_flip | pauli`. Per-channel schemas the verifier enforces: `depolarizing`/`bit_flip`/`phase_flip` → `p ∈ [0,1]`; `amplitude_damping`/`phase_damping` → `gamma ∈ [0,1]` **or** a time (`T1`/`T2`); `thermal` → `T1`, `T2`, optional `n_bar`; `readout_error` → `p0given1`, `p1given0`; `pauli` → `probabilities=[…]` (4 entries single-qubit, 16 two-qubit). Anything else is `NOISE_CHANNEL_INVALID`. This keeps the schema small and Aer-mappable.

### D2 — Target selector grammar
Closed selector set: broad classes `all_gates | single_qubit_gates | two_qubit_gates | all_measurements | all_qubits`; `qs[N]` (qubit by index); `qs[role:R]` (every qubit with role `R`); `gates[A,B,…]` (named gates). Each row's selector decides which Aer install call is used (`add_quantum_error` for specific qubits/gates, `add_all_qubit_quantum_error` for broad classes, `add_readout_error` for measurement targets).

### D3 — Parameters and units
Parameters are free-form `k=v` pairs validated against the per-channel schema. Time-domain values accept SI suffixes `ns | us | ms`; a bare number is `ns`. The verifier rejects dimensionally-inconsistent parameters (`thermal` with no time unit; `depolarizing` with a time unit).

### D4 — Deprecated context-field alias (migration)
The legacy `noise: noise_model = <kind>(<params>)` context field is retained for one release. The parser routes it through the existing `_parse_noise_model_string` and wraps the result in a **single-row `NoiseModelSection`** targeting `all_gates` (preserving today's "attach to all gates" semantics), and the verifier emits exactly one `NOISE_CONTEXT_FIELD_DEPRECATED` pointing at the section form. Compile output for the alias is byte-identical to the equivalent one-row section. Removed in v0.8.
*Alternative considered:* hard-cut the field now — rejected; it breaks every existing noisy benchmark with no transition window.

### D5 — Ambiguous / mixed parameters are errors, not auto-converted
A row mixing time-domain and probability-domain parameters for the same effect (e.g. `amplitude_damping` with both `gamma=` and `T1=`) is `NOISE_PARAMETER_AMBIGUOUS`. Silent auto-conversion would hide user mistakes (Open Question 2).

### D6 — Idle-qubit noise heuristic
When `thermal` is declared on `all_qubits`, the compiler inserts idle thermal-relaxation per gate-time on otherwise-idle qubits (the physically-correct behaviour Aer needs an explicit duration for); otherwise it does not. Documented clearly (Open Question 3).

### D7 — Backend behaviour when a backend can't model a channel
- **Qiskit/Aer:** full support.
- **QASM 3:** no native noise grammar → emit the rows as a `// noise:` comment block and warn `NOISE_DROPPED_FOR_BACKEND` listing the dropped channels; compile still succeeds (Open Question 5).
- **Stabilizer/Stim (when it lands):** reject non-Pauli channels with `STABILIZER_BACKEND_NOISE_INCOMPATIBLE`; map `depolarizing`/`bit_flip`/`phase_flip` onto Stim's `DEPOLARIZE*`/`X_ERROR`/`Z_ERROR`. Dormant until that backend exists.

### D8 — `qs[role:R]` parses now, rejected until roles land
The selector grammar accepts `qs[role:R]` so the schema is stable, but `noise_target_resolves` rejects it (no role system to resolve against yet) with a clear "requires qubit-role-types" message folded into `NOISE_TARGET_NO_MATCH`. A one-line follow-up enables resolution once `qubit-role-types` merges.

### D9 — Assertions under noise (interaction with runtime-state-assertions)
Runtime-state-assertion sampling stays **noiseless by default**; opting into noisy sampling is a future `## assertion policy` field (`under_noise: bool`), owned by a small follow-up to the assertions spec — not this change (Open Question 4).

## Risks / Trade-offs

- **Aer `to_dict()` round-trip drift across qiskit-aer versions** → the round-trip test pins a hand-written reference for a fixed qiskit-aer version; treat a mismatch as a version-bump signal, not a silent failure.
- **Time→Kraus conversion needs gate durations** → depends on `## resources`; if durations are absent, time-domain channels degrade to a warning and the channel is skipped (not a hard error).
- **Selector grammar collides with table-cell parsing** → reuse the existing markdown infix cell grammar in `markdown_parser.py` rather than a bespoke parser.
- **MODIFIED requirements must preserve existing behaviour** → the context-field scenarios are retained verbatim under the alias path so existing noisy machines compile unchanged.

## Migration Plan

Additive + alias. New section + AST + verifier rules + compiler builder; the context-field path is preserved as a deprecated alias (D4). No machine breaks on landing; authors migrate at leisure before v0.8. Rollback = revert the change; the alias path is the pre-change behaviour.

## Open Questions

1. **Per-qubit T1/T2 inhomogeneity at scale** — v1 ships the one-row-per-qubit form; a `from_calibration_file:` annotation is revisited only on user demand.
2. **Stabilizer channel mapping details** — finalized when `stabilizer-fast-path-backend` lands; the rejection diagnostic is defined here.
3. **`pauli` two-qubit 16-element ordering** — adopt Aer's `PauliError` ordering; pin it in the well-formedness test.
