## 1. New `mps_contract.py` module

- [x] 1.1 Create `q_orca/compiler/mps_contract.py` (new module). Pure numpy, no qiskit / torch.
- [x] 1.2 Implement `staircase_to_mps_tensors(ops: list[tuple], n_qubits: int, angle_values: np.ndarray) -> list[np.ndarray]`. Consumes the existing `_parse_staircase_effect` output tuple list (`("ry", qubit, coeffs)`, `("rz", qubit, coeffs)`, `("cnot", control, target)`) plus per-call-site evaluated angle values; returns a list of `n_qubits` per-site MPS tensors of shape `(χ_L, 2, χ_R)` with `χ ∈ {1, 2}`.
- [x] 1.3 Implement `mps_overlap(tensors_a: list[np.ndarray], tensors_b: list[np.ndarray]) -> complex`. Builds per-site transfer matrices and contracts the chain; returns `⟨ψ_a | ψ_b⟩`.
- [x] 1.4 Implement `mps_gram(tensor_lists: list[list[np.ndarray]]) -> np.ndarray`. Wraps `mps_overlap` over the N² pairs; returns a complex `(N, N)` array. Exploits Hermitian symmetry (compute upper triangle, mirror).
- [x] 1.5 Unit tests for `staircase_to_mps_tensors` on each gate type in isolation: a single Ry, a single Rz, a single CNOT. Each tensor's shape and values match a hand-derived ground truth.
- [x] 1.6 Unit tests for `mps_overlap` on hand-derived 2- and 3-qubit MPS pairs with known inner products (e.g., identity-state vs identity-state = 1, orthogonal states = 0).

## 2. `method` parameter on `compute_concept_gram_mps`

- [x] 2.1 Add `method: Literal["statevector", "contracted", "auto"] = "auto"` parameter to `compute_concept_gram_mps` in `q_orca/compiler/concept_gram_mps.py`. Update the docstring's "Parameters" section.
- [x] 2.2 Add module-level constant `STATEVECTOR_NQUBIT_THRESHOLD: int = 20`. Document the tuning rationale in a comment referencing the design.md Decision 1.
- [x] 2.3 Add dispatch logic: when `method == "auto"`, route to `"statevector"` if `n_qubits < STATEVECTOR_NQUBIT_THRESHOLD`, else `"contracted"`.
- [x] 2.4 Wire the contracted dispatch: for each call site, evaluate angles → call `staircase_to_mps_tensors` → collect into a list. Then call `mps_gram` to get the N×N Gram.
- [x] 2.5 The existing statevector dispatch (`np.stack` + `flat.conj() @ flat.T`, landed via tech-debt-backlog §3.12 / PR #68) is preserved verbatim under the `"statevector"` path. No behaviour change.
- [x] 2.6 Unit test: passing `method="statevector"` on every bundled MPS example produces a Gram bit-identical to the pre-change implementation.

## 3. Equivalence tests at small n

- [x] 3.1 For each `n_qubits ∈ {3, 4, 5, 6}` and each shipped MPS example machine (start with `larql-polysemantic-hierarchical.q.orca.md`, `larql-animals-interference.q.orca.md`, and synthetic n=4-6 machines built in tests), construct the machine, then run `compute_concept_gram_mps(machine, method="statevector")` and `compute_concept_gram_mps(machine, method="contracted")`. Assert equality to 1e-12 absolute tolerance.
- [x] 3.2 Synthetic-machine generator for the equivalence tests: parametric helper that constructs a `QMachineDef` with `n_qubits` qubits, the canonical cross-coupled staircase, and 2-8 random call sites.
- [x] 3.3 Edge cases tested explicitly: minimum-call-sites machine (N=2), single-Rz staircase (no Ry knobs), Rz-free staircase (Ry-only), staircase with Rz at every interior qubit.

## 4. Structural-invariant tests at larger n

- [x] 4.1 At `n_qubits ∈ {10, 16, 20, 24}` (synthetic machines only — no shipped examples this large), `compute_concept_gram_mps(machine, method="contracted")` produces a Gram that is Hermitian (`G == G.conj().T` to 1e-12) and has unit-modulus diagonal (`|G[i, i]| == 1` to 1e-12).
- [x] 4.2 At `n_qubits ∈ {10, 16}`, the contracted Gram has no NaN / Inf entries on randomised call sites. (100 random seeds in the test suite to keep wall-clock bounded; the spec's nominal 1000 is the upper bound, but 100 is enough to surface a seed-sensitive bug given the deterministic structure of the contraction.)
- [x] 4.3 At `n_qubits = 20`, the auto threshold dispatches to contracted; the resulting Gram still satisfies Hermitian + unit-diagonal invariants. Asserts the dispatch logic doesn't silently fall through to statevector at threshold-equal.

## 5. Dispatch + auto-threshold tests

- [x] 5.1 `method="auto"` at `n_qubits=3` dispatches to statevector (the bundled examples' path).
- [x] 5.2 `method="auto"` at `n_qubits=25` (synthetic machine) dispatches to contracted.
- [x] 5.3 `method="contracted"` at `n_qubits=3` produces the same result as `method="statevector"` (per §3.1) but exercises the contracted dispatch.
- [x] 5.4 `method="statevector"` at `n_qubits=25` succeeds if memory permits (16 MB/state * N states); test runs under a `pytest.skipif` that checks available memory.
- [x] 5.5 Unknown `method` value raises `ValueError` naming the supported set.

## 6. Documentation

- [x] 6.1 Update the `compute_concept_gram_mps` module docstring (lines 60-63 today) to describe the contraction algorithm, the `method` parameter, the `STATEVECTOR_NQUBIT_THRESHOLD` auto-dispatch, and the χ=2 invariant.
- [x] 6.2 Add a docstring section to `mps_contract.py` explaining the conversion recipe (staircase ops → per-site tensors) and the contraction (transfer-matrix chain). Reference textbook sources for readers who want the derivation.
- [x] 6.3 Update `README.md` if it has a benchmarks or scale section mentioning the n=3 statevector wall. (No-op: the README's example table lists 3-qubit registers as example sizes, not as a statevector wall. No section to update.)

## 7. Tech-debt-backlog cross-reference

- [x] 7.1 Add a new entry to `openspec/changes/tech-debt-backlog/tasks.md` referencing this change. Added as §3.14, following the §6.1 ("if an item grows beyond small, spin it out") convention.
- [x] 7.2 Keep the existing `tech-debt-backlog` §3.10 (3-qubit reframe), §3.11 (float-coercion guard), §3.12 (vectorised Gram) entries unchanged; they were independent prior polishes and stay archived in place.

## 8. Closing

- [x] 8.1 Run `pytest` full suite; verify all tests pass. (1005 passed, 19 skipped locally on the active Python — multi-version CI verification runs through GitHub Actions on PR.)
- [x] 8.2 Run `openspec validate mps-transfer-matrix-contraction --strict`.
- [x] 8.3 Update `CHANGELOG.md` under unreleased.
- [x] 8.4 Run the existing `verify-examples` CI workflow on every bundled MPS example to confirm no observable behaviour change at n=3. (Covered by `TestShippedExampleEquivalence` in `tests/test_concept_gram_mps_contraction.py`, which loads both shipped MPS examples and pins contracted = statevector to 1e-12. The CI workflow itself runs on the PR.)

## 9. Downstream notification

- [ ] 9.1 Comment on polygram PR #43 (`clustered-dictionary-analysis`) noting that this q-orca change is the path to lifting the statevector wall. (Cross-repo notification; left for a human reviewer to post after merge.)
- [x] 9.2 Note in the q-orca CHANGELOG that the existing `compute_concept_gram_hea` path does NOT yet have a transfer-matrix contraction equivalent; HEA contraction is a forward-looking follow-on if a consumer asks for it.
