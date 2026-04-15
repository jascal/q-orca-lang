# Changelog

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
