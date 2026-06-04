## Context

The shipped execution-backends framework (archived 2026-04-17) defines a
single contract: `BackendAdapter.verify(machine, options) -> (QVerificationResult,
BackendResult)`. `qutip_backend`, `cuquantum_backend`, and `cudaq_backend` all
implement it by delegating to `dynamic_verify[_gpu]` — i.e. backends are
**Stage 4b dynamic-verification** simulators, not a separate run-path engine.
Backend selection already exists on two surfaces: the `--backend` CLI flag
(`verify` and `run`, resolved by `_resolve_backend` over `orca.yaml`) and the
`## assertion policy` `backend: 'auto' | <name>` field (language spec
§"Assertion Policy Section"). The QuTiP path is `O(2^n)`, so the largest QEC
machine we can verify is `bit-flip-syndrome` (5 qubits); one distance-3
surface-code round (17 qubits) is out of reach.

The research draft `docs/research/spec-stabilizer-fast-path-backend.md` predates
the framework and assumes a `run(circuit, shots) -> MeasurementResults`
interface and a brand-new `## execution` section. Neither exists; this design
re-grounds the feature on the shipped `verify()` contract and the existing
backend-selection surfaces.

## Goals / Non-Goals

**Goals:**
- A `stim` / `stabilizer` `BackendAdapter` that verifies Clifford machines on a
  stabilizer tableau in polynomial time, producing a `QVerificationResult`
  indistinguishable in shape from the QuTiP path.
- Clifford-aware `auto` selection: Clifford → stabilizer, non-Clifford →
  state-vector, with no new in-file syntax.
- Verify a distance-3 surface-code round and multi-round bit-flip codes that the
  state-vector path cannot reach; let CI raise Clifford shot counts essentially
  for free.

**Non-Goals (v1):**
- `backend: stabilizer+magic` (Clifford+T magic-state branching) — Open Q1.
- Accelerating the `q-orca run` iterative simulate path — v1 targets the Stage
  4b verification + assertion-sampling path (the `BackendAdapter` contract).
  Open Q2.
- Stim detector-error-model / decoder (PyMatching) emission — Open Q3.
- A new `## execution` section — reusing `## assertion policy` instead (D1).

## Decisions

### D1 — Reuse existing backend-selection surfaces, not a new `## execution` section
The research draft's `## execution` block duplicates the shipped `## assertion
policy` `backend` field and `--backend` flag. We extend those: the accepted
backend names gain `stabilizer` and `stim`, and `## assertion policy` gains one
optional key `stabilizer_fallback: 'state-vector' | 'error'` (default `error`).
*Alternative considered:* a dedicated `## execution` section (per the draft) —
rejected as a second source of truth for backend selection.

### D2 — Stabilizer is a Stage-4b verification backend (matches the shipped contract)
`StabilizerBackend.verify()` runs the same three Stage-4b checks the QuTiP
backend runs (reachability-by-simulation, sampling-based `## assertion policy`
state checks, backend-agnostic invariants) by sampling a stabilizer tableau. It
returns a `QVerificationResult`; downstream code (assertions, context updates)
stays oblivious to the backend. The research draft's `MeasurementResults`
round-tripping concern reframes to: **`QVerificationResult` parity** between
backends, pinned by a distribution-equivalence test (D7).

### D3 — Clifford classifier (`q_orca/compiler/stabilizer.py::is_clifford`)
`is_clifford(machine) -> (bool, list[non_clifford_gate])` walks the flattened
action effects (the existing gate-walk used by the parametric/resource passes).
Clifford set: `H, S, S†(Sdg), X, Y, Z, CX, CY, CZ, SWAP`, Pauli measurement, and
classically-controlled Pauli corrections; plus `Rx/Ry/Rz(θ)` when `θ` simplifies
to `{0, π/2, π, 3π/2}` via the shipped `q_orca/angle.py` evaluator. Gate names
are cross-checked against `KNOWN_UNITARY_GATES` (single source of truth, per the
parser's `_format_known_gate_list` pattern) so a newly added gate defaults to
*non-Clifford* until explicitly classified — conservative and safe.

### D4 — Backend availability and preference order
Two thin adapters detect their dependency at module load (like the others):
`stim_backend` (wraps Stim) and `qiskit_stabilizer_backend` (wraps
`AerSimulator(method="stabilizer")`, `qiskit-aer ≥ 0.17`). Registered as `stim`
and `stabilizer`; the `stabilizer` alias prefers Stim, then Aer-stabilizer, then
falls back to state-vector via the existing `BackendRegistry.get_with_fallback`.
`stim` ships behind a `stabilizer` extras group; absence degrades gracefully.

### D5 — `auto` routing and force/refuse semantics
- `backend: auto` (default): call `is_clifford`; True → `stabilizer`, False →
  `qutip`. Dispatch lives where `_resolve_backend` already runs (CLI verify/run)
  and in `dynamic_verify`'s backend kwarg.
- `backend: stabilizer` forced on a non-Clifford machine → compiler raises
  `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND` (first offending gate + source span),
  fatal unless `stabilizer_fallback: state-vector`, which downgrades to a
  warning and uses the state-vector path.
- `backend: state-vector` forced → never auto-routes (escape hatch).

### D6 — Invariant fallback
Sampling-based state-assertion categories (`classical`/`superposition`/
`entangled`/`separable`) are evaluated natively from tableau samples.
State-vector-only invariant forms — `fidelity(|ψ>, …)` and `schmidt_rank(…)` —
have no tableau analogue; attempting them under the stabilizer backend emits
`INVARIANT_REQUIRES_STATEVECTOR` (error) naming the invariant, so the user
either drops the invariant or forces `backend: state-vector`.

### D7 — Compilation to Stim / Aer-stabilizer
`compile_to_stim(machine) -> stim.Circuit` maps gates to Stim primitives
(`H, S, CX, CZ, …`), mid-circuit `measure` to `MR` (measure-reset, when a
`reset` effect follows) or `M`, and classically-controlled Pauli corrections to
Stim's `CX rec[-1]` / `CZ rec[-1]`. The Aer path reuses the existing
`q_orca/compiler/qiskit.py` circuit object, switching only the simulator method.
A parity test runs `active-teleportation` on both stabilizer and QuTiP at
`shots=10000` and asserts the outcome distributions agree within statistical
tolerance.

## Risks / Trade-offs
- **Symbolic angle that *could* fold to a Clifford multiple but the evaluator
  doesn't** (e.g. `π/4 + π/4` = `π/2`) → classifier conservatively returns
  non-Clifford → state-vector (correct, just slower — never wrong). Mitigation:
  reuse the shipped `angle.py` simplifier (handles `π/2` literals); a test pins
  the known-folding cases so a regression is visible. Aggressive symbolic folding
  is out of scope for v1.
- **Stim/qiskit-aer absent in an environment** → `auto` silently uses
  state-vector; forced `stabilizer` falls back per registry with a warning.
  Mitigation: extras group + module-load detection mirrors the existing backends.
- **Measurement/feedforward mapping subtleties** (`MR` vs `M`, `rec[-1]`
  targeting) → the single highest-care area. Mitigation: the distribution-parity
  test on `active-teleportation` (D7) gates correctness.
- **Distribution parity tolerance** chosen too tight → flaky CI. Mitigation:
  Wilson-score-style bound at `shots=10000`, seeded.

## Migration Plan
Additive. A machine that never names `stabilizer`/`stim` and contains any
non-Clifford gate routes to state-vector under `auto` — today's behaviour,
unchanged. `stim` is an opt-in extra; CI installs it to exercise the fast path.
Rollback = revert the change and drop the extras group; no data or spec
migration.

## Open Questions
1. `backend: stabilizer+magic` Clifford+T magic-state branching — explicit
   follow-on (bridges to the ZX-calculus optimization pass spec).
2. Routing the `q-orca run` iterative simulate path through the stabilizer
   backend (the framework today only spans Stage-4b verification).
3. Stim detector-error-model emission to feed PyMatching / Union-Find decoders
   for real decoder-benchmarking experiments — high-value follow-on.
4. Default preference when both Stim and Aer-stabilizer are present (Stim is
   faster; pinned to Stim in v1).
5. A per-invariant backend-requirement escape hatch (e.g.
   `fidelity(...) [requires: state-vector]`) so a state-vector-only invariant
   can coexist with a stabilizer-verified machine rather than forcing a
   whole-machine backend choice. Deferred — `INVARIANT_REQUIRES_STATEVECTOR` is
   the v1 behaviour.
