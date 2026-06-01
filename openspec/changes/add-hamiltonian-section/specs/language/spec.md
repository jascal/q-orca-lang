## ADDED Requirements

### Requirement: Declarative Hamiltonian Section

The parser SHALL recognize one or more `## hamiltonian <name>` sections, placed between `## context` and `## actions`. Each section body is a table with columns `| Coefficient | Pauli string | Qubits |`, and each row contributes one weighted Pauli term to the named Hamiltonian. `<name>` defaults to `H` when omitted; a machine MAY declare several distinct names (e.g. `H_C` and `H_M`).

A `Coefficient` is a real numeric literal or a symbolic angle expression resolvable by the existing `evaluate_angle` helper. A `Pauli string` is a sequence over the alphabet `{I, X, Y, Z}`; its length MUST equal the length of the row's `Qubits` list, with `Pauli[i]` acting on `Qubits[i]`. The parser SHALL attach a `HamiltonianDecl(name, terms)` (each term a `HamiltonianTerm(coefficient, pauli, qubits)`) to `QMachineDef.hamiltonians`.

A machine with no `## hamiltonian` section parses exactly as before this change.

#### Scenario: Single Hamiltonian parses

- **WHEN** a machine declares `## hamiltonian H` with rows `1.0 | XX | [q0, q1]`, `1.0 | YY | [q0, q1]`, `1.0 | ZZ | [q0, q1]`
- **THEN** `QMachineDef.hamiltonians` contains one `HamiltonianDecl` named `H` with three terms, each with coefficient `1.0` and a two-qubit Pauli string

#### Scenario: Multiple named Hamiltonians parse

- **WHEN** a machine declares both `## hamiltonian H_C` and `## hamiltonian H_M`
- **THEN** `QMachineDef.hamiltonians` contains two decls named `H_C` and `H_M`, tracked independently

### Requirement: Hamiltonian Measurement Effect

The parser SHALL recognize a `measure(<H_name>) -> ctx.<field>` action effect form. It denotes that the action estimates `⟨H_name⟩` over the current state and writes the resulting scalar into the named context field.

#### Scenario: measure(H) effect parses

- **WHEN** an action's effect is `measure(H) -> ctx.energy`
- **THEN** the action is recorded as a Hamiltonian-measurement effect targeting Hamiltonian `H` and context field `energy`
