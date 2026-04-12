# Changelog

## 0.3.3 (unreleased)

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
