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

## Limitations

- `fidelity(…)` invariants are not yet expressible in the `## invariants`
  grammar; when they are, fidelity against a non-stabilizer target will require
  the state-vector backend.
- The stabilizer backend is **verification-only** in this release. The
  `q-orca run` / `simulate` sampling path, a Clifford+T magic-state extension,
  and Stim detector-error-model export for decoder benchmarking are follow-ons.
