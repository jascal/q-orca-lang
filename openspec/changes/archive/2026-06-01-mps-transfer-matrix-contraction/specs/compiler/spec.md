## MODIFIED Requirements

### Requirement: compute_concept_gram_mps accepts a method parameter

`q_orca.compiler.concept_gram_mps.compute_concept_gram_mps` SHALL accept a new keyword argument `method: Literal["statevector", "contracted", "auto"] = "auto"`.

When `method="statevector"`, the function SHALL use the existing explicit-2ⁿ-statevector implementation. The result SHALL be bit-identical to the pre-change implementation on every input.

When `method="contracted"`, the function SHALL use the O(n · χ⁶) transfer-matrix contraction implementation. For every input on which both modes can run (e.g., n_qubits small enough that statevector doesn't OOM), the contracted result SHALL equal the statevector result to 1e-12 absolute tolerance.

When `method="auto"` (the default), the function SHALL dispatch to `"statevector"` when `n_qubits < STATEVECTOR_NQUBIT_THRESHOLD` and to `"contracted"` otherwise.

`STATEVECTOR_NQUBIT_THRESHOLD` SHALL be a module-level constant exposed for tuning, with initial value 20.

#### Scenario: method="statevector" preserves pre-change behaviour

- **WHEN** `compute_concept_gram_mps(machine, method="statevector")` is called on any shipped MPS example
- **THEN** the result is bit-identical to the result produced by the pre-change implementation on the same machine

#### Scenario: contracted equals statevector at small n

- **WHEN** `compute_concept_gram_mps(machine, method="contracted")` is called on a machine with `n_qubits ∈ {3, 4, 5, 6}`
- **THEN** the result equals `compute_concept_gram_mps(machine, method="statevector")` on the same machine to 1e-12 absolute tolerance

#### Scenario: auto dispatches to statevector below threshold

- **WHEN** `compute_concept_gram_mps(machine, method="auto")` is called with `n_qubits=3`
- **THEN** the function takes the statevector code path

#### Scenario: auto dispatches to contracted at threshold

- **WHEN** `compute_concept_gram_mps(machine, method="auto")` is called with `n_qubits=20`
- **THEN** the function takes the contracted code path

#### Scenario: unknown method value raises

- **WHEN** `compute_concept_gram_mps(machine, method="invalid")` is called
- **THEN** a `ValueError` is raised whose message contains the invalid value and the supported set `{"statevector", "contracted", "auto"}`

### Requirement: contracted path is constant in memory across n_qubits

The contracted-path implementation SHALL allocate intermediate state of size O(n · χ²) per MPS feature (not O(2ⁿ)). At χ=2 this is O(n) complex numbers per feature, regardless of how large `n_qubits` grows.

This requirement is testable by running the contracted path at large synthetic `n_qubits` (e.g., 24, 28) on a machine with N=2 call sites and confirming no out-of-memory error. Compare against the statevector path at the same n which OOMs at 28.

#### Scenario: contracted path runs at n_qubits=28 on a small synthetic machine

- **WHEN** a synthetic 28-qubit machine with N=2 call sites is built and `compute_concept_gram_mps(machine, method="contracted")` is invoked
- **THEN** the function returns a finite `(2, 2)` complex Gram without raising MemoryError

### Requirement: contracted Gram preserves Hermitian + unit-modulus-diagonal invariants

For any valid input, the contracted Gram `G` SHALL satisfy:

- Hermitian: `G[i, j] == G[j, i].conjugate()` to 1e-12 absolute tolerance for every (i, j).
- Unit-modulus diagonal: `abs(G[i, i]) == 1.0` to 1e-12 absolute tolerance for every `i` (the state vectors are normalised).
- Finite: no NaN or Inf entries.

#### Scenario: Hermitian invariant holds at n_qubits=16

- **WHEN** a synthetic 16-qubit machine with 8 random-seed call sites is built and run through `method="contracted"`
- **THEN** the resulting Gram satisfies `np.allclose(G, G.conj().T, atol=1e-12)` and `np.allclose(np.abs(np.diag(G)), 1.0, atol=1e-12)`

### Requirement: bond_dim != 2 continues to raise (no change)

The existing `bond_dim != 2` guard in `compute_concept_gram_mps` is preserved unchanged. The contracted path SHALL also enforce `bond_dim == 2` and SHALL raise the same `MpsGramConfigurationError` for any other value.

The χ>2 generalisation (multi-CNOT KAK + multi-rank transfer matrices) is explicitly out of scope for this change; the error message remains identical.

#### Scenario: bond_dim=4 raises on the contracted path

- **WHEN** `compute_concept_gram_mps(machine, method="contracted", bond_dim=4)` is called
- **THEN** the same `MpsGramConfigurationError` is raised as in the pre-change implementation, with a message naming `bond_dim=4` and pointing at the single-CNOT-per-step staircase constraint
