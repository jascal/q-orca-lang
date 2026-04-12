# Changelog

## 0.3.3 (unreleased)

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
