## Why

Stage 4b dynamic verification (and the sampling-based `## assertion policy`
checks) run on the QuTiP state-vector simulator, whose cost is `O(2^n)` in
qubit count. The existing `bit-flip-syndrome` example (5 qubits) is already the
largest QEC machine we can realistically verify; a single round of the
distance-3 surface code (17 physical qubits) is intractable, and every QEC
example the roadmap calls out (`coverage-analysis-v0.4.md` §2.5, §3.2) is
blocked behind this wall. Yet encoders, syndrome extractors, and repeated
stabilizer rounds are *exactly* the Clifford-only circuits that the
Aaronson–Gottesman stabilizer tableau simulates in polynomial time. A
stabilizer fast-path lets q-orca verify error-correcting codes at
hardware-relevant scale, and routes the all-Clifford Bell/GHZ/teleportation/
syndrome sanity checks through a simulator that makes raising CI shot counts
from 64 to 10 000 free instead of minutes-per-commit.

## What Changes

- Add a **Clifford classifier** (`q_orca/compiler/stabilizer.py::is_clifford`)
  that walks a machine's flattened gate effects and reports whether every gate
  is Clifford (`H, S, S†, X, Y, Z, CX, CY, CZ, SWAP`, Pauli measurement,
  classically-controlled Pauli correction) plus `Rx/Ry/Rz` at angles in
  `{0, π/2, π, 3π/2}` (reusing `q_orca/angle.py`), returning the offending
  gates otherwise.
- Add a **stabilizer verification backend** implementing the shipped
  `BackendAdapter` protocol — registered as `stim` (preferred, wrapping
  [Stim](https://github.com/quantumlib/Stim)) with `stabilizer` as an alias
  that prefers Stim, falls back to `AerSimulator(method="stabilizer")`, then to
  state-vector with a warning. It runs Stage 4b (reachability-by-simulation,
  sampling-based state assertions, backend-agnostic invariants) by sampling a
  stabilizer tableau instead of a state vector. Guidance: prefer `backend: stim`
  for best performance; `backend: stabilizer` is the stable alias that resolves
  Stim → Aer-stabilizer → state-vector.
- Make backend selection **Clifford-aware**: under the default `backend: auto`
  (the `## assertion policy` field and the `--backend` CLI flag already exist),
  a Clifford machine routes to the stabilizer backend and a non-Clifford one to
  the state-vector path. The accepted backend names gain `stabilizer` / `stim`,
  which share the same force/refuse semantics below.
- **Force/refuse semantics**: forcing `backend: stabilizer` on a machine the
  classifier rejects raises a structured
  `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND` (offending gate + source location),
  fatal unless `stabilizer_fallback: state-vector` is declared, in which case a
  warning is emitted and the state-vector path is used.
- **Invariant fallback**: state-vector-only invariants (`fidelity(…)`,
  `schmidt_rank(…)`) cannot be evaluated on a stabilizer tableau and emit
  `INVARIANT_REQUIRES_STATEVECTOR` when attempted under the stabilizer backend.
- Add `examples/surface-code-3.q.orca.md` (one round of distance-3 rotated
  surface code, 17 physical qubits — intractable for state-vector) and
  `examples/bit-flip-repeated.q.orca.md` (three syndrome rounds).

Non-Clifford machines (`T`, `CCX/CCZ`, `MCX/MCZ`, arbitrary-angle rotations)
fall through to the existing QuTiP/cuQuantum/CUDA-Q backends unchanged. The
`backend: stabilizer+magic` decomposition is explicitly **out of scope**.

## Capabilities

### New Capabilities
<!-- none — backends are spec'd within compiler/verifier, matching the shipped qutip/cuquantum/cudaq adapters -->

### Modified Capabilities
- `compiler`: add the Clifford classifier and a stabilizer compilation target
  (machine → Stim / Aer-stabilizer circuit), plus the
  `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND` diagnostic the classifier owns.
- `verifier`: Stage 4b dynamic verification becomes backend-dispatched; Clifford
  machines verify on the stabilizer simulator; state-vector-only invariants emit
  `INVARIANT_REQUIRES_STATEVECTOR` under the stabilizer backend.
- `language`: the backend-selection surface (`## assertion policy` `backend`
  field + `--backend`) accepts `stabilizer` / `stim`, the `auto` default
  performs Clifford auto-detection, and an optional `stabilizer_fallback` key
  governs the force-on-non-Clifford behaviour.

## Impact

- New code: `q_orca/compiler/stabilizer.py` (classifier + Stim/Aer compilation);
  `q_orca/backends/stim_backend.py` + `q_orca/backends/qiskit_stabilizer_backend.py`
  (registered in `backends/__init__.py` and `registry.py`); backend dispatch in
  `q_orca/verifier/dynamic.py` and the `verify`/`run` paths of `q_orca/cli.py`;
  two error codes in `q_orca/verifier/types.py`.
- New optional dependency: `stim` (and the `AerSimulator(method="stabilizer")`
  method from the already-used `qiskit-aer`) behind an extras group, detected at
  module load like the other backends — absence degrades to state-vector. The
  exact `qiskit-aer` floor guaranteeing reliable stabilizer support is confirmed
  and pinned by the packaging task (it is currently unpinned in the extras).
- Edited: `## assertion policy` parsing (accept new backend names +
  `stabilizer_fallback`); new examples; `docs/language/` backend note; mark
  `docs/research/spec-stabilizer-fast-path-backend.md` delivered.
- Backward compatible: machines that never name `stabilizer` and contain any
  non-Clifford gate behave exactly as today (`auto` → state-vector).
- **Dependencies**: the shipped **execution-backends** framework (archived
  2026-04-17) supplies the `BackendAdapter` protocol and `BackendRegistry`.
  Composes with `add-runtime-state-assertions` (sampling-based assertions run
  natively; `fidelity`/`schmidt_rank` fall back) and the `[loop N]` annotation
  (each unrolled iteration re-runs the same Clifford check).
