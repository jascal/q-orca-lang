## Why

The parameterized rotation gate system (`Rx`, `Ry`, `Rz`) shipped in v0.3.3 only covers single-qubit gates. Two-qubit parameterized gates (`CRz`, `CRx`, `CRy`, `RXX`, `RYY`, `RZZ`) are the essential building blocks of QAOA cost layers, Heisenberg VQE, and UCCSD ansätze — none of these algorithms can be expressed natively in q-orca today. The implementation is a direct, self-contained extension of the existing parameterized gate machinery.

## What Changes

- Add six new gate kinds to the AST: `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ`
- Extend the markdown parser's effect string tokenizer to parse `Gate(qs[i], qs[j], angle)` (two qubit args + angle)
- Extend Qiskit compiler to emit `qc.crz(...)`, `qc.rxx(...)`, etc.
- Extend QASM compiler to emit `crz(θ) q[i], q[j];` (or decomposition for `RXX/RYY/RZZ`)
- Extend verifier unitarity check to accept all six new gate kinds
- Add `examples/qaoa-maxcut.q.orca.md` — 3-qubit QAOA MaxCut example
- Add `tests/test_two_qubit_parameterized.py`

## Capabilities

### New Capabilities

*(none — extends existing compiler, parser, and verifier capabilities)*

### Modified Capabilities

- `compiler`: add QASM and Qiskit emission for six two-qubit parameterized gate kinds
- `language`: add `Gate(qs[i], qs[j], angle)` effect syntax and the six new gate kinds to the gate effect grammar

## Impact

- `q_orca/ast.py` — extend `GateKind` literal
- `q_orca/parser/markdown_parser.py` — new regex branch in `_parse_gate_from_effect`
- `q_orca/compiler/qiskit.py` — six new gate dispatch branches
- `q_orca/compiler/qasm.py` — six new gate dispatch branches (with QASM 2 decomposition for `RXX/RYY/RZZ`)
- `q_orca/verifier/` — extend unitarity rule
- New: `examples/qaoa-maxcut.q.orca.md`, `tests/test_two_qubit_parameterized.py`
