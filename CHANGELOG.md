# Changelog

## Unreleased

### Added

- **Parametric actions** — action signatures now accept typed positional parameters (`int` for `qs[...]` subscripts and `angle` for rotation-gate angles) after the leading qubit-list parameter. Call sites in the transitions table supply literal arguments; the compiler substitutes them into a fresh copy of the effect string per site. One `query_concept | (qs, c: int) -> qs | Hadamard(qs[c])` row replaces N copy-pasted actions. Parameters are compile-time constants — out-of-range subscripts and unbound identifiers raise structured parse-time errors that name the offending transition. Zero-parameter signatures (`(qs) -> qs`, `(ctx) -> ctx`) parse unchanged, so every existing example is additive-compatible.
- **New example `examples/larql-polysemantic-12.q.orca.md`** — 12-qubit concept register, 12 non-orthogonal concept vectors (pairwise overlap 1/2), one parametric `query_concept(c: int)` action stamping 12 call sites from one template. Documents the analytic polysemy / cross-talk table in the leading paragraph.
- **New demo `demos/larql_polysemantic_12/demo.py`** — runs 12 independent single-query Qiskit simulations at 1024 shots each and recovers the analytic polysemy scores (≈ 75% on in-feature concepts, ≈ 33.3% cross-talk floor on out-of-feature) within Monte-Carlo tolerance.
- **Structured-overlap polysemantic example, demo, and Gram helper** — companion to `larql-polysemantic-12` that swaps the flat Hadamard dictionary for a *clustered* concept geometry on a compact 3-qubit register. `examples/larql-polysemantic-clusters.q.orca.md` encodes 12 concepts in 3 clusters of 4 (capitals, fruits, vehicles) via a multi-angle parametric `prepare_concept(a, b, c)` + `query_concept(a, b, c)` pair (intra-cluster overlap 0.72 uniform, inter-cluster < 0.10 — a block-structured Gram matrix). `demos/larql_polysemantic_clusters/demo.py` prints an ASCII Gram heatmap and recovers the three-tier polysemy column `1.0 / 0.72 / ≲ 0.09` empirically. New optional helper `q_orca.compute_concept_gram(machine, concept_action_label="query_concept")` returns the analytic N×N overlap matrix for any machine that follows the product-state preparation convention; raises `ConceptGramConfigurationError` when the convention is violated.

### Changed

- Backwards-compatible: no behavior change for existing machines. Both halves of `extend-gate-set-and-parametric-actions` (multi-controlled gates, parametric actions) are additive.

---

## 0.5.0 (2026-04-21)

### Added

- **Pluggable execution backends** — new backend abstraction lets machines compile to `qutip`, `cuquantum`, or `cudaq` in addition to Qiskit. Select via backend name; each backend is opt-in and imported lazily.
- **Real GPU gate simulation** — CuPy-backed path for `cuquantum`/`cudaq` backends; QuTiP 5.x compatibility shims so `qutip` backend works with the current release line.
- **Multi-controlled gates end-to-end** — `CCX`, `CCZ`, `MCX`, `MCZ` supported in parser, verifier, and compilers (Qiskit + QASM). Includes CSWAP tests and an explicit arity error for malformed multi-control calls.
- **Classical context updates** — context fields can now be mutated from action effects (grammar, verifier, compiler). See the `add-classical-context-updates` spec for the full surface.
- **Iterative runtime for context updates** — `simulate_machine` now dispatches to `q_orca.runtime.iterative.simulate_iterative` whenever a machine declares any action with a `context_update` effect. The walker runs per-segment Qiskit circuits rebuilt at the live context, applies mutations between segments, threads `seed_simulator + iteration_index` for reproducibility, and enforces an `iteration_ceiling` safety net. Returns `QIterativeSimulationResult` with a per-transition trace and aggregated measurement counts. Driven end-to-end by `examples/predictive-coder-learning.q.orca.md`. Non-context-update machines keep the existing flat-circuit path with byte-identical output. See the `run-context-updates` spec for the full surface.
- **Verifier warning `UNBOUNDED_CONTEXT_LOOP`** — at warning severity when an iterative machine has no `int`-field bounding guard on any path to `[final]`; surfaced by the existing classical-context stage and suppressed by `VerifyOptions.skip_classical_context`.
- **Context-field angle references in rotation gates** — `Rx(qs[0], ctx.theta)` and related forms are resolved at compile time instead of requiring a literal.
- **Quantum-path detection via action effects** — `check_superposition_leaks` and friends now identify preparation paths by effect content, not just event naming conventions, reducing false positives on custom event names.
- **CI infrastructure** — scheduled nightly job and automated PR-review job; prompts are now repo-canonical.

### Fixed

- QASM qubit count inference now scans both gate targets and controls, fixing undercount on circuits that only use a qubit as a control.
- Grover CI flake resolved by seeding the shots simulator.
- Two CUDA-Q backend bugs (severity/`valid` field inconsistency, missing regression coverage on `CCX`/`CCZ`/`MCX`/`MCZ` emit paths).
- Five Hermes-flagged bugs from prior QA reports (see #6).

### Changed

- Internal parser helper `_has_trailing_mutation` renamed to `_contains_mutation_segment` for accuracy — it matches anywhere in the segment, not just the trailing position.
- `docs/specs/` reframed as `docs/research/` drafts; execution-backends feature spec promoted into the drafts tree.

---

## 0.4.0 (2026-04-14)

### Added

- **Mid-circuit measurement and classical feedforward** — measure a qubit mid-circuit and condition subsequent gates on the result. New syntax in action effects: `measure(qs[N]) -> bits[M]` and `if bits[M] == val: Gate(qs[K])`. Classical bits declared as `list<bit>` in `## context`.
- **Qiskit dynamic circuits** — mid-circuit measurements compile to `qc.measure(N, M)` and feedforward gates to `with qc.if_test((qc.clbits[M], val)):` using IBM's Dynamic Circuits API.
- **OpenQASM 3.0 feedforward** — conditional gates emit as `if (c[M]) { gate; }` (bare-bit per-bit syntax), verified to parse cleanly via `qiskit.qasm3.loads`.
- **New verifier checks**: `check_mid_circuit_coherence` (error if a unitary gate is applied to a qubit already measured mid-circuit without a reset) and `check_feedforward_completeness` (warning if a measurement result is never consumed by a conditional gate). Activated by `mid_circuit_coherence` and `feedforward_completeness` rules in `## verification rules`.
- **Two-qubit parameterized gates** — `CRx(qs[N], qs[M], theta)`, `CRy`, `CRz` (controlled rotation) and `RXX(qs[N], qs[M], theta)`, `RYY`, `RZZ` (symmetric interaction) supported end-to-end in the parser, Qiskit compiler, QASM compiler, and verifier. RZZ/RXX/RYY decompose to native gates in QASM (`cx; rz; cx` etc.).
- **New examples**: `examples/active-teleportation.q.orca.md` (3-qubit deterministic teleportation with X/Z feedforward), `examples/bit-flip-syndrome.q.orca.md` (5-qubit bit-flip error syndrome extraction), `examples/qaoa-maxcut.q.orca.md` (QAOA MaxCut with RZZ gates), `examples/bell-entangler.q.orca.md` (Bell pair with full pipeline coverage).
- `CONTRIBUTING.md` — setup instructions, good first issues, and research directions.

### Fixed

- QASM conditional syntax corrected from whole-register OpenQASM 2 form (`if(c==val)`) to per-bit OpenQASM 3.0 form (`if (c[M]) { gate; }`). The integer comparison `c[M] == 1` was also rejected by Qiskit's QASM 3.0 importer; the bare-bit form is accepted by all tested simulators.
- `check_superposition_leaks` no longer fires `SUPERPOSITION_LEAK` for transitions whose action is a mid-circuit measurement — these are coherent operations, not decoherence events.
- `check_mid_circuit_coherence` BFS now continues through mid-circuit measurement transitions rather than halting, enabling correct reuse detection across the full circuit.
- Two-qubit parameterized gate parsing no longer silently falls through to `theta=0.0` on unrecognized angle strings — an explicit parse error is now emitted.
- QAOA example updated to include all three triangle edges (`RZZ(qs[0], qs[2], pi/4)` was missing).

### Changed

- `QuantumCircuit(n)` → `QuantumCircuit(n, n_bits)` in Qiskit output when the machine declares classical bits.
- `KNOWN_UNITARY_GATES` extended with `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ`.

---

## 0.3.3 (unreleased — rolled into 0.4.0)

### Changed (noise models)

- **Breaking**: `thermal(T1, T2)` now takes relaxation times in nanoseconds
  and emits `noise.thermal_relaxation_error(T1, T2, 50)` (50 ns gate time).
  Previously `thermal(p, q)` silently fell back to `depolarizing_error(p, 1)`.
  Update any context fields using `thermal(...)` accordingly.
- `thermal` noise is applied to single-qubit gates only (`h, x, y, z, rx, ry,
  rz, t, s`); two-qubit gates are excluded because `thermal_relaxation_error`
  returns a single-qubit channel.
- `thermal(T1)` with one parameter defaults T2 = T1 (physical upper bound).
- `NoiseModel.parameter2` default changed from `0.01` to `0.0` (sentinel
  meaning "T2 defaults to T1").



### Added

- **Parameterized single-qubit rotation gates** (`Rx`, `Ry`, `Rz`) are now
  fully supported end-to-end: the markdown parser, Qiskit compiler, QASM
  compiler, and dynamic verifier all recognize the canonical qubit-first syntax
  `Rx(qs[N], <angle>)`.
- Symbolic angle grammar: decimal literals, `pi`, `pi/<int>`, `<int>*pi`, and
  `<int>*pi/<int>` (with optional leading minus) are evaluated to a Python
  `float` at parse time via the new `q_orca.angle.evaluate_angle` helper.
- Parse errors are now surfaced in `QParseResult.errors` for malformed rotation
  gate effects (unrecognized angle expression or wrong argument order).
- New example: `examples/vqe-rotation.q.orca.md` — a single-qubit variational
  example rotating `|0>` by `π/4` with a measurement.

### Changed

- **Breaking**: the canonical rotation-gate argument order is now **qubit-first,
  angle-second**: `Rx(qs[0], pi/4)`. The Qiskit compiler previously accepted the
  reverse order (`Rx(1.5708, qs[0])`); that form now produces a parse error.
  Machines written against the old Qiskit-compiler argument order must be
  updated. The QASM and dynamic-verifier parsers already used the canonical order
  and are unaffected.
- `QParseResult` now has an `errors: list[str]` field (default empty list).

### Fixed

- Rotation-gate effects no longer silently fall through to `parameter=0.0` when
  the angle string is symbolic or unrecognized. An explicit error is now emitted.
