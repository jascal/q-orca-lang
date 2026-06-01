## Context

`compute_concept_gram_mps` is the analytic Gram path for MPS-encoded
hierarchical-polysemantic machines. It enumerates the call sites of
a parametric concept action (the "preparation" or "inverse" form of
a CNOT-staircase), evaluates each site's angle arguments, builds the
resulting statevector by applying the staircase circuit to `|0ⁿ⟩`,
and returns the N×N matrix of inner products.

The cost structure of the current implementation:

- **Per-state**: O(2ⁿ) memory + O(n · 2ⁿ) compute (each gate
  application is a 2ⁿ-vector update).
- **Pairwise**: N² inner products, each O(2ⁿ). After `tech-debt
  §3.12`'s vectorisation, the N² loop is a single BLAS matmul of
  shape `(N, 2ⁿ) @ (2ⁿ, N)`, which is asymptotically the same but
  hits BLAS's per-call efficiency.

The 2ⁿ factor is the wall. At n=3 (the shipped example) it's
trivial. At n=25 it's 256 MB *per state*; at n=32 it's 64 GB per
state. No matter how fast the per-state simulation, the storage is
exponential.

The matrix product state (MPS) representation captures the same
states with **O(n · χ²)** parameters total — linear in n, with
χ controlled by entanglement structure. The staircase-prepared
state with one CNOT per step has Schmidt rank 2 across every
bipartition, so χ=2 is exact (not approximate). This is precisely
the structural property `add-mps-concept-encoding` was named for.

The contraction algorithm:

1. Each per-feature state is represented by `n` tensors
   `A_k ∈ ℂ^(χ_L × d × χ_R)` with `d=2` (physical index = qubit
   computational basis) and `χ ∈ {1, 2}` (1 at the chain endpoints,
   2 in the interior for χ=2).
2. To compute `⟨ψ | φ⟩`, for each site k contract the physical
   index between `A_k^*` (from ψ) and `B_k` (from φ), giving a
   "transfer matrix" `T_k = Σ_s (A_k[:, s, :])^* ⊗ (B_k[:, s, :])`
   of shape `(χ², χ²)`.
3. Multiply the `T_k`s left-to-right; the final scalar is `⟨ψ | φ⟩`.

Cost: each transfer-matrix construction is O(χ²·d·χ²) = O(χ⁴·d),
and each chain step is a `(χ², χ²) · (χ², χ²)` multiply costing
O(χ⁶). Total per-overlap: **O(n · χ⁶)**. Per-state memory: O(n · χ²)
= **constant in n** at fixed χ.

For χ=2 this is 64n ops/overlap with 4n complex numbers in memory.
n=32 → 2048 ops/overlap with ~128 floats stored.

The conversion from the parsed staircase effect to MPS tensors is a
well-known recipe:

- Each `Ry(qs[k], θ)` modifies the local tensor `A_k` to apply the
  single-qubit rotation on the physical index.
- Each `Rz(qs[k], φ)` similarly modifies `A_k` (phase on the
  physical-index-1 component).
- Each `CNOT(qs[k], qs[k+1])` couples bond indices: the control's
  computational-1 component xor's the target's index. In bond form,
  this becomes a structured (χ_L × 2 × χ_M_new) and
  (χ_M_new × 2 × χ_R) tensor pair at sites k and k+1 with
  χ_M_new=2.

For the cross-coupled staircase
`Ry(0); CNOT(0,1); Ry(1); Rz(1); CNOT(1,2); Ry(2); …` the bond
dimension is exactly 2 between every adjacent pair after the first
CNOT, matching the χ=2 pin. Sites without an incoming CNOT have
χ_L=1.

## Goals / Non-Goals

**Goals:**

- Implement the O(n · χ⁶) transfer-matrix contraction path for the
  cross-coupled rung-1 CNOT-staircase MPS at χ=2.
- Expose it via a `method` parameter on `compute_concept_gram_mps`:
  `"statevector"` (current), `"contracted"` (new), `"auto"` (default,
  threshold-based).
- Pin equivalence with the statevector path at small n via direct
  equality tests.
- Keep the statevector path bit-for-bit unchanged at every shipped n.
- Stay torch-free / qiskit-free (pure numpy).

**Non-Goals:**

- **χ > 2 support.** The bond-dim-2 pin remains. χ>2 requires
  multi-CNOT KAK decomposition per step plus higher-rank transfer
  matrices; that's a separate larger change with no current
  consumer asking for it.
- **HEA encoding.** `compute_concept_gram_hea` is a separate path
  with a different state-preparation convention. The contraction
  technique generalises but the conversion from HEA effect to MPS
  tensors needs its own derivation. Out of scope.
- **Auto-differentiation.** The contraction is a forward-only
  computation. No backward pass needed for current consumers.
- **Caching or memoisation** across calls. Each
  `compute_concept_gram_mps` call rebuilds tensors from scratch.
  Cross-call caching is a future optimisation.

## Decisions

**Decision 1 — `method="auto"` default with threshold at n_qubits=20.**

Three candidates were considered:

- `method="contracted"` default: cleanest, but the per-overlap
  constant of contraction (matrix multiply of (χ²×χ²) matrices,
  numpy overhead) dominates below n≈15. At n=3 the statevector
  path is ~4× faster.
- `method="statevector"` default: preserves current behaviour but
  forces every consumer wanting larger n to opt in explicitly.
- `method="auto"`: dispatches on n_qubits. Chosen.

The auto threshold of n_qubits=20 is conservative: at n=20
statevector is 16 MB/state which is still fine, but contraction
becomes the cheaper option both in time and memory. The 16-MB
per-state regime is also where pairwise compute starts hurting
(N² · 2²⁰ ops dominates for N>1000), so the threshold is the
"big-n regime begins" boundary.

The threshold is exposed as a module-level constant
`STATEVECTOR_NQUBIT_THRESHOLD = 20` so it can be tuned by callers
if benchmarking reveals a different crossover.

**Decision 2 — New module `mps_contract.py` for the conversion +
contraction.**

The conversion from parsed staircase ops to per-site MPS tensors
is ~80 LOC and the contraction is ~50 LOC. Both are independent
of the rest of `concept_gram_mps.py` (no QMachineDef dependence
once the ops are parsed). Putting them in a separate module makes
them unit-testable in isolation and reusable from a future
`concept_gram_hea` MPS path if one materialises.

**Decision 3 — Reuse the existing parser; only add a post-parse
step.**

`_parse_staircase_effect` already returns a list of `("ry", qubit,
coeffs)`, `("rz", qubit, coeffs)`, `("cnot", control, target)`
tuples. The new code consumes this list and builds MPS tensors;
the parser stays unchanged. This isolates the contraction change
from the parser, keeps the existing parser tests load-bearing, and
preserves every error path.

**Decision 4 — Equivalence test as the load-bearing acceptance gate.**

For n_qubits ∈ {3, 4, 5, 6} and every shipped MPS example
machine, the contracted Gram must equal the statevector Gram to
1e-12 absolute. This is the differential test that pins
correctness: if the contraction has a subtle index-ordering bug,
it shows up at n=3 in the equivalence test before any large-n
run.

Beyond n=6 the statevector path remains the reference but
synthetic tests can't compare because both paths run on the same
machine — there's no independent ground truth. The post-n=6 tests
assert structural invariants instead: Hermitian, unit-modulus
diagonal, no NaN/Inf, correct shape.

**Decision 5 — Tech-debt-backlog entry, not an inline-deferred fix.**

The MPS contraction has been deferred via the tech-debt-backlog
since the original `add-mps-concept-encoding` change. Per
tech-debt-backlog's §5 convention, "when an item grows enough to
warrant its own proposal/design (behavior change, new
requirement, cross-module impact), it is pulled out into a
dedicated OpenSpec change and the backlog entry is marked with a
pointer to that change." This change is the pull-out.

A new entry in `tech-debt-backlog/tasks.md` will reference this
change for posterity; the original deferred-decision text in
`add-mps-concept-encoding/design.md` stays in archive as
historical record.

## Risks / Trade-offs

**Risk:** the contraction has a subtle index-ordering or
conjugation bug that doesn't surface at small n.

Mitigation: the equivalence test at n ∈ {3, 4, 5, 6} on every
shipped example pins byte-identity at small n. The test is the
load-bearing gate.

Secondary mitigation: the contraction code is small (≤200 LOC)
and the structural pattern (transfer matrix per site, chain
multiplication) is textbook. Code review focuses on the
conversion (Ry/Rz/CNOT effects on per-site tensors) more than
on the contraction itself.

**Risk:** the per-overlap constant of contraction (numpy matmul
overhead at (4, 4) matrices) dominates at small N.

Mitigation: the `method="auto"` threshold of n_qubits=20 keeps
the statevector path active at small n where its overhead is
lower. Benchmarking against the bundled n=3 example confirms
no regression on the shipped consumer.

If benchmarking reveals the auto threshold should be higher
(say, n=22 instead of n=20), the module-level constant is the
single tuning knob.

**Risk:** consumers that pass `method="contracted"` explicitly
at small n hit the constant-factor overhead.

Acceptable. The contracted mode is documented as "asymptotically
preferable past `STATEVECTOR_NQUBIT_THRESHOLD`; small-n users
should leave `method="auto"` or pass `"statevector"` explicitly".

**Risk:** the MPS-tensor conversion handles only the
cross-coupled rung-1 staircase shape. Inverse-form staircases
(per the existing parser) need separate handling.

Mitigation: the parser already distinguishes preparation form
from inverse form. The contraction code dispatches on the
parsed form, falling back to the statevector path with a clear
error if it encounters a shape it can't handle. The minimal
v1 supports the preparation form (the larql-animals-interference
shape); inverse form support follows once a consumer needs it.

## Sequencing

Within this change:

1. `mps_contract.py` module — conversion + contraction routines.
2. Wire `method` parameter into `compute_concept_gram_mps`;
   dispatch logic.
3. Equivalence tests at n ∈ {3, 4, 5, 6} on every shipped
   MPS example machine.
4. Structural-invariant tests at larger synthetic n (Hermitian,
   unit-modulus diagonal, finite).
5. Documentation update in module docstring.
6. Tech-debt-backlog entry.

Each step gates the next; the change merges when the
equivalence tests pass.

## Migration Notes

No migration required. `method="auto"` default produces:

- **`statevector` results** for every shipped example
  (`n_qubits ≤ 5`) — byte-identical to today.
- **`contracted` results** for hypothetical large-n machines
  (`n_qubits ≥ 20`) — equivalent to statevector where both can
  run, and feasible where statevector OOMs.

Polygram consumers can opt into `method="contracted"`
explicitly when they want deterministic algorithmic choice
regardless of `n_qubits`.
