## 1. Dependency & packaging

- [ ] 1.1 Add a `stabilizer` extras group to `pyproject.toml` pulling in
  `stim`; confirm and pin the minimum `qiskit-aer` version that provides a
  reliable `method="stabilizer"` (the `quantum`/`all` extras currently pull
  `qiskit-aer` unpinned).
- [ ] 1.2 Detect `stim` and the Aer stabilizer method at module load (mirror the
  `AVAILABLE` pattern in `qutip_backend.py` / `cuquantum_backend.py`).

## 2. Clifford classifier (compiler)

- [ ] 2.1 New `q_orca/compiler/stabilizer.py::is_clifford(machine) -> tuple[bool,
  list[QuantumGate]]`: walk the flattened action effects (reuse the existing
  gate-walk used by the parametric/resource passes), tag each gate, return the
  offending list. Derive the gate-name membership from `KNOWN_UNITARY_GATES`.
- [ ] 2.2 Clifford-angle matching: accept `Rx/Ry/Rz(θ)` only when `θ` simplifies
  to `{0, π/2, π, 3π/2}` via `q_orca/angle.py`; everything else is non-Clifford.
- [ ] 2.3 Add `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND` and
  `INVARIANT_REQUIRES_STATEVECTOR` to `q_orca/verifier/types.py`.

## 3. Stabilizer compilation targets (compiler)

- [ ] 3.1 `compile_to_stim(machine) -> stim.Circuit`: map Clifford gates to Stim
  primitives; mid-circuit `measure` → `MR` (when a `reset` effect follows) or
  `M`; classically-controlled Pauli corrections → `CX rec[-1]` / `CZ rec[-1]`.
- [ ] 3.2 `compile_to_qiskit_stabilizer(machine) -> QuantumCircuit`: reuse
  `q_orca/compiler/qiskit.py`, switching only the destination simulator method.

## 4. Backend adapters & registry

- [ ] 4.1 New `q_orca/backends/stim_backend.py` implementing `BackendAdapter`
  (`verify()` returns a `QVerificationResult` of identical shape to the QuTiP
  path by sampling the Stim tableau); register as `stim`.
- [ ] 4.2 New `q_orca/backends/qiskit_stabilizer_backend.py` wrapping
  `AerSimulator(method="stabilizer")`.
- [ ] 4.3 Register both in `q_orca/backends/__init__.py`; add the `stabilizer`
  alias preferring Stim, then Aer-stabilizer, then state-vector fallback via the
  existing `BackendRegistry.get_with_fallback`.

## 5. Selection & dispatch

- [ ] 5.1 Parser: extend `## assertion policy` to accept the `stabilizer_fallback`
  key and the `stabilizer` / `stim` backend values; add `stabilizer_fallback` to
  the `AssertionPolicy` dataclass (default `'error'`).
- [ ] 5.2 `dynamic_verify` gains a `backend` kwarg defaulting to the resolved
  policy/CLI backend; under `auto` it calls `is_clifford` and routes
  Clifford → stabilizer, else → state-vector.
- [ ] 5.3 CLI: accept `stabilizer` / `stim` (and document `auto` as the default)
  on `--backend` for both `verify` and `run`; wire force/refuse +
  `stabilizer_fallback` behaviour through `_resolve_backend` / dispatch; update
  `--backend` help text.
- [ ] 5.4 Force-on-non-Clifford: raise `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND`
  (fatal) unless `stabilizer_fallback: state-vector`, which warns and uses the
  state-vector path.

## 6. Verifier — invariant fallback

- [ ] 6.1 Under the stabilizer backend, emit `INVARIANT_REQUIRES_STATEVECTOR`
  for `fidelity(…)` and `schmidt_rank(…)` invariants; keep sampling-based
  state-category assertions evaluable from tableau samples.

## 7. Examples

- [ ] 7.1 `examples/surface-code-3.q.orca.md`: one round of the distance-3
  rotated surface code (17 physical qubits — intractable for state-vector).
- [ ] 7.2 `examples/bit-flip-repeated.q.orca.md`: three rounds of the 3-qubit
  bit-flip code, each extracting a fresh syndrome with conditional corrections.

## 8. Tests

- [ ] 8.1 `tests/test_stabilizer_backend.py`: `is_clifford` recognition across
  `examples/` — bell, ghz, teleportation, active-teleportation, bit-flip-syndrome
  → True; deutsch-jozsa, qaoa-maxcut, vqe-* → False.
- [ ] 8.2 Clifford-angle acceptance: `Rz(π/2) ≡ S`, `Rx(π) ≡ X`, etc.
- [ ] 8.3 Distribution parity: `active-teleportation` outcome distribution under
  the stabilizer backend matches QuTiP within statistical tolerance at
  `shots=10000` (seeded).
- [ ] 8.4 `NON_CLIFFORD_GATE_IN_STABILIZER_BACKEND` fires on forced stabilizer +
  non-Clifford machine; `stabilizer_fallback: state-vector` downgrades to a warning.
- [ ] 8.5 `INVARIANT_REQUIRES_STATEVECTOR` fires for `fidelity` / `schmidt_rank`
  under the stabilizer backend.
- [ ] 8.6 Auto-routing: Clifford machine selects stabilizer when available, falls
  back to state-vector (with warning) when Stim/Aer absent.
- [ ] 8.7 `surface-code-3` verifies on the stabilizer path within a CI time bound.
- [ ] 8.8 Angle-fold edge case: pin which rotation angles the `angle.py` evaluator
  folds to a Clifford multiple (e.g. `π/4 + π/4` → `π/2`) vs. those it leaves
  un-folded; assert un-folded cases conservatively route to state-vector (correct,
  not wrong).

## 9. Docs

- [ ] 9.1 Document the stabilizer backend in `docs/language/`: backend selection
  (`stim` for best performance vs the `stabilizer` alias), `auto` Clifford
  detection, `stabilizer_fallback`, the invariant restriction, **when to use it**
  (QEC, Clifford randomized benchmarking, high-shot verification), and its
  **performance characteristics** (poly-time tableau vs exponential
  state-vector); mention it in the `## assertion policy` reference.
- [ ] 9.2 Mark `docs/research/spec-stabilizer-fast-path-backend.md` delivered,
  noting the divergence from its pre-build sketch (`verify()` contract reused;
  `## assertion policy` reused instead of a new `## execution` section).
