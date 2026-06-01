## 1. AST + parser

- [ ] 1.1 In `q_orca/ast.py`, add `HamiltonianTerm(coefficient, pauli, qubits)` and `HamiltonianDecl(name, terms)`; add `hamiltonians: list[HamiltonianDecl]` to `QMachineDef`
- [ ] 1.2 Parser `_parse_hamiltonian_block`: parse `## hamiltonian <name>` + the `| Coefficient | Pauli string | Qubits |` table; integrate into the section-dispatch loop; default name `H`
- [ ] 1.3 `effect_parser`: parse `measure(<H_name>) -> ctx.<field>` into a Hamiltonian-measurement effect
- [ ] 1.4 Backward-compat: a machine with no `## hamiltonian` section parses unchanged

## 2. Verifier

- [ ] 2.1 `_check_hamiltonian_hermitian`: every coefficient evaluates real (reuse `evaluate_angle`); else `HAMILTONIAN_NON_HERMITIAN` at the offending row
- [ ] 2.2 `_check_pauli_qubit_indices`: Pauli-string length == qubit-list length and indices in the declared register; else `HAMILTONIAN_PAULI_OUT_OF_RANGE`
- [ ] 2.3 Add the two error codes to `verifier/types.py`; wire the checks into the pipeline (fire only when a `## hamiltonian` section is present)

## 3. Compiler

- [ ] 3.1 New `q_orca/compiler/measurement_grouping.py`: deterministic qubit-wise commutativity grouping (Peruzzo et al.)
- [ ] 3.2 Qiskit `build_measurement_circuits_for(hamiltonian)`: one circuit per group with basis-rotation prefix (`H` for X, `Sdg; H` for Y, identity for Z) + terminal measure
- [ ] 3.3 QASM mirror: emit one measurement program per group

## 4. Runtime

- [ ] 4.1 `_run_hamiltonian_measurement` in `runtime/composed.py`: run each group's circuit shot-batched in the leaf path, estimate per-term ⟨P⟩, aggregate `Σ coeff·⟨P⟩` to the target context field
- [ ] 4.2 Track multiple named Hamiltonians independently
- [ ] 4.3 CLI `q-orca run --report-hamiltonians`: per-Hamiltonian expectation + per-group breakdown + shots/group

## 5. Examples + tests + docs

- [ ] 5.1 Refactor `examples/vqe-heisenberg.q.orca.md` to declare `## hamiltonian H`; add/refresh `examples/qaoa-maxcut.q.orca.md` with `## hamiltonian H_C` + `## hamiltonian H_M`
- [ ] 5.2 Tests: single-Pauli expectation (±1); commuting-group batching with Bell-state `⟨XX+YY+ZZ⟩ = 3`; `HAMILTONIAN_NON_HERMITIAN`; `HAMILTONIAN_PAULI_OUT_OF_RANGE` (length + index); multi-Hamiltonian QAOA; backward-compat
- [ ] 5.3 Docs: `docs/language/hamiltonian.md` (section grammar, Pauli convention, `measure(H)`, grouping, `--report-hamiltonians`); mark `docs/research/spec-hamiltonian-section.md` delivered
