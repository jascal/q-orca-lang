# The `## noise_model` section

Declare a realistic noise model directly in a `.q.orca.md` machine. The verifier
reads it (validating channels, resolving targets, checking the coherence budget)
and the Qiskit Aer compiler builds the corresponding `NoiseModel` automatically.
Shipped by `add-noise-model-section`.

```markdown
## noise_model

| Channel       | Target              | Parameters                   |
|---------------|---------------------|------------------------------|
| depolarizing  | single_qubit_gates  | p=0.001                      |
| depolarizing  | two_qubit_gates     | p=0.012                      |
| readout_error | all_measurements    | p0given1=0.02, p1given0=0.04 |
```

## Channels

| Channel | Parameters | Notes |
|---|---|---|
| `depolarizing` | `p ∈ [0,1]` | dimension follows the target (1 for single-qubit, 2 for `two_qubit_gates`) |
| `amplitude_damping` | `gamma ∈ [0,1]` *or* a time (`T1`) | single-qubit channel |
| `phase_damping` | `gamma ∈ [0,1]` *or* a time (`T2`) | single-qubit channel |
| `thermal` | `T1`, `T2` (times), optional `n_bar` | single-qubit; installed on single-qubit gates |
| `readout_error` | `p0given1`, `p1given0` | applied to measurements |
| `bit_flip` / `phase_flip` | `p` | Pauli X / Z error |
| `pauli` | `probabilities=[…]` | 4 entries `[I,X,Y,Z]` (single-qubit) or 16 (two-qubit, Aer `PauliError` order `[II,IX,…,ZZ]`, qubit 0 first); must sum to 1 |

A row mixing a probability (`p`/`gamma`) and a time (`T1`/`T2`) for the same
effect is rejected as `NOISE_PARAMETER_AMBIGUOUS` — supply one, not both.

## Targets

| Selector | Meaning |
|---|---|
| `all_gates` | every gate |
| `single_qubit_gates` / `two_qubit_gates` | by arity |
| `all_qubits` | all qubits — the channel is applied at gate operations on every qubit. **Note:** true idle-qubit decay (relaxation on a qubit while *another* qubit is gated) is **not modeled in v1**; it needs per-timestep duration scheduling, a documented follow-up. |
| `all_measurements` | measurement readout (`readout_error`) |
| `qs[N]` | a qubit by index |
| `qs[role:R]` | every qubit with role `R` — **requires `qubit-role-types`**; parses today but is reported `NOISE_TARGET_NO_MATCH` until that capability ships |
| `gates[A,B,…]` | a named list of gates |

## Units

Time-domain values take the SI suffixes `ns`, `us`, `ms`; a bare number is
interpreted as `ns`. `T1=100us` is normalized to `100000.0` (ns) at parse time.

## Backends

- **Qiskit / Aer** — full support; `--noise=off` strips the model.
- **QASM 3** — no native noise grammar, so the section is emitted as a stable
  `// noise: channel=… target=… k=v …` comment block and a
  `NOISE_DROPPED_FOR_BACKEND` warning is raised; the circuit still compiles.
- **Stabilizer / Stim** *(when that backend ships)* — only Pauli channels
  (`depolarizing`, `bit_flip`, `phase_flip`) are accepted; others are rejected
  with `STABILIZER_BACKEND_NOISE_INCOMPATIBLE`.

## Coherence budget

When `thermal`/`T2` is declared and the machine declares a `gate_duration_ns`
context field, the verifier estimates the circuit duration and warns with
`COHERENCE_BUDGET_EXCEEDED` if it exceeds `T2`. Without a declared duration the
check is skipped (not failed).

## Deprecated alias

The legacy single-field form is kept for one release as a deprecated alias:

```markdown
| noise | noise_model | depolarizing(0.01) |
```

It is parsed into a single-row section targeting `all_gates`, compiles
byte-identically to the equivalent section, and raises
`NOISE_CONTEXT_FIELD_DEPRECATED` (whose suggestion shows the section form).
**Removed in v0.8** — migrate to `## noise_model`.

## Worked examples

**Uniform depolarizing (sanity check):**

```markdown
## noise_model
| Channel      | Target    | Parameters |
| depolarizing | all_gates | p=0.005    |
```

**Kandala-shaped two-rate model (IBM-class device):** see
`examples/vqe-heisenberg-noisy.q.orca.md`.

**Full T1/T2 + readout (calibrated benchmark):**

```markdown
## noise_model
| Channel       | Target           | Parameters                   |
| depolarizing  | single_qubit_gates | p=0.0008                   |
| depolarizing  | two_qubit_gates  | p=0.011                      |
| thermal       | all_qubits       | T1=120us, T2=90us            |
| readout_error | all_measurements | p0given1=0.015, p1given0=0.03 |
```
