# Tasks: add-parameterized-two-qubit-gates

- [x] Extend `GateKind` comment in `q_orca/ast.py` to include `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ`
- [x] Extend `_parse_gate_from_effect` in `q_orca/parser/markdown_parser.py` — new regex branch for `Gate(qs[i], qs[j], angle)` two-qubit parameterized form
- [x] Extend `_parse_single_gate` in `q_orca/compiler/qiskit.py` — parse two-qubit parameterized effects
- [x] Extend `_gate_to_qiskit` in `q_orca/compiler/qiskit.py` — emit `qc.crz(...)`, `qc.rxx(...)`, etc.
- [x] Extend `_gate_to_qasm` in `q_orca/compiler/qasm.py` — emit direct QASM for `CRx/CRy/CRz` and decompositions for `RXX/RYY/RZZ`
- [x] Extend `KNOWN_UNITARY_GATES` in `q_orca/verifier/quantum.py`
- [x] Add `examples/qaoa-maxcut.q.orca.md`
- [x] Add `tests/test_two_qubit_parameterized.py`
