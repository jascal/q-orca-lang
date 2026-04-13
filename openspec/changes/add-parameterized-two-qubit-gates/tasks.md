## 1. AST

- [ ] 1.1 Extend `GateKind` comment in `q_orca/ast.py` to document the six
      new kinds: `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ`

## 2. Parser

- [ ] 2.1 Add a regex branch in `_parse_gate_from_effect`
      (`q_orca/parser/markdown_parser.py`) for
      `Gate(qs[i], qs[j], <angle>)` — captures gate name, two qubit
      indices, and angle string; passes angle through `evaluate_angle`;
      emits `QuantumGate(kind=..., targets=[j], controls=[i], parameter=...)`
      for controlled forms and `targets=[i,j]` for symmetric forms

## 3. Qiskit compiler

- [ ] 3.1 Add six dispatch branches in `_gate_to_qasm`
      (`q_orca/compiler/qiskit.py`):
      `CRx` → `qc.crx(angle, ctrl, tgt)`,
      `CRy` → `qc.cry(...)`,
      `CRz` → `qc.crz(...)`,
      `RXX` → `qc.rxx(angle, q0, q1)`,
      `RYY` → `qc.ryy(...)`,
      `RZZ` → `qc.rzz(...)`

## 4. QASM compiler

- [ ] 4.1 Add six dispatch branches in `_gate_to_qasm`
      (`q_orca/compiler/qasm.py`):
      `CRx/CRy/CRz` → direct `crx(θ) q[c], q[t];` etc.
      `RZZ` → `cx q[i],q[j]; rz(θ) q[j]; cx q[i],q[j];`
      `RXX` → H-conjugated RZZ decomposition
      `RYY` → Rx(π/2)-conjugated RZZ decomposition

## 5. Verifier

- [ ] 5.1 Add `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ` to the known
      unitary gate set in `q_orca/verifier/quantum.py`

## 6. Example and tests

- [ ] 6.1 Add `examples/qaoa-maxcut.q.orca.md` — 3-qubit QAOA MaxCut
      on a triangle graph using `RZZ` cost layer and `Rx` mixer
- [ ] 6.2 Create `tests/test_two_qubit_parameterized.py` covering:
      parser round-trip for all six gate kinds, Qiskit emission
      (`qc.rzz`, `qc.crz` etc.), QASM emission, and verifier acceptance
- [ ] 6.3 Run `pytest tests/test_two_qubit_parameterized.py` and confirm
      all tests pass; run full `pytest` suite and confirm no regressions
