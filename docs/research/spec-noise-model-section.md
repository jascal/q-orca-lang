# Spec: Declarative `## noise_model` Section

**Status:** Draft
**Date:** 2026-05-01
**Priority:** Medium

> Generated: 2026-05-01 — weekly feature spec session

---

## Summary

Promote noise modelling from the present *single-context-field* hack
(a `noise: noise_model = depolarizing(0.01)` row in `## context`
that the Qiskit compiler parses with a regex) into a first-class
top-level `## noise_model` section. The new section is a tabular
declaration of channels, each row binding a channel kind
(`depolarizing`, `amplitude_damping`, `phase_damping`, `thermal`,
`readout_error`) to a target scope (`all_gates`, `single_qubit_gates`,
`two_qubit_gates`, `all_measurements`, or a specific qubit/role
selector) and its parameters. The Qiskit Aer compiler builds the
corresponding `NoiseModel` instance automatically; the verifier
warns when declared `T1`/`T2` are inconsistent with the static
gate-duration estimate; the resource-estimation pipeline picks up
noise-aware fidelity bounds and surfaces them on the existing
`error_rate(...)` and `fidelity(...)` invariants (queued for a
follow-on `extended-invariants` change).

This change is the second-highest-leverage feature in the v0.4
coverage roadmap (§4.7) for the same reason that
`add-resource-estimation` was the first: practitioners ask
*how good* and *how expensive*, in that order, before they ask
anything else. The current single-channel hack answers neither
question well — it cannot express the asymmetry between single- and
two-qubit gate errors that defines every NISQ device, cannot
express readout error at all, and cannot express per-qubit
T1/T2 inhomogeneity, all of which Kandala et al.
(`1704.05018`, indexed in `q-orca-kb` wing
`q-orca-implementations` room `noise-models`) treat as the minimum
faithful model of a real superconducting backend.

---

## Motivation

**The user problem.** Today a machine author who wants to verify
that a circuit survives a realistic noise budget has to:

1. Drop a single `noise: noise_model = depolarizing(0.01)` row in
   the `## context` table.
2. Accept the same depolarizing rate on `H`, `CNOT`, `T`, and
   measurements alike — even though the physics ratio is closer
   to `1 : 10 : 1 : 50` on every IBM and IonQ device shipped to
   date.
3. Hand-write a Python wrapper around the compiled Qiskit circuit
   to add measurement readout error, T1/T2 channels, and
   per-qubit calibration data — none of which the q-orca compiler
   can express.

This is a roughly 50-line ad-hoc Python file per benchmark, and the
machine spec itself loses any record that the benchmark was even
*supposed* to be noisy. When the benchmark drifts from the noise
file, nothing in the q-orca pipeline catches it.

**The current workaround.** Two patterns appear in the
benchmarks/ scaffold added in PR #42:

- *"Pretend the existing single channel is enough"* — used for
  Bell-state and GHZ benchmarks where a uniform depolarizing rate
  is genuinely defensible because the circuit has only two gate
  types.
- *"Compile to QASM, hand off to a Python script that loads
  qiskit-aer's `NoiseModel.from_backend(FakeKolkata)`"* — used for
  the VQE-Heisenberg and bit-flip-syndrome benchmarks. This gives
  realistic device fidelity numbers but the noise model is now
  invisible to the q-orca verifier.

Neither lets the verifier reason about the noise. Neither lets the
resource-estimation pipeline produce a fidelity prediction. And
neither survives a refactor of the underlying machine — the
context-field hack persists; the Python wrapper goes stale.

**Why now.** Three forces converge:

- The just-merged resource-estimation change defines `gate_count`,
  `cx_count`, `t_count`, and `depth` as first-class context-derived
  metrics. Combining those with a per-channel error rate is exactly
  the math behind the standard NISQ-circuit fidelity estimate
  `F ≈ ∏_g (1 - ε_g)` (Kandala et al. `1704.05018` §III). The
  inputs are now available; only the noise declaration is missing.
- The queued `extended-invariants` follow-on (roadmap §4.6) names
  `error_rate(|state⟩) <= 0.01` and `coherence_time(q0) <= T2` as
  invariants. Neither has a meaningful definition without a
  noise-model section.
- The forthcoming **stabilizer fast-path backend** (queued spec
  `spec-stabilizer-fast-path-backend.md`) restricts noise to the
  Pauli channels (`depolarizing`, bit-flip, phase-flip) that Stim
  natively supports. Defining the noise-model schema *now* lets
  the stabilizer compiler reject incompatible channels at
  compile-time rather than failing at simulation-time.

---

## Proposed Syntax / API

### Section grammar

```markdown
## noise_model

| Channel            | Target               | Parameters                   |
|--------------------|----------------------|------------------------------|
| depolarizing       | single_qubit_gates   | p=0.001                      |
| depolarizing       | two_qubit_gates      | p=0.012                      |
| amplitude_damping  | all_qubits           | T1=100us                     |
| phase_damping      | all_qubits           | T2=80us                      |
| thermal            | qs[role:ancilla]     | T1=60us, T2=40us             |
| readout_error      | all_measurements     | p0given1=0.02, p1given0=0.04 |
```

**Channel column** (closed enum). `depolarizing | amplitude_damping
| phase_damping | thermal | readout_error | bit_flip | phase_flip |
pauli`. The `pauli` row accepts a fully-general 16-element
single-qubit (or 256-element two-qubit) Pauli channel via a
`probabilities=...` parameter; the others are sugar.

**Target column** (closed selector grammar). `all_gates |
single_qubit_gates | two_qubit_gates | all_measurements |
all_qubits` for the broad classes; `qs[N]` to target a qubit by
index; `qs[role:R]` to target every qubit declared with role `R`
in the `## context` (couples cleanly with the queued
`qubit-role-types` proposal); `gates[H,X,CNOT]` to target a list
of gate names. The selector is parsed with the existing
markdown-table-cell infix grammar from
`q_orca/parser/markdown_parser.py`.

**Parameters column** (free-form `k=v` pairs). Per-channel
schemas (validated by the verifier):

- `depolarizing` — `p: float in [0, 1]`
- `amplitude_damping`, `phase_damping` — either `gamma: float in
  [0, 1]` or `T1=...` / `T2=...` (with auto-conversion against
  the gate duration declared in `## resources`)
- `thermal` — `T1`, `T2`, optional `n_bar` for thermal occupation
- `readout_error` — `p0given1`, `p1given0`
- `bit_flip`, `phase_flip` — `p`
- `pauli` — `probabilities=[p_I, p_X, p_Y, p_Z]` for single-qubit;
  the 16-element list for two-qubit

Time-domain parameters take the SI suffixes `ns | us | ms`; missing
suffix is interpreted as `ns`. The verifier rejects
dimensionally-inconsistent parameters
(`thermal` with no time unit, `depolarizing` with one).

### CLI

```bash
q-orca compile examples/vqe-heisenberg.q.orca.md \
  --target=qiskit \
  --noise=on
# emits a NoiseModel built from the ## noise_model section

q-orca verify examples/vqe-heisenberg.q.orca.md --noise=on
# additionally checks fidelity / coherence invariants under the model

q-orca compile examples/vqe-heisenberg.q.orca.md \
  --target=qiskit \
  --noise=off
# strips the noise section; emits a noiseless circuit
```

The current `noise: noise_model = ...` context-field syntax is kept
for one release as a *deprecated* alias that gets parsed into a
single-row `## noise_model` section and emits a deprecation
diagnostic `NOISE_CONTEXT_FIELD_DEPRECATED` pointing at the new
section form. Removed in v0.8.

---

## Implementation Sketch

**Parser** (`q_orca/parser/markdown_parser.py`, ~150 LOC).
Add a `## noise_model` recognizer alongside the existing `##
context`, `## events`, `## actions`, `## invariants`,
`## resources`, `## verification rules` recognizers. Reuse the
generic markdown-table parsing helper. New per-row parser
`_parse_noise_row` that dispatches by `Channel` value into one of
the per-kind sub-parsers; selector-column parser
`_parse_noise_target` that returns one of `AllGates |
SingleQubitGates | TwoQubitGates | AllMeasurements | AllQubits |
QubitIndex(int) | QubitRole(str) | GateList(list[str])`.

**AST** (`q_orca/ast.py`, ~50 LOC). Replace the existing flat
`NoiseModel` dataclass with:

- `NoiseChannel` (kind, target, parameters dict)
- `NoiseModelSection` (channels: list[NoiseChannel], default_units)

Add `noise_model: Optional[NoiseModelSection]` to `QMachineDef`.
The legacy `noise` context-field path still constructs a
single-channel `NoiseChannel` via the deprecation-alias parser.

**Verifier**, four new rules:

1. `noise_channel_well_formed` — per-row schema validation
   (parameters present, in range, dimensionally consistent). New
   diagnostic `NOISE_CHANNEL_INVALID`.
2. `noise_target_resolves` — per-row check that the selector
   matches at least one extant gate / qubit / measurement; warn
   on no-op rows. New diagnostic `NOISE_TARGET_NO_MATCH`.
3. `coherence_time_vs_circuit_duration` — if
   `## resources` declares per-gate durations and the noise model
   declares T1/T2, sum the worst-case path duration through the
   transition graph and warn if it exceeds T2. Reuses the depth
   estimate from the resource-estimation pipeline. New diagnostic
   `COHERENCE_BUDGET_EXCEEDED`.
4. `backend_noise_compatibility` — when compile target is
   stabilizer / Stim, reject non-Pauli channels with
   `STABILIZER_BACKEND_NOISE_INCOMPATIBLE`. When target is
   `qutip`, allow all channels. When target is QASM 3.0, emit
   noise as `// noise:` comments only (QASM 3.0 has no native
   noise grammar) with diagnostic
   `QASM_NOISE_AS_COMMENT`.

**Qiskit compiler** (`q_orca/compiler/qiskit.py`, ~200 LOC).
Replace the existing single-channel `_emit_qiskit_noise_model_code`
with a per-target code generator. The generated Python builds a
`qiskit_aer.noise.NoiseModel` by iterating the channels: each row
calls one of `add_quantum_error`, `add_all_qubit_quantum_error`,
or `add_readout_error` depending on its target and channel kind.
Time-domain parameters convert to Kraus operators via the
`thermal_relaxation_error` helper, using the gate-duration
estimate from the `## resources` section.

**QASM compiler** (`q_orca/compiler/qasm.py`, ~30 LOC).
Emit the noise rows as `// noise:` comment block at the top of
the program. No semantic effect.

**Stabilizer compiler hook** (~30 LOC, paired with the
stabilizer-fast-path spec). Reject non-Pauli channels at
compile-time; map allowed channels onto Stim's
`DEPOLARIZE1`/`DEPOLARIZE2`/`X_ERROR`/`Z_ERROR` instructions.

**Documentation** (`docs/language/noise-model.md`, ~150 lines).
Cover the channel catalogue, target selector grammar, the
deprecation timeline for the context-field alias, and three
worked examples (uniform depolarizing for sanity check, Kandala-
shaped two-rate model for IBM-class devices, full T1/T2 + readout
for a calibrated benchmark).

**Total estimate.** ~600 LOC implementation + ~300 LOC tests +
~150 lines of docs. About a week of focused work.

---

## Test Cases

1. **Round-trip a Kandala-shaped model.** A new
   `examples/vqe-heisenberg-noisy.q.orca.md` declares the
   asymmetric two-rate depolarizing model
   (`single_qubit_gates: p=0.001`, `two_qubit_gates: p=0.012`) plus
   `readout_error: p0given1=0.02, p1given0=0.04`. The Qiskit
   compiler emits a `NoiseModel` whose
   `to_dict()` round-trip equals a hand-written reference. Stage 4b
   simulation under the model produces a Heisenberg ground-state
   energy estimate within 0.05 of the analytic value across `shots
   = 10_000`.

2. **Coherence-budget warning fires.** A test machine declares
   `T1=10ns, T2=8ns` plus a 20-gate sequence with declared
   per-gate duration `2ns`. Verifier emits
   `COHERENCE_BUDGET_EXCEEDED` (40ns circuit > 8ns T2) with the
   numbers in the diagnostic message.

3. **Stabilizer-backend rejection.** A test machine declares
   `amplitude_damping(0.05)` and is compiled with
   `--target=stabilizer`. Verifier emits
   `STABILIZER_BACKEND_NOISE_INCOMPATIBLE` and refuses to compile.
   Same machine with only `bit_flip(0.01)` compiles successfully.

4. **Selector resolution.** A test machine declares
   `qs[role:ancilla]` as the target of a thermal channel; the
   `## context` declares `qubits = [q0:data, q1:ancilla, q2:ancilla]`.
   Verifier resolves the selector to `[1, 2]` and the emitted
   Qiskit code applies the channel only to those two indices. A
   second test with a `qs[role:nonexistent]` target emits
   `NOISE_TARGET_NO_MATCH`.

5. **Deprecation alias.** A test machine using the legacy
   `noise: noise_model = depolarizing(0.01)` context-field form
   parses successfully into a single-row `NoiseModelSection` and
   emits exactly one
   `NOISE_CONTEXT_FIELD_DEPRECATED` diagnostic. Compile output
   matches the equivalent `## noise_model` section form
   byte-for-byte.

---

## Dependencies

- **`add-resource-estimation`** (merged) — provides the
  per-gate duration and gate-count infrastructure that the
  coherence-budget verifier rule and the time-domain parameter
  conversion both rely on. No reverse dependency.
- **`qubit-role-types` (queued)** — the `qs[role:R]` target
  selector requires the role-types syntax. We can ship this spec's
  selector grammar with the role variant *parseable but rejected*
  if role-types hasn't merged yet, then enable it in a one-liner
  follow-up. Soft dependency.
- **`stabilizer-fast-path-backend` (queued)** — defines the
  contract for which noise channels Stim accepts. We co-design the
  rejection behaviour now and finalize when stabilizer-fast-path
  lands. No hard dependency in either direction; this spec ships
  fine without stabilizer support.
- **`extended-invariants` (queued, roadmap §4.6)** — adds the
  `fidelity(...)`, `error_rate(...)`, `coherence_time(...)`
  predicates that consume noise-model output. Best landed *after*
  this spec.
- **`bounded-loop-annotation` (this session, companion spec)** —
  no interaction. Disjoint parts of the parser and compiler.

---

## Open Questions

1. **Per-qubit T1/T2 inhomogeneity.** A real device has a different
   T1 per qubit. The selector grammar above lets you write
   one row per qubit, but that's verbose for a 27-qubit
   benchmark. **Options:** (a) accept it; users with calibration
   data write a Python helper that emits the q-orca section; (b)
   add a `from_calibration_file: path/to/cal.json` annotation that
   the parser dereferences; (c) wait for hardware-aware compile
   passes (out of scope here). **Tentative choice: (a) for v0.7
   ship; revisit (b) if user feedback demands.**

2. **Time-domain vs probability-domain mixing.** A row that
   declares `amplitude_damping` with `gamma=0.05` is fine; same
   row with `T1=100us` is also fine; *both* in the same row is an
   error. Should the verifier auto-convert when both are present
   *and* consistent? **Tentative choice: no — reject as
   `NOISE_PARAMETER_AMBIGUOUS`. Auto-conversion silently hides
   user mistakes.**

3. **Noise on idle qubits.** A qubit that is *idle* during a
   gate on another qubit still suffers T1/T2 decay. Qiskit Aer's
   `thermal_relaxation_error` requires an explicit duration
   parameter to model this. Should q-orca auto-insert idle-noise
   on every qubit per gate-time? **Tentative choice: yes when
   `thermal` is declared on `all_qubits`; no otherwise. Document
   the heuristic clearly.**

4. **Readout error and the `[assert: …]` annotations.** The
   queued runtime-state-assertions proposal samples the simulator
   to verify per-state predicates. Should those samples run
   *under* the declared noise model (more realistic but flakier
   assertions) or against a noiseless reference (deterministic
   but ignores the very thing we're modelling)? **Tentative
   choice: noiseless by default with a `## assertion policy`
   field `under_noise: bool = false` to opt in.** The runtime-
   assertions spec will need a small follow-up to thread this
   through.

5. **Backend selection when noise is declared but the chosen
   backend can't model it.** Today the user picks the backend via
   `--target=`. If they pick `qasm3` and declare a thermal
   channel, the channel is silently dropped (QASM 3 has no noise
   grammar). **Tentative choice: emit a warning
   `NOISE_DROPPED_FOR_BACKEND` listing the channels that won't be
   simulated and naming the backend, but compile successfully.**

