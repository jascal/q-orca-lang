# Feature: Stabilizer (Clifford) Fast-Path Backend

> Generated: 2026-04-24 — weekly feature spec session

---

## Feature: Stabilizer Fast-Path Backend

**Summary:** Add a dedicated stabilizer-formalism simulation backend that
automatically detects Clifford-only circuits (or Clifford-only *prefixes* of
arbitrary circuits) and runs them in polynomial time using
Aaronson–Gottesman's stabilizer tableau representation, wrapping either
[Stim](https://github.com/quantumlib/Stim) or the `AerSimulator(method="stabilizer")`
primitive already ships with `qiskit-aer ≥ 0.17`. The dynamic verifier
(Stage 4b) and the `shots=N` execution mode today lean on the QuTiP
state-vector simulator, whose cost is `O(2^n)` in qubit count and collapses
on every QEC example of practical size (5+ data qubits plus
syndrome/ancilla rounds). Since the Clifford group — `{H, S, CNOT,
CZ, X, Y, Z, measurement}` — is exactly the gate set that dominates
encoders, syndrome-extractors, and repeated stabilizer rounds, a stabilizer
backend lets q-orca simulate error-correcting codes at hardware-relevant
scale (hundreds of logical operations, thousands of physical qubits) with
no loss of correctness. Non-Clifford gates (`T`, `Rx(θ)`, `Ry(θ)`,
`Rz(θ)` at non-Clifford angles, `CCX`, `CCZ`, `MCX`, `MCZ`, parametric
rotations at arbitrary angles) fall through unchanged to the existing
QuTiP/cuQuantum/CUDA-Q backends.

---

**Motivation:** The algorithms and use cases this unlocks include:

- **Scalable error-correction verification.** `bit-flip-syndrome.q.orca.md`
  already exists (5 qubits, mid-circuit measurement, conditional
  corrections) but is the largest QEC example q-orca can realistically
  verify on the state-vector path. Surface codes, Steane's 7-qubit code,
  Shor's 9-qubit code, and repeated rounds of the bit-flip / phase-flip
  code are all Clifford-only and all explicitly called out in the coverage
  analysis roadmap (`openspec/roadmap/coverage-analysis-v0.4.md` §2.5,
  §3.2). The state-vector simulator cannot verify even a single round of
  the distance-3 surface code (17 physical qubits). Stim and the Qiskit
  Aer stabilizer method both handle thousands of qubits in milliseconds.
- **Randomized benchmarking and circuit fidelity estimation.** Randomized
  benchmarking is defined entirely on the Clifford group; stabilizer
  simulation turns `shots=10_000` sweeps over 20-qubit RB sequences from
  impossible into routine. This is the canonical NISQ characterization
  protocol and the foundation of IBM's device-fidelity reports.
- **Graph-state protocol verification.** BB84, MBQC (measurement-based
  quantum computing) primitives, and superdense coding — the quantum
  communication demos on the roadmap — are all Clifford circuits once
  basis preparation and measurement are fixed. The full QKD eavesdropping
  demo (three machines × many shots) becomes tractable only with a
  stabilizer backend.
- **Regression-test acceleration.** The existing q-orca test suite spends
  most of its Stage 4b runtime on Bell / GHZ / teleportation / syndrome
  sanity checks, all of which are Clifford. Routing these to the
  stabilizer backend during CI cuts test-suite time substantially and
  lets us raise shot counts from `shots=64` (noise-floor level) to
  `shots=10_000` (statistically tight) without burning minutes of CI per
  commit.
- **Stim-based noise characterization.** Stim's detector-error-model
  emission is the standard input to decoders like PyMatching and the
  Union–Find decoder. A stabilizer backend is the gateway to using q-orca
  to drive real decoder benchmarking experiments on Clifford-encoded
  surface-code circuits.

---

**Proposed Syntax:**

Two surfaces: an opt-in backend declaration, and a CLI flag. The default
behaviour is **automatic detection** — if the parser's gate effect table
contains only Clifford gates and Pauli measurements, the stabilizer
backend is selected automatically when running under `Stage 4b` or
`shots=N`; otherwise the existing state-vector backend is selected. A
user can force-select or force-disable the fast path.

```markdown
# machine SurfaceCode3

> Distance-3 surface code, one round of stabilizer extraction.

## context

| Field   | Type            | Default                                |
|---------|-----------------|----------------------------------------|
| qubits  | list<qubit>     | [q0, q1, q2, q3, q4, q5, q6, q7, q8]   |
| ancilla | list<qubit>     | [a0, a1, a2, a3, a4, a5, a6, a7]       |
| bits    | list<bit>       | [b0, b1, b2, b3, b4, b5, b6, b7]       |

## execution

| Key     | Value      |
|---------|------------|
| shots   | 10000      |
| backend | stabilizer |

## events
- encode
- extract_syndrome
- decode
- correct
```

CLI equivalents:

```bash
q-orca verify examples/surface-code-3.q.orca.md --backend stabilizer
q-orca verify examples/surface-code-3.q.orca.md --backend auto      # default
q-orca verify examples/surface-code-3.q.orca.md --backend state-vector   # force off
```

If a user declares `backend: stabilizer` in `## execution` but the
parser discovers a non-Clifford gate in the action table, the compiler
MUST raise a structured error (`NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND`)
with the offending gate and its source location. The error is fatal
unless the user adds `stabilizer_fallback: state-vector` to the section,
in which case a warning is emitted and the state-vector path is used.

For circuits that are Clifford *except* for a small non-Clifford
magic-state prefix (e.g. a T-gate injection), a future follow-up can add
`backend: stabilizer+magic`, which decomposes the non-Clifford slice
into `2^t` stabilizer branches weighted by magic-state expansion
coefficients. That is explicitly out of scope for this spec; only the
pure-Clifford fast path is included here.

---

**Implementation Sketch:**

### Parser changes

- Add optional `## execution` section grammar. Parser recognizes three
  keys: `shots: int`, `backend: stabilizer | state-vector | auto`,
  `stabilizer_fallback: state-vector | error`. Unknown keys are a
  structured parser error. Absence of the section yields the existing
  defaults (no shots, backend auto).
- Extend `q_orca/ast.py` with an `ExecutionConfig` dataclass carrying
  the three fields above, plumbed into `Machine.execution_config`.

### Compiler changes (new classifier + dispatcher)

- New module `q_orca/compiler/stabilizer.py`:
  - `is_clifford(machine) -> tuple[bool, list[QuantumGate]]` — walks the
    flattened action sequence and tags every gate as Clifford or not.
    Clifford set: `H, S, S†, X, Y, Z, CX, CZ, CY, SWAP`; plus `Rz(θ)` /
    `Rx(θ)` / `Ry(θ)` at angles in `{0, π/2, π, 3π/2}`; plus measurement
    and classically-controlled Pauli corrections. Returns `(False,
    non_clifford_list)` on failure. Angle-matching reuses the existing
    `q_orca/angle.py` simplifier (already shipped, handles symbolic
    `π/2` literals).
  - `compile_to_stim(machine) -> stim.Circuit` — maps each gate into
    Stim's `H`, `S`, `CX`, `MR`, `M`, `DETECTOR`, `OBSERVABLE_INCLUDE`
    primitives. Mid-circuit measurement maps to `MR` (measure-reset) or
    `M` (measure-only) depending on whether the `reset()` effect follows.
    Classical-feedforward conditionals from `add-runtime-state-assertions`
    and the shipped `active-teleportation.q.orca.md` become Stim's
    `CX rec[-1]` / `CZ rec[-1]` instructions.
  - `compile_to_qiskit_stabilizer(machine) -> QuantumCircuit` — same
    circuit object the existing Qiskit compiler produces, but destined
    for `AerSimulator(method="stabilizer")` rather than the default
    method. This path reuses 90 % of `q_orca/compiler/qiskit.py`.
- New backend module `q_orca/backends/stim_backend.py`:
  - Implements the existing `Backend` protocol from
    `q_orca/backends/base.py` (already used by `qutip_backend.py`,
    `cuquantum_backend.py`, `cudaq_backend.py`).
  - Registers as `"stim"` and as `"stabilizer"` (alias) in
    `q_orca/backends/registry.py`.
  - `run(circuit, shots) -> MeasurementResults` — hands off to Stim's
    `sample()` and reshapes into the existing `MeasurementResults`
    dataclass so downstream code (verifier assertions, context
    updates) is oblivious to the backend choice.
- New backend module `q_orca/backends/qiskit_stabilizer_backend.py`:
  - Thin wrapper over `AerSimulator(method="stabilizer")` for users who
    already have `qiskit-aer` but not Stim.
  - Registry alias: `"stabilizer"` prefers Stim if available, otherwise
    Qiskit Aer stabilizer, otherwise falls back to state-vector with a
    warning.
- Compiler dispatch in `q_orca/cli.py` (verify and run paths): after
  parsing, call `stabilizer.is_clifford(machine)`; if True and backend
  is `auto`, route to stabilizer; if False and backend is `auto`, route
  to the existing state-vector path; if explicit, honour the user choice
  with the error behaviour above.

### Verifier changes

- The static verifier is untouched — stabilizer selection is a *runtime*
  concern, not a structural one. Unitarity / no-cloning / completeness
  still apply.
- The dynamic verifier (`q_orca/verifier/dynamic.py`) gains a `backend:`
  kwarg that defaults to `machine.execution_config.backend`. All three
  existing Stage 4b checks (reachability by simulation, state-category
  sampling for the `add-runtime-state-assertions` change, invariants
  evaluation for the extended `## invariants` work in the roadmap) are
  backend-agnostic because they consume `MeasurementResults`, not raw
  state vectors. Pure state-vector-only invariants (`fidelity(|ψ>,
  |Φ+>)`, `schmidt_rank(…)`) cannot run under the stabilizer backend
  and MUST emit `INVARIANT_REQUIRES_STATEVECTOR` when attempted.

### New tests / examples needed

- `tests/test_stabilizer_backend.py`:
  - `is_clifford` recognition across every example in `examples/` —
    bell, ghz, teleportation, bit-flip-syndrome must be True;
    vqe-rotation, qaoa-maxcut, deutsch-jozsa, vqe-heisenberg must be
    False (they contain `Rx(θ)` / `Rz(θ)` at arbitrary angles).
  - Clifford-angle acceptance for `Rz(π/2) ≡ S`, `Rx(π) ≡ X`, etc.
  - Measurement + feedforward end-to-end on `active-teleportation`:
    result distribution under stabilizer backend matches QuTiP
    result distribution (within statistical tolerance) at `shots=10000`.
  - `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND` fires when user forces
    stabilizer on a non-Clifford machine.
- `examples/surface-code-3.q.orca.md`: one round of the distance-3
  rotated surface code. 17 physical qubits — intractable for the
  state-vector path, routine for stabilizer.
- `examples/bit-flip-repeated.q.orca.md`: three rounds of the 3-qubit
  bit-flip code, each round extracting a fresh syndrome and applying
  conditional corrections. Directly motivates the backend by being the
  first example in which the state-vector path measurably slows CI.
- `demos/error_correction_pipeline/` extension: run a decoder
  benchmarking sweep across shot counts under the stabilizer backend.

---

**Complexity:** Medium — Stim integration and the Clifford detector are
both well-scoped; the main care is ensuring `MeasurementResults`
round-tripping is identical across backends so no user-facing downstream
code (assertions, context updates, invariants) has to change.

**Priority:** High — this is a prerequisite for every QEC example on
the roadmap, and the coverage analysis explicitly lists QEC and the
associated demo as underserved. Also the fastest way to make CI
materially faster without shrinking coverage.

**Dependencies:**
- Requires the shipped **execution backends** framework (archived
  2026-04-17) for the `Backend` protocol and registry.
- Composes with but does **not** require:
  - In-flight `add-resource-estimation` (same backend counts the same
    CX / depth metrics via a separate path).
  - In-flight `add-runtime-state-assertions` (stabilizer backend
    supports sampling-based `classical` / `superposition` / `entangled`
    / `separable` assertions natively; `fidelity` / `schmidt_rank`
    gracefully fall back to state-vector with a warning).
  - Queued `[loop N]` annotation (each unrolled iteration passes through
    the same Clifford check; this composes trivially).

**Literature:**

- Aaronson & Gottesman, "Improved simulation of stabilizer circuits"
  (2004), `quant-ph/0406196` — canonical tableau algorithm;
  `O(n² · m)` for an `n`-qubit, `m`-gate Clifford circuit.
- Bravyi & Maslov, "Hadamard-free circuits expose the structure of the
  Clifford group" (2021) — Qiskit's Clifford-class internals build on
  this decomposition.
- Fowler, Mariantoni, Martinis & Cleland, "Surface codes" (2012),
  `1208.0928` — the direct QEC motivator; indexed in q-orca-kb.
- Steane, "Multiple particle interference and quantum error correction"
  (1996), `quant-ph/9605043` — indexed.
- "Simulating quantum circuits with ZX-calculus reduced stabiliser
  decompositions" (Kissinger & van de Wetering, 2022) — bridge to the
  ZX-calculus optimization pass (see companion spec) by giving Stim /
  stabilizer-aware compilation a principled way to handle Clifford+T
  slices as an incremental next step.
- Qiskit Aer primitives documentation — the `method="stabilizer"`
  simulator (`qiskit-aer ≥ 0.17`, indexed in q-orca-kb).
- Huang & Martonosi, "Statistical assertions for validating patterns
  and finding bugs in quantum programs" (ISCA 2019) — motivates the
  sampling-based invariants this backend supports natively.

---
