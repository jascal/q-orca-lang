## Why

VQE/QAOA machines have no machine-readable definition of *what observable they
measure*. `examples/vqe-heisenberg.q.orca.md` carries its `⟨XX+YY+ZZ⟩/4`
Hamiltonian in three places the parser can't cross-check — a prose state
description, an empty-effect `set_energy` action, and a `ctx.energy` guard with
no binding to a measurement. Practitioners must inline basis-rotation gates into
an action (conflating ansatz with observable) or drop out to Python. A
declarative `## hamiltonian` section makes the observable a first-class,
verifier-checked part of the file, separate from how the ansatz is prepared.

## What Changes

- Add a `## hamiltonian <name>` section (between `## context` and `## actions`)
  holding an ID-typed table of Pauli terms: `| Coefficient | Pauli string |
  Qubits |`. A machine may declare several (e.g. QAOA's `H_C` and `H_M`).
- Coefficients are real literals or symbolic angle expressions (resolved via the
  existing `evaluate_angle`); they MUST evaluate real. Pauli strings use
  `{I, X, Y, Z}` and their length MUST equal the `Qubits` list length.
- Add a `measure(H_name) -> ctx.field` effect form: the runtime decomposes the
  named Hamiltonian into qubit-wise-commuting groups (Peruzzo et al. 2014),
  emits one shot-batched measurement circuit per group, and aggregates the
  per-term expectations into a single `float` written to the context field.
- Verifier: `HAMILTONIAN_NON_HERMITIAN` (complex coefficient) and
  `HAMILTONIAN_PAULI_OUT_OF_RANGE` (string/qubit-list length mismatch or
  out-of-register index).
- Compiler: a qubit-wise commutativity grouper + per-group basis-rotation
  measurement circuits for the Qiskit and QASM backends.
- CLI: `q-orca run --report-hamiltonians` prints, per declared Hamiltonian, the
  estimated expectation, the per-Pauli-group breakdown, and shots per group.
- Refactor `examples/vqe-heisenberg.q.orca.md` (and `qaoa-maxcut.q.orca.md`) to
  declare `## hamiltonian` instead of in-action energy logic.

## Capabilities

### New Capabilities
<!-- none — extends language, verifier, compiler, runtime -->

### Modified Capabilities
- `language`: add the `## hamiltonian <name>` section and the
  `measure(H_name) -> ctx.field` effect form.
- `verifier`: add Hermiticity (real-coefficient) and Pauli/qubit-index validity
  checks.
- `compiler`: add qubit-wise-commuting measurement grouping and per-group
  measurement-circuit emission (Qiskit + QASM).
- `runtime`: add Hamiltonian expectation aggregation in the shot-batched leaf
  path, plus the `--report-hamiltonians` diagnostic surface.

## Impact

- New code: `q_orca/compiler/measurement_grouping.py`; AST `HamiltonianTerm` /
  `HamiltonianDecl` + `QMachineDef.hamiltonians`; parser `_parse_hamiltonian_block`;
  verifier checks + 2 error codes; Qiskit/QASM measurement-circuit builders;
  `effect_parser` `measure(H)` form; runtime `_run_hamiltonian_measurement`.
- Edited examples: `vqe-heisenberg`, `qaoa-maxcut`. New docs:
  `docs/language/hamiltonian.md`.
- Backward compatible: machines without a `## hamiltonian` section are
  unchanged; the new effect form is additive.
- **Dependencies**: `add-composed-runtime` (merged) — `measure(H)` runs in
  `run_composed`'s shot-batched leaf path. Nested support composes with
  `extend-nested-shot-aggregation` (merged); ships leaf-first regardless.
