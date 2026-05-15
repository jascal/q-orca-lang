# Changelog

## Unreleased

### Added

- **MPS concept-Gram transfer-matrix contraction** (`mps-transfer-matrix-contraction`) — `compute_concept_gram_mps` gained a `method` parameter (`"statevector" | "contracted" | "auto"`, default `"auto"`). The new `"contracted"` path builds per-site MPS tensors of shape `(χ_L, 2, χ_R)` at `χ ≤ 2` from the parsed staircase ops and contracts pairs via a left-to-right transfer-matrix sweep at cost `O(n · χ⁶)` per overlap, with memory constant in `n` at fixed `χ`. `"auto"` dispatches to `"statevector"` when `n_qubits < STATEVECTOR_NQUBIT_THRESHOLD` (currently 20) and to `"contracted"` otherwise, so all shipped examples keep the prior statevector behaviour. The two paths are pinned to within 1e-12 absolute tolerance on every `n_qubits ∈ {3, 4, 5, 6}` shipped example. The companion `compute_concept_gram_hea` path does NOT yet have a transfer-matrix contraction equivalent; HEA contraction is a forward-looking follow-on if a consumer asks for it.

### Tests

- New `tests/test_concept_gram_mps_contraction.py` covers the contracted primitives in isolation (single-Ry / single-Rz / single-CNOT tensor builds, hand-derived overlap pairs), pins `"statevector"` against the pre-change Python `np.vdot` double-loop bit-for-bit, asserts contracted = statevector at `n ∈ {3, 4, 5, 6}` on synthetic + shipped machines (cross-coupled and Rz-knob variants), and checks the contracted path produces Hermitian, unit-modulus-diagonal, finite Grams at `n ∈ {10, 16, 20, 24}` over 100 random seeds.

---

## 0.9.1 (2026-05-07)

### Fixed

- **Bit-flip syndrome physics bug** ([PR #62](../../pull/62), `extend-conditional-gate-compound-bits`) — corrected an incorrect bit-flip syndrome encoding in compound conditional-gate handling.
- **Inverse-form `Ry(qs[k], -(a + b))` parses end-to-end** ([PR #59](../../pull/59), `tech-debt-backlog` §5.9) — parser previously rejected the negated-sum angle expression in inverse-form effects.
- **`verify_skill` silent-pass gate** ([PR #61](../../pull/61), `tech-debt-backlog` §5.3) — closed a path where `verify_skill` could silently report success without exercising its checks.
- **`concept_gram_mps` polish** ([PR #58](../../pull/58), `tech-debt-backlog` §3.11, §5.2, §5.10–§5.13, §5.15) — assorted correctness and ergonomics fixes in the rung-1 MPS Gram path.

### Changed

- **`_infer_qubit_count` promoted to shared util** ([PR #60](../../pull/60), `tech-debt-backlog` §3.13) — moved to `q_orca/compiler/util.py` as the public `infer_qubit_count`. Analysis modules (`concept_gram_mps`, `concept_gram_hea`) now import the public name instead of reaching into `q_orca.compiler.qasm`'s underscored surface; `qasm.py` keeps an internal alias so existing parity tests stay green.

### Tests

- **Test coverage for shipped examples** ([PR #63](../../pull/63), `tech-debt-backlog` §5.4) — added 71 tests across `active-teleportation`, `qaoa-maxcut`, `predictive-coder-minimal`, `predictive-coder-learning`, and `larql-gate-knn-grover` covering parse / verify / compile / behaviour where the semantics admit a clean assertion (e.g. round-trip teleportation recovery, QAOA Z₂-symmetry, predictive-coder ancilla = q0 XOR q1 truth table).

---

## 0.9.0 (2026-05-03)

### Added

- **HEA tier-ordering invariant** (`add-hea-tier-ordering-invariant`) — declarative grammar lets HEA-encoded machines pin their concept-Gram tier separation as a verifier-checked bound. The `## theta` block accepts an optional 3rd `cluster` column carrying a tier label per concept; rows without a cluster column default to `_default`. The `## invariants` block accepts a new `concept_gram_tier_separation <op> <decimal in [0, 1]>` form (operators `>=`, `>`, `<=`, `<`, `==`/`=`). New helper `q_orca.compute_tier_separation(gram, clusters)` returns `min_intra_cluster_mean − max_cross_cluster_overlap` (or `None` when every cluster is a singleton). Stage 4b verifier now evaluates the declared inequality against the analytic Gram of HEA-encoded machines and surfaces `HEA_TIER_INVARIANT_VIOLATED` (with cluster-pair attribution), `HEA_TIER_UNDEFINED` (all-singleton), or `HEA_TIER_INVARIANT_NOT_APPLICABLE` (warning, on non-HEA machines). The whole evaluation is gated by `VerifyOptions.skip_dynamic` like the rest of Stage 4b. The `HEA_TIER_TOLERANCE = 0.025` constant is preserved as the recommended default; the verifier reads the value the machine declares.

### Changed

- `examples/larql-hea-minimal.q.orca.md` updated to declare `cluster` labels (`a, b → s1`, `c → s2`) and a `## invariants - concept_gram_tier_separation >= 0.025` bound, exercising the new grammar end-to-end.
- Backwards-compatible: HEA machines that do not declare a tier-separation invariant retain prior Stage 4b behavior (consistency check only). Machines without any `## encoding` section are unaffected.

---

## 0.8.0 (2026-05-02)

### Added

- **Rung-2 HEA concept encoding** (`add-rung2-hea-encoding`) — new explicit grammar for hardware-efficient ansatz machines. Two new sections, `## encoding` and `## theta`, declare the ansatz shape (`kind: hea`, `depth`, `entangler ∈ {ring, chain}`, `rotations` ⊆ `{Rx, Ry, Rz}`) and the per-concept parameter tensor of shape `(|rotations|, depth, n)`. New compiler helper `q_orca.compute_concept_gram_hea(machine, concept_action_label="query_concept")` builds each concept state by applying the declared rotation layers + entangler block in order and returns the analytic N×N overlap matrix. Verifier Stage 4b now invokes the helper for HEA machines and surfaces any `HeaGramConfigurationError` as a `HEA_GRAM_INVALID` error (shape mismatch, call-site / theta-row count mismatch, missing or wrong-kind encoding). Tier-ordering enforcement is *not* part of this change — the spike-validated constant `HEA_TIER_TOLERANCE = 0.025` is exposed from `q_orca.verifier.hea_encoding` for downstream use, but the matching invariant grammar is deferred to a follow-up proposal.
- **New example `examples/larql-hea-minimal.q.orca.md`** — 3-qubit depth-3 ring-entangler ansatz with rotations `(Ry, Rz)` and three concepts (`a`, `b`, `c`); `a–b` share a sub-cluster (overlap ≈ 0.9999) and `c` is the cross-cluster outsider (≈ 0.38), giving a sub→cross gap of ~0.6162 — well above `HEA_TIER_TOLERANCE`. Pipeline test in `tests/test_examples.py::TestExamples::test_larql_hea_minimal_pipeline` covers parse → AST surface (encoding/theta) → verify → analytic Gram tier separation.

### Changed

- Backwards-compatible: machines without an `## encoding` section preserve all rung-0 / rung-1 dispatch behavior. `compute_concept_gram_hea` is opt-in and only invoked when `machine.encoding.kind == "hea"`.

---

## 0.7.1 (2026-05-02)

### Added

- **Safe `Rz` phase knobs in rung-1 MPS** ([PR #51](../../pull/51)) — `compute_concept_gram_mps` now accepts optional `Rz(qs[i], <expr>)` rotations anywhere in the rung-1 staircase as 1-qubit interference knobs that preserve χ=2 (Schmidt rank unchanged). The matcher relaxes its signature check from "exactly `n_qubits` angle params" to "≥ 1 angle params, all type `angle`", letting machines declare a separate `phi` knob alongside `(α, β, γ)`. New example `examples/larql-animals-interference.q.orca.md` walks 4 concepts with `α = γ = 0`, `β ∈ {-0.5, +0.5}`, `φ ∈ {0, π/2}` and reproduces a strictly-ordered three-tier off-diagonal Gram (0.8851 / 0.6816 / 0.5931) where the φ-matched cross-cluster value coincides with the rung-1 product-state cosine.
- **Companion example `examples/larql-animals-hierarchy.q.orca.md`** — 4-concept γ-axis sibling distinction (real-rotation knob), included as the no-phase counterpart to the interference example.

### Fixed

- **Inverse-form `Rz` symmetry-break guardrail** — `compute_concept_gram_mps` previously accepted inverse-form (`U_prep^†`) effects with non-trivial `Rz` and silently returned an unphysical "all-1.0" Gram on the φ-only axis (because `|0⟩` is a fixed point of `Rz`). The matcher now raises `MpsGramConfigurationError(kind="rz_in_inverse_form")` with a message pointing the user to the preparation form and to `larql-animals-interference.q.orca.md`. The deeper symbolic-inversion fix remains tracked in `tech-debt-backlog/tasks.md` §5.16.

---

## 0.7.0 (2026-05-01)

### Added

- **Parametric actions** — action signatures now accept typed positional parameters (`int` for `qs[...]` subscripts and `angle` for rotation-gate angles) after the leading qubit-list parameter. Call sites in the transitions table supply literal arguments; the compiler substitutes them into a fresh copy of the effect string per site. One `query_concept | (qs, c: int) -> qs | Hadamard(qs[c])` row replaces N copy-pasted actions. Parameters are compile-time constants — out-of-range subscripts and unbound identifiers raise structured parse-time errors that name the offending transition. Zero-parameter signatures (`(qs) -> qs`, `(ctx) -> ctx`) parse unchanged, so every existing example is additive-compatible.
- **New example `examples/larql-polysemantic-12.q.orca.md`** — 12-qubit concept register, 12 non-orthogonal concept vectors (pairwise overlap 1/2), one parametric `query_concept(c: int)` action stamping 12 call sites from one template. Documents the analytic polysemy / cross-talk table in the leading paragraph.
- **New demo `demos/larql_polysemantic_12/demo.py`** — runs 12 independent single-query Qiskit simulations at 1024 shots each and recovers the analytic polysemy scores (≈ 75% on in-feature concepts, ≈ 33.3% cross-talk floor on out-of-feature) within Monte-Carlo tolerance.
- **Resource estimation** — new `## resources` section declares which static cost numbers the compiler should report (`gate_count`, `depth`, `cx_count`, `t_count`, `logical_qubits`); `## invariants` accepts the same five identifiers as bound LHS so a budget overrun becomes a verifier error (`RESOURCE_BOUND_EXCEEDED`) before any hardware run. Two new compiler entry points — `q_orca.estimate_resources(machine)` and `q_orca.compile_with_resources(machine)` — share one transpile pass per machine via `id(machine)` memoization. Verifier stage 4c (`resource_bounds`) is gated on the presence of resource invariants and can be skipped via `--skip-resource-bounds` or `VerifyOptions(skip_resource_bounds=True)`. Examples `bell-entangler`, `qaoa-maxcut`, and `vqe-heisenberg` pin their gate budgets. See `docs/language/resources.md`.
- **Structured-overlap polysemantic example, demo, and Gram helper** — companion to `larql-polysemantic-12` that swaps the flat Hadamard dictionary for a *clustered* concept geometry on a compact 3-qubit register. `examples/larql-polysemantic-clusters.q.orca.md` encodes 12 concepts in 3 clusters of 4 (capitals, fruits, vehicles) via a multi-angle parametric `prepare_concept(a, b, c)` + `query_concept(a, b, c)` pair (intra-cluster overlap 0.72 uniform, inter-cluster < 0.10 — a block-structured Gram matrix). `demos/larql_polysemantic_clusters/demo.py` prints an ASCII Gram heatmap and recovers the three-tier polysemy column `1.0 / 0.72 / ≲ 0.09` empirically. New optional helper `q_orca.compute_concept_gram(machine, concept_action_label="query_concept")` returns the analytic N×N overlap matrix for any machine that follows the product-state preparation convention; raises `ConceptGramConfigurationError` when the convention is violated.
- **Hierarchical (MPS bond-2) polysemantic example, demo, and Gram helper** — rung-1 sibling of `larql-polysemantic-clusters` that lifts the 12-concept dictionary from product states to **bond-dimension-2 matrix product states** via a cross-coupled CNOT-staircase preparation `Ry(q0, a); CNOT(q0, q1); Ry(q1, a + b); CNOT(q1, q2); Ry(q2, b + c)` (linear-combination angles cross-couple adjacent qubits, producing a Gram that does not factorize as `|⟨φᵢ|φⱼ⟩|² = ∏ₖ |⟨φᵢᵏ|φⱼᵏ⟩|²`). `examples/larql-polysemantic-hierarchical.q.orca.md` organizes 12 concepts as a two-level hierarchy (3 super-groups × 2 sub-clusters × 2 concepts) on the same 3-qubit register and produces a four-tier Gram matrix — self 1.000 / sub-cluster-mate 0.882 / super-group-sibling {0.335, 0.593, 0.753} / cross-group [0.000, 0.178] — one tier richer than rung 0. `demos/larql_polysemantic_hierarchical/demo.py` prints a 4-tier ASCII Gram heatmap, recovers the polysemy column from 12 Qiskit circuits, and prints a side-by-side rung-0 vs rung-1 comparison. New optional helper `q_orca.compute_concept_gram_mps(machine, concept_action_label="query_concept", bond_dim=2)` enumerates the parametric call sites of a CNOT-staircase action (single-bound-param **or** linear-combination angles), builds each concept statevector, and returns the analytic N×N overlap matrix; raises `MpsGramConfigurationError` (missing action, wrong signature, non-staircase effect, unrecognized angle expression, no call sites, or `bond_dim != 2`).

### Changed

- Backwards-compatible: no behavior change for existing machines. Both halves of `extend-gate-set-and-parametric-actions` (multi-controlled gates, parametric actions) are additive.
- **Generalized angle parser** — `q_orca/angle.py::evaluate_angle` now accepts top-level linear combinations (`a + b`, `2*pi + gamma`, `-a - b`) in addition to the prior literal / single-identifier shapes. The Ry-segment matcher in `concept_gram_mps.py` parses the angle as a linear combination via `ast.parse` and substitutes call-site argument values per coefficient/parameter pair. The single-bound-param shape remains a degenerate one-term linear combination, so all archived examples parse unchanged.

### Fixed

- **MPS encoding factorization bug** (`fix-mps-encoding-non-factorizing`, [PR #48](../../pull/48)) — the original rung-1 staircase preparation `Ry(q0,α); CNOT(q0,q1); Ry(q1,β); CNOT(q1,q2); Ry(q2,γ)` was advertised as producing non-factorized concept overlap "by virtue of being entangled". This is mathematically false: while the staircase output has Schmidt rank > 1, its same-angle Gram matrix factorizes exactly as the product-state Gram (`|⟨φᵢ|φⱼ⟩|² = ∏ₖ cos²((θᵢᵏ − θⱼᵏ)/2)`), giving only 3 visible tiers, not 4. Replaced with the cross-coupled-by-sum encoding above, where the Ry on each non-leading qubit takes a linear combination of *two* bound parameters; this breaks the per-qubit factorization and yields the four-tier hierarchy the example claims. Adds new error kind `MpsGramConfigurationError("unrecognized_angle_expression")` for non-linear angle expressions in the Ry-segment matcher; appends post-mortem entry to `add-mps-concept-encoding/design.md`; cross-links new tech-debt §5.7 (verifier blind spot — Gram factorization vs. encoding entanglement) for a future verifier rule that would catch this class of bug at verify time.

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
