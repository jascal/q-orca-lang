## MODIFIED Requirements

### Requirement: Three Backend Targets

The compiler SHALL expose three backend entry points:

- `compile_to_qasm(machine)` → OpenQASM 3.0 string
- `compile_to_qiskit(machine, options)` → Qiskit Python script string
- `compile_to_mermaid(machine)` → Mermaid `stateDiagram-v2` string

#### Scenario: Qiskit script with simulation options

- **WHEN** `compile_to_qiskit(machine, QSimulationOptions(analytic=True))`
  is called on a Bell-pair machine
- **THEN** the returned script contains `qc = QuantumCircuit(2)`, the
  necessary `qc.h(...)` and `qc.cx(...)` calls, and produces a
  probability dictionary on the final `print(json.dumps(result, ...))`

#### Scenario: CNOT translation across backends

- **WHEN** an action's effect is `CNOT(qs[0], qs[1])`
- **THEN** QASM emits `cx q[0], q[1];`, Qiskit emits `qc.cx(0, 1)`,
  and Mermaid renders the action as a transition label `... / apply_CNOT`

#### Scenario: Bell-pair QASM output structure

- **WHEN** `compile_to_qasm` is called on the Bell-pair machine
- **THEN** the output contains `OPENQASM 3.0;`, `qubit[2] q;`, `h q[0];`,
  and `cx q[0], q[1];` in that order

#### Scenario: Bell-pair Mermaid output structure

- **WHEN** `compile_to_mermaid` is called on the Bell-pair machine
- **THEN** the output begins with `stateDiagram-v2`, contains `direction LR`,
  has a `[*] -->` transition for the initial state, and includes at least one
  transition label containing `apply_CNOT`
