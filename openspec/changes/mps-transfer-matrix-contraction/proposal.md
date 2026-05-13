## Why

`q_orca/compiler/concept_gram_mps.py:compute_concept_gram_mps` is
the MPS-encoded concept-Gram analysis path. It computes
`gram[i, j] = ⟨c_i | c_j⟩` for every pair of call sites of a
parametric concept action whose effect follows the CNOT-staircase
MPS preparation convention from `add-mps-concept-encoding`.

Today it builds the **full `2ⁿ` statevector** for every call site
(call `infer_qubit_count(machine)` for `n`; allocate `2ⁿ` complex
amplitudes per state; simulate the staircase explicitly), then
contracts pairs via `flat.conj() @ flat.T` (already vectorised
under `tech-debt-backlog §3.12` / commit 1c13dc0). The module
docstring is explicit at lines 60-63:

> the present implementation uses an explicit 2ⁿ statevector
> simulation, which is fine for the shipped n = 3 example. The
> asymptotically-correct O(n · χ⁶) transfer-matrix contraction
> is tracked under tech-debt-backlog as a future optimization
> for larger n.

The contraction has stayed in tech-debt-backlog because no
shipped consumer needed it. That's about to change.

**Polygram** (the SAE-feature-interpretability frontend that
emits machines for this helper) is scoping a clustered-dictionary
primitive (polygram PR #43) and a Rung4 encoding (PR #42) that
expand the per-encoding feature cap from 8 to 16-32 features.
Even past 32 features the clustered path keeps per-block
encodings small enough that the statevector path holds. But
two adjacent workflows want larger registers:

1. **HEA_Rung2 with larger `n_qubits`** — already supported in
   polygram's encoding API; per-encoding cap scales as
   `2**n_qubits`. The MPS Gram helper isn't on the HEA path
   (HEA uses `compute_concept_gram_hea`) but the same memory
   wall applies analogously, and the contraction technique
   developed here transfers structurally.
2. **MPSRung1 extended past 3 qubits** — sized as polygram-side-
   only per the corrected `docs/research/rung3-rank-bound.md`,
   but exercises this helper at larger `n`. The statevector
   path holds up to ~25 qubits (storage 2²⁵·16 = 512 MB) and
   then OOMs.

Per-state storage at increasing `n_qubits` (complex128):

| n | bytes/state | notes |
|---|---|---|
| 3 | 128 B | shipped today |
| 10 | 16 KB | trivial |
| 20 | 16 MB | comfortable |
| 24 | 256 MB | tight on a laptop |
| 28 | 4 GB | needs a server |
| 30 | 16 GB | doesn't fit on most dev boxes |
| 32 | 64 GB | infeasible |

The asymptotically-correct path —  contracting the MPS
representation directly rather than materialising the
statevector — is O(n · χ⁶) per overlap, with χ²-sized
intermediate memory. At χ=2 (the current pin) the per-overlap
cost is roughly **64n operations** vs `2ⁿ` for the statevector
path, and the memory is **constant in n** vs exponential.

This change implements that contraction as a new code path in
`compute_concept_gram_mps`, gated by a `method` parameter,
with the existing statevector path retained as the small-`n`
reference and equivalence test target.

## What Changes

- **New transfer-matrix contraction implementation** in
  `q_orca/compiler/concept_gram_mps.py`. Builds per-site
  MPS tensors `A_k` of shape `(χ, 2, χ)` from the parsed
  staircase effect (Ry/CNOT/Rz at each site, with the
  cross-coupled angle expressions). Computes `⟨ψ | φ⟩` as a
  chain of transfer-matrix multiplications at cost
  `O(n · χ⁶)` per overlap.
- **`method` parameter** on `compute_concept_gram_mps`:
  `"statevector"` (current behaviour) | `"contracted"` (new) |
  `"auto"` (default: contracted when `n_qubits >= 20`,
  statevector otherwise). The threshold is chosen so the
  statevector path stays the cheaper option in the small-n
  regime (the per-overlap constant of MPS contraction
  dominates below ~n=15) while contraction takes over before
  statevector memory becomes painful.
- **Equivalence test**: for every `n_qubits ∈ {3, 4, 5, 6}`
  and every shipped MPS example machine, the contracted Gram
  equals the statevector Gram to 1e-12 absolute. Pins
  byte-equivalence of the two paths on the regime where both
  fit in memory.
- **No bond-dimension changes**. `bond_dim != 2` continues to
  raise `MpsGramConfigurationError`. The χ>2 path is a
  separate forward-looking change (multi-CNOT KAK
  decomposition + multi-rank transfer matrices); explicitly
  out of scope here.
- **Documentation update** in the module docstring: lines
  60-63 ("present implementation uses explicit 2ⁿ
  statevector ... tracked under tech-debt-backlog as a future
  optimization") become a description of the contraction
  algorithm + the `method` parameter + the `auto` threshold.
- **Tech-debt entry** in `openspec/changes/tech-debt-backlog/tasks.md`
  pointing at this dedicated change.

## Capabilities

### Modified Capabilities

- `compiler`: `compute_concept_gram_mps` accepts a `method`
  parameter. The `"contracted"` and `"auto"` modes are new
  algorithmic paths; the `"statevector"` mode preserves
  byte-identical behaviour with the pre-change implementation.

## Impact

- `q_orca/compiler/concept_gram_mps.py` — new contraction
  implementation (~250 LOC), `method` parameter on
  `compute_concept_gram_mps`, dispatch logic, doctsring update.
- `q_orca/compiler/mps_contract.py` — new module (~150 LOC)
  holding the `(staircase → MPS tensors)` conversion and the
  transfer-matrix contraction routine. Pure numpy. Importable
  separately for testing.
- `tests/test_concept_gram_mps_contraction.py` — new test
  module covering equivalence vs statevector on small `n`,
  scaling correctness on synthetic large-`n` machines (no
  ground-truth comparison; assertion is that contraction
  produces a Hermitian unit-diagonal Gram), and dispatch
  logic.
- `openspec/changes/tech-debt-backlog/tasks.md` — add an entry
  marking this work as pulled out into a dedicated change
  (per the §5 "pull out into a dedicated change" pattern the
  tech-debt-backlog already uses).
- `CHANGELOG.md` — entry under unreleased: "MPS Gram helper
  gains O(n · χ⁶) transfer-matrix contraction path; auto-
  selected past n_qubits=20."

**No breaking changes.** The `method` parameter defaults to
`"auto"`, which produces statevector results for `n_qubits ≤ 19`
(the current shipped regime, including all bundled examples).
Past `n_qubits = 20`, `"auto"` switches to `"contracted"` —
results match statevector to 1e-12 where both can run.

**Not on the critical path** for any currently-shipped
example. Motivated by downstream consumers (polygram) that
want to push past the statevector wall.
