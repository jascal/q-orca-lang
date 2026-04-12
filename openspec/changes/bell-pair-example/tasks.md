## 1. Fix bell-entangler example

- [x] 1.1 Add `[initial]` annotation to the `|00>` state heading in
      `examples/bell-entangler.q.orca.md`
- [x] 1.2 Replace the two `fidelity(...)` guards with `prob('00') ≈ 0.5`
      and `prob('11') ≈ 0.5` in the `## guards` section
- [x] 1.3 Run `q-orca verify --strict examples/bell-entangler.q.orca.md`
      and confirm it passes (iterate on the example if the superposition-leak
      or completeness check fires)

## 2. Update AST snapshot

- [x] 2.1 Run `pytest tests/test_examples.py::TestExamples::test_bell_entangler_ast_snapshot`
      and, if it fails due to guard-syntax changes, update the `expected` dict
      in `test_examples.py` to match the new parsed representation

## 3. Pipeline tests

- [x] 3.1 Create `tests/test_bell_pair_pipeline.py` with a `TestBellPairQASM`
      class: parse `bell-entangler.q.orca.md`, call `compile_to_qasm`, assert
      output contains `OPENQASM 3.0;`, `qubit[2] q;`, `h q[0];`, `cx q[0], q[1];`
- [x] 3.2 Add a `TestBellPairQiskit` class: call
      `compile_to_qiskit(machine, QSimulationOptions(analytic=True))`, assert
      output contains `QuantumCircuit(2)`, `qc.h(`, `qc.cx(0, 1)`, and
      `json.dumps`
- [x] 3.3 Add a `TestBellPairMermaid` class: call `compile_to_mermaid`, assert
      output starts with `stateDiagram-v2`, contains `direction LR`, has a
      `[*] -->` line, and contains a transition label with `apply_CNOT`
- [x] 3.4 Run `pytest tests/test_bell_pair_pipeline.py` and confirm all tests pass

## 4. Full suite check

- [x] 4.1 Run `pytest` and confirm no regressions
