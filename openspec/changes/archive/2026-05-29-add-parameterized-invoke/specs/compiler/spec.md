## ADDED Requirements

### Requirement: Composed-Machine Rendering and Backend Refusal

Each compiler backend SHALL have explicit behavior when given a
machine that contains invoke states: Mermaid SHALL render them;
QASM and Qiskit SHALL refuse and emit a structured error
directing the user to the composed-runtime follow-up. This
preserves diagramming and static analysis while preventing silent
compilation of a composition whose runtime semantics are not yet
specified.

- **Mermaid**: invoke states SHALL be rendered as a distinct node
  shape (rounded rectangle) labeled with the child machine name.
  The Mermaid diagram SHALL include a nested `state <ChildName>
  { ... }` block for each resolved child, so the composed diagram
  is self-contained.
- **QASM / Qiskit**: given a machine whose AST contains any
  invoke state, the compiler SHALL return a structured
  `COMPILE_COMPOSED_MACHINE` error whose message reads
  "cannot compile a machine with invoke states directly. Compile
  child machines individually and compose via the runtime
  (planned as `add-composed-runtime`)."

#### Scenario: Mermaid with invoke

- **WHEN** a parent machine has
  `## state |train> [invoke: QChild(theta=theta) shots=1024]` and
  `QChild` is a sibling machine in the same file
- **THEN** the Mermaid output shows `|train>` as a rounded
  rectangle labeled `invoke: QChild` and includes a nested
  `state QChild { ... }` block rendering QChild's own states and
  transitions

#### Scenario: QASM refuses composed machine

- **WHEN** `compile_to_qasm(parent_machine)` is called and
  `parent_machine` has any invoke state
- **THEN** the compiler returns a structured
  `COMPILE_COMPOSED_MACHINE` error rather than an incomplete QASM
  program

#### Scenario: Qiskit refuses composed machine

- **WHEN** `compile_to_qiskit(parent_machine, options)` is called
  and `parent_machine` has any invoke state
- **THEN** the compiler returns the same structured
  `COMPILE_COMPOSED_MACHINE` error as QASM — the Qiskit backend
  does not fall back to any partial compilation
