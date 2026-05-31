## 1. AST + parser

- [ ] 1.1 In `q_orca/ast.py`, add `NoiseChannel(kind, target, parameters)` and `NoiseModelSection(channels, default_units)`; add `noise_model: NoiseModelSection | None` to `QMachineDef`; keep the legacy flat `NoiseModel` only as the alias intermediate (or delete once the alias path constructs `NoiseChannel` directly)
- [ ] 1.2 Add a `## noise_model` section recognizer in `q_orca/parser/markdown_parser.py` (alongside `## context`/`## resources`/etc.), reusing the generic table helper
- [ ] 1.3 `_parse_noise_target`: parse the closed selector grammar into `AllGates | SingleQubitGates | TwoQubitGates | AllMeasurements | AllQubits | QubitIndex | QubitRole | GateList`
- [ ] 1.4 `_parse_noise_params`: parse `k=v` pairs; resolve SI time suffixes `ns|us|ms` to nanoseconds (bare = ns)
- [ ] 1.5 `_parse_noise_row`: assemble a `NoiseChannel` from Channel/Target/Parameters (no schema enforcement — that is the verifier's job)
- [ ] 1.6 Deprecated alias: route the `noise` context field through `_parse_noise_model_string` and wrap into a single-row `NoiseModelSection` targeting `all_gates`

## 2. Verifier rules + diagnostics

- [ ] 2.1 `noise_channel_well_formed` — per-channel schema validation; `NOISE_CHANNEL_INVALID`, `NOISE_PARAMETER_AMBIGUOUS` (mixed time/probability), dimensional-consistency checks
- [ ] 2.2 `noise_target_resolves` — resolve selectors; `NOISE_TARGET_NO_MATCH` for no-op rows; `qs[role:R]` reported unresolved (requires `qubit-role-types`) until roles land
- [ ] 2.3 `coherence_time_vs_circuit_duration` — worst-case path duration (reusing resource-estimation depth/durations) vs `T2`; `COHERENCE_BUDGET_EXCEEDED`; skip when durations absent
- [ ] 2.4 `backend_noise_compatibility` — QASM target → `NOISE_DROPPED_FOR_BACKEND` (compile anyway); stabilizer target → `STABILIZER_BACKEND_NOISE_INCOMPATIBLE` for non-Pauli (dormant until that backend ships); Aer → accept all
- [ ] 2.5 `NOISE_CONTEXT_FIELD_DEPRECATED` (warning) emitted exactly once when the legacy `noise` field is used

## 3. Qiskit Aer compiler

- [ ] 3.1 Replace `_emit_qiskit_noise_model_code` with a per-channel generator iterating `NoiseModelSection.channels`
- [ ] 3.2 Install-call dispatch by target: `add_all_qubit_quantum_error` (broad classes / gate lists), `add_quantum_error` (specific qubits), `add_readout_error` (measurements)
- [ ] 3.3 Error construction per kind: depolarizing / amplitude_damping / phase_damping / thermal (`thermal_relaxation_error` using `## resources` gate duration) / bit_flip / phase_flip / pauli; convert SI times to ns
- [ ] 3.4 Idle-qubit thermal-relaxation insertion when `thermal` targets `all_qubits` (D6)
- [ ] 3.5 `--noise=on|off` flag on `compile`/`verify`; default on when a section is present
- [ ] 3.6 Byte-identical output for the legacy field vs the equivalent one-row section

## 4. QASM compiler

- [ ] 4.1 Emit the section as a `// noise:` comment block at program top (`q_orca/compiler/qasm.py`); no semantic effect

## 5. Example + docs

- [ ] 5.1 Add `examples/vqe-heisenberg-noisy.q.orca.md` — Kandala-shaped two-rate depolarizing + readout error
- [ ] 5.2 Add `docs/language/noise-model.md` — channel catalogue, selector grammar, deprecation timeline, three worked examples (uniform, two-rate, full T1/T2 + readout)
- [ ] 5.3 Mark `docs/research/spec-noise-model-section.md` as delivered

## 6. Tests

- [ ] 6.1 Round-trip a Kandala-shaped model: emitted `NoiseModel.to_dict()` equals a pinned reference; Stage-4b energy estimate within 0.05 of analytic across 10_000 shots
- [ ] 6.2 Coherence-budget warning fires with the numbers in the message
- [ ] 6.3 Stabilizer-backend rejection (non-Pauli) and acceptance (Pauli) — guarded/marked until the stabilizer backend ships
- [ ] 6.4 Selector resolution: `qs[role:ancilla]` → `[1, 2]`; `qs[role:nonexistent]` → `NOISE_TARGET_NO_MATCH`
- [ ] 6.5 Deprecation alias: legacy field parses to a single-row section, emits exactly one `NOISE_CONTEXT_FIELD_DEPRECATED`, and compiles byte-for-byte identically to the section form
- [ ] 6.6 Well-formedness: out-of-range `p`, mixed time/probability params, missing required params each emit the right diagnostic
