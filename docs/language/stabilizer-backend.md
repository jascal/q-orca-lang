# Stabilizer (Clifford) fast-path backend

Stage 4b dynamic verification runs on a simulation backend. The default
state-vector backend (QuTiP) is `O(2ⁿ)` in qubit count, so its entanglement
check becomes intractable past a handful of qubits — the 5-qubit
`bit-flip-syndrome` example is about the largest QEC machine it can verify.

The **stabilizer backend** (Stim) verifies *Clifford-only* circuits in
polynomial time. Encoders, syndrome extractors, repeated stabilizer rounds,
graph states, and randomized-benchmarking sequences are all Clifford, so a
distance-3 surface code or a 30-qubit GHZ state — both far past the
state-vector wall — verify in milliseconds with no loss of correctness.

## When to use it

- **Quantum error correction** — encode / syndrome-extract / decode circuits.
- **Clifford randomized benchmarking** — RB sequences are Clifford by
  construction.
- **High-shot or many-qubit verification** where the state-vector path is too
  slow or simply too large to hold in memory.

A circuit is Clifford when every gate is drawn from
`{H, S, S†, X, Y, Z, CNOT, CY, CZ, SWAP}`, a Pauli measurement, or a
classically-controlled Pauli correction; plus `Rx`/`Ry`/`Rz` at angles that are
multiples of `π/2`. Any other gate (`T`, `CCX`/`CCZ`, `MCX`/`MCZ`,
arbitrary-angle rotations) makes the circuit non-Clifford.

## Selecting a backend

Backend selection is the same surface as the other backends — the `--backend`
CLI flag, the `orca.yaml` `backend` key, and the `## assertion policy`
`backend` field — with three stabilizer-aware values:

| Value | Behaviour |
|---|---|
| `auto` (default) | Classify the machine: a Clifford machine routes to the stabilizer backend (when Stim is available), any other to the state-vector backend. |
| `stim` | Force Stim — best performance. |
| `stabilizer` | Stable alias: resolve Stim → Aer-stabilizer → state-vector. |
| `state-vector` | Force the QuTiP state-vector path (escape hatch). |

```bash
q-orca verify examples/bit-flip-syndrome.q.orca.md            # auto → stim
q-orca verify examples/bit-flip-syndrome.q.orca.md --backend stim
q-orca verify examples/vqe-heisenberg.q.orca.md               # non-Clifford → qutip
```

The `--json` report's `backend` block shows the backend that actually ran
(e.g. `stim`), not the literal `auto`.

## Forcing the stabilizer backend on a non-Clifford machine

Forcing `backend: stim` / `stabilizer` on a machine that contains a
non-Clifford gate raises `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND`, naming the
first offending gate. It is fatal by default. To downgrade it to a warning and
fall back to the state-vector path, set `stabilizer_fallback` in the policy:

```markdown
## assertion policy
| Setting              | Value        |
|----------------------|--------------|
| backend              | stabilizer   |
| stabilizer_fallback  | state-vector |
```

## How it works

The stabilizer backend reproduces the state-vector backend's checks without the
exponential cost:

- **Unitarity** holds by construction for Clifford gates — no matrix check.
- **Entanglement** (von Neumann entropy + Schmidt rank across each declared
  bipartition) is read from the stabilizer tableau via the GF(2) rank of its
  check matrix — `S_A = rank_GF2(M_A) − |A|`, Schmidt rank `2^{S_A}`
  (Fattal et al., quant-ph/0406168) — instead of evolving a state vector. The
  verdict matches QuTiP exactly.
- **Collapse completeness** is structural and backend-independent.

## Installation

Stim is an optional dependency:

```bash
pip install 'q-orca[stabilizer]'
```

When Stim is absent, `auto` simply uses the state-vector path, and an explicit
`stim`/`stabilizer` selection falls back to it with a warning — verification is
never lost.

## Sampling (`compile_to_stim`)

Beyond verification, a Clifford machine can be compiled to a runnable circuit and
sampled. `q_orca.compiler.stabilizer.compile_to_stim(machine)` returns a
`stim.Circuit`:

- Clifford gates map to their Stim primitives (`π/2` rotations → `√X`/`√Y`/`S`).
- `measure(qs[i]) -> bits[j]` emits a Stim `M` and records a `bit → record` index.
- Single-clause Pauli feedforward (`if bits[j] == 1: X/Y/Z(qs[k])`) maps to Stim's
  measurement-record-controlled `CX`/`CY`/`CZ rec[-N]`, where `N` is the relative
  offset of `bits[j]`'s record at emit time.

For example, `active-teleportation` (q0 = message, q1+q2 = the Bell pair) compiles
to — Stim args are qubit indices, `M 0 1` measures q0→b0 then q1→b1:

```
H 1             # prepare the q1,q2 Bell pair
CX 1 2
CX 0 1          # Bell-measure q0 against q1
H 0
M 0 1           # b0 = M(q0)  (record -2 after this line),  b1 = M(q1)  (record -1)
CX rec[-1] 2    # if b1 == 1: X(q2)   — b1 is the most recent record
CZ rec[-2] 2    # if b0 == 1: Z(q2)   — b0 is one record earlier
```

`sample_stim_circuit(circuit, shots, seed)` runs the circuit and returns an
outcome→count dict. A secondary target, `compile_to_qiskit_stabilizer(machine)`,
produces a `QuantumCircuit` for `AerSimulator(method="stabilizer")` as a fallback
when Stim is absent. Both paths' sampled distributions match the state-vector
backend (validated at `shots=10000`).

`compile_to_stim` fails fast with a `StabilizerCompileError` rather than emit a
silently-wrong circuit on an unsupported construct: a non-Clifford machine, a
non-Pauli feedforward correction, a `== 0` or **multi-clause AND** feedforward,
or an adaptive `[loop until:]` body.

## Decoding (QEC syndrome → correction)

Single-clause feedforward (teleportation) compiles in-circuit; **real QEC
syndrome decoding** — where a correction depends on the *whole* multi-bit
syndrome — is a classical **decoder** instead. The model is the one from the
QEC primer: errors are chains, the syndrome is their endpoints, and decoding is
**minimum-weight perfect matching** (MWPM). Stim builds the matching graph (the
detector error model); [PyMatching](https://github.com/oscarhiggott/PyMatching)
runs Edmonds' blossom algorithm.

`compile_to_stim_with_detectors(machine)` emits a `DETECTOR` for each stabilizer
measurement (a measurement of an `ancilla`/`syndrome`-role qubit) and an
`OBSERVABLE_INCLUDE` over the logical readout (a `data`-role qubit = Z_L), with
noise drawn from the machine's `## noise_model`. `logical_error_rate(machine,
shots, seed)` (in `q_orca.evaluation.qec`) decodes each shot and returns the
fraction whose decoded correction disagrees with the true logical observable.

End-to-end — a distance-3 bit-flip code at physical error rate `p = 0.05`:

```python
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.evaluation.qec import logical_error_rate

machine = parse_q_orca_markdown(open("examples/bit-flip-code.q.orca.md").read()).file.machines[0]
ler = logical_error_rate(machine, shots=20000, seed=7)
# ler ≈ 0.0076 ≈ 3·p²  — a single data error is corrected, so a logical error
# needs ≥2; decoding pulls the logical rate far below the raw p = 0.05.
```

The logical error rate **falls with code distance** (a bigger code corrects more)
and **rises with the physical error rate** — the trends that confirm the
observable and detectors are correct.

**Single-round and multi-round.** Single-round (code-capacity) decoding gives
each ancilla measurement its own detector. **Multi-round / circuit-level**
decoding is supported once an ancilla is `reset(qs[i])` between rounds (it is
re-initialised via `MR`): the compiler emits a cross-round `DETECTOR` comparing a
stabilizer's record across consecutive rounds. The logical observable is inferred
as a single data qubit (correct for repetition / bit-flip codes); codes whose
`Z_L` is a multi-qubit chain (the surface code) will need an explicit observable
declaration — a planned follow-on. (The quantitative *improves-with-rounds*
benefit needs the full phenomenological noise model — a tuning exercise.)

## Limitations

- `fidelity(…)` invariants are not yet expressible in the `## invariants`
  grammar; when they are, fidelity against a non-stabilizer target will require
  the state-vector backend.
- `compile_to_stim` handles **single-clause** feedforward (teleportation-style).
  Real QEC **syndrome decoding** uses multi-clause AND corrections, which Stim's
  single-record `rec[-N]` controls cannot express in-circuit — that is a decoder
  concern (Stim `DETECTOR` / PyMatching), a follow-on. `compile_to_stim` refuses
  multi-clause feedforward with a clear error.
- A `measure(qs[i]) -> bits[j]` followed by `reset(qs[i])` compiles to a single
  Stim `MR` (measure-and-reset); a standalone `reset(qs[i])` compiles to `R`. A
  `reset` is treated as a stabilizer-compatible operation (it does not make a
  machine non-Clifford).
- Wiring the sampler into `q-orca run` / `simulate`, a Clifford+T magic-state
  extension, and Stim detector-error-model export are follow-ons.
