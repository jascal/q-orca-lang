## Why

Noise modelling in q-orca is a single-context-field hack: one `noise: noise_model = depolarizing(0.01)` row that the Qiskit compiler parses with a regex into a flat `NoiseModel(kind, parameter, parameter2)`. It cannot express the **asymmetry between single- and two-qubit gate errors** that defines every NISQ device (rates vary by device, but two-qubit gates are consistently roughly an order of magnitude noisier — the asymmetry, not any one ratio, is the point), cannot express **readout error** at all, and cannot express **per-qubit T1/T2** inhomogeneity. Authors who need a faithful model hand-write ~50 lines of Python around the compiled circuit (e.g. `NoiseModel.from_backend(...)`), at which point the noise is invisible to the verifier and the resource-estimation pipeline, and drifts out of sync with the machine.

The just-merged `add-resource-estimation` change makes `gate_count`/`cx_count`/`t_count`/`depth` first-class — exactly the inputs to the standard fidelity estimate `F ≈ ∏_g (1 − ε_g)`. The only missing piece is a first-class noise declaration the verifier and compiler can both read.

## What Changes

- Add a first-class top-level **`## noise_model` section**: a table of rows, each binding a **channel** (`depolarizing | amplitude_damping | phase_damping | thermal | readout_error | bit_flip | phase_flip | pauli`) to a **target selector** (`all_gates | single_qubit_gates | two_qubit_gates | all_measurements | all_qubits | qs[N] | qs[role:R] | gates[...]`) and its **parameters** (`k=v` pairs; time-domain values take `ns|us|ms`, default `ns`).
- Replace the flat `NoiseModel` AST with `NoiseChannel` (kind, target, params) + `NoiseModelSection` (channels, default units); add `noise_model: NoiseModelSection | None` to `QMachineDef`.
- The Qiskit Aer compiler builds a `NoiseModel` per-channel/per-target (`add_quantum_error` / `add_all_qubit_quantum_error` / `add_readout_error`; time-domain → `thermal_relaxation_error` using `## resources` gate durations). A `--noise=on|off` compile/verify flag toggles it.
- The QASM backend emits the section as a `// noise:` comment block (QASM 3 has no native noise grammar).
- Four verifier rules: per-row schema validation, target resolution, a coherence-budget check (circuit duration vs T2), and backend compatibility (Stim/QASM behaviour).
- **BREAKING (soft, deprecation-gated):** the legacy `noise: noise_model = ...` context field is kept for one release as a *deprecated alias* — parsed into a single-row `## noise_model` section and flagged `NOISE_CONTEXT_FIELD_DEPRECATED`. Slated for removal in v0.8.
- Out of scope (graceful degradation): the `qs[role:R]` selector parses now but is rejected by the verifier until `qubit-role-types` lands; Stim channel-rejection is co-designed now but dormant until `stabilizer-fast-path-backend` ships; the `error_rate(...)`/`coherence_time(...)` invariants are a later `extended-invariants` change.

## Capabilities

### New Capabilities
<!-- none — noise modelling already exists across language/verifier/compiler; this extends it -->

### Modified Capabilities
- `language`: add the `## noise_model` section grammar; re-spec the `noise` context field as a deprecated single-row alias.
- `verifier`: add noise-channel well-formedness, target resolution, coherence-budget, and backend-compatibility rules.
- `compiler`: re-spec Qiskit noise compilation to build from the section (per-channel/per-target, readout error, time-domain conversion); add QASM noise-as-comment emission.

## Impact

- **Changed code**: `q_orca/parser/markdown_parser.py` (section recognizer + row/selector parsers); `q_orca/ast.py` (`NoiseChannel`/`NoiseModelSection`, keep alias path); `q_orca/verifier/` (4 rules + diagnostics); `q_orca/compiler/qiskit.py` (per-channel builder, replacing `_emit_qiskit_noise_model_code`); `q_orca/compiler/qasm.py` (comment block).
- **New diagnostics**: `NOISE_CHANNEL_INVALID`, `NOISE_PARAMETER_AMBIGUOUS`, `NOISE_TARGET_NO_MATCH`, `COHERENCE_BUDGET_EXCEEDED`, `STABILIZER_BACKEND_NOISE_INCOMPATIBLE`, `QASM_NOISE_AS_COMMENT`, `NOISE_DROPPED_FOR_BACKEND`, `NOISE_CONTEXT_FIELD_DEPRECATED`.
- **New example**: `examples/vqe-heisenberg-noisy.q.orca.md` (Kandala-shaped two-rate model + readout error).
- **Dependencies**: `add-resource-estimation` (merged) — satisfied. Soft, forward-compatible coupling to `qubit-role-types` and `stabilizer-fast-path-backend` (both queued).
