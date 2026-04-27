# Research: Polysemantic Encoding Beyond the Product-State Manifold

**Date:** 2026-04-24
**For:** q-orca-lang
**Status:** Research note — pre-proposal
**Scope:** Scaling analysis of the shipped polysemantic-clusters
encoding, and a ladder of generalizations that leave the
product-state manifold.
**Companion:** `docs/research/concept-encoding-efficiency.md` (the
language-extension questions A/B/C framing). This note extends that
analysis with concrete scaling numbers and a rung-by-rung plan for
non-product-state encodings.

---

## Summary

The `larql-polysemantic-clusters` example (OpenSpec change
`add-polysemantic-clusters`, PR #31) ships a 3-qubit × 12-concept
block-structured Gram matrix using product-state `Ry` encodings on an
n-torus. The analytic helper `compute_concept_gram` relies on the
factorized overlap `⟨c_i | c_j⟩ = ∏_k cos((θ_{i,k} − θ_{j,k})/2)` to
stay O(N² · n) in classical analysis cost.

That closed-form is the feature *and* the ceiling. The product-state
submanifold has n angular dimensions inside a 2ⁿ-dimensional Hilbert
space, so practical capacity for clean block-Gram tiers scales as
**N ≈ O(n²)** — linear clusters × linear intra-cluster concepts.
Past N ≈ 1000 concepts the statevector Gram path dies; past N ≈ 10⁵
even the dense pairwise Gram matrix doesn't fit in RAM. More
critically, the intra-cluster tier is *uniform* by construction
(isotropic tetrahedral scatter), which does not match what real
sparse-autoencoder dictionaries look like.

This note maps the practical scaling walls, frames "leaving the
product manifold" in terms of the unification hierarchy, and
recommends a concrete next step: **ship a rung-1 MPS-bond-2 example**
that keeps the polynomial analytic-Gram property while adding
adjacent-qubit correlations. An OpenSpec proposal lives at
`openspec/changes/add-mps-concept-encoding/`.

---

## Part 1 — Scaling of the shipped scheme

### Complexity recap

Let `n` = qubits, `K` = clusters, `m` = concepts per cluster,
`N = K·m`, `S` = shots per query. Target intra-overlap
`T ≈ 0.72`, inter-overlap cap `ε < 0.10`, axis-aligned cluster
centers so `K ≤ n`, `m ≤ n`.

| axis | per-circuit | total |
|---|---|---|
| qubits | `n` | — |
| gates | `2n` Ry (prep + inverse-prep query) | `2nN` |
| depth | `2` (all Ry's on distinct qubits, parallelizable) | — |
| shots | `S` | `NS` |

| Gram method | time | space |
|---|---|---|
| statevector (current helper) | `O(N² · 2ⁿ)` | `O(N · 2ⁿ)` |
| closed-form `∏ cos((θᵢ−θⱼ)/2)` | `O(N² · n)` | `O(N · n)` |

The matrix itself is `O(N²)` at 16 B per complex entry.

### Practical estimates — 5 regimes

With `S = 1024`, `T = 0.72`, `ε < 0.10`, axis-aligned so
`N ≈ n²`:

| regime | N | n | closed-form Gram | dense Gram RAM | wall-clock realistic |
|---|---|---|---|---|---|
| demo baseline | 12 | 3 | < 1 μs | 2 KB | **~5–10 s** (sim) ✓ |
| toy dict | 50 | 8 | ~μs | 40 KB | ~1 min (sim) ✓ |
| small LM-scale | 256 | 16 | ~ms | 1 MB | ~30 min (sim) ✓ |
| small SAE | 4 K | 64 | ~10 s | 256 MB | ~1 hr (QPU push) |
| SAE-scale | 65 K | 256 | ~hour CPU / min GPU | **64 GB** | days (QPU) — research-only |
| production SAE | 1 M | 1000 | ~weeks | 16 TB | classical SAE wins |

### The five walls, ordered by which bites first

1. **Statevector-based Gram wall** — bites at `n ≈ 20–25`. The
   current helper builds a 2ⁿ amplitude vector per concept; at n=20
   that's 16 MB × N concepts. Switch to closed-form contraction
   beyond this point. Purely a classical-analysis concern.
2. **Simulator wall-clock** — bites at `N ≈ 1–5 K`. Qiskit
   BasicSimulator executes each circuit in Python with per-circuit
   transpile overhead ~ms; batching reduces but does not eliminate.
3. **QPU queue/reload latency** — bites at `N ≈ 10 K`. On current
   IBM / IonQ hardware, per-circuit queue+reload is seconds to
   minutes. Execution itself is fast; scheduling dominates.
4. **Dense Gram storage** — bites at `N ≈ 30 K – 100 K`. `N² × 16 B`
   fills RAM. Past here, only sampled / block-sparse / clustered
   Gram queries are viable.
5. **Angular resolution** — bites at `n ≈ 100+`. Scatter radius
   `Δ ∝ 1/√n` drops below per-qubit Ry calibration noise
   (~0.1°–0.5° on current hardware). Intra-cluster tiers blur into
   each other.

### The honest crossover

Up to `N ≈ 1 K` this is a valid methodology. Beyond `N ≈ 10 K`
classical sparse-autoencoder tooling is strictly better — the
quantum register uses only `n` of the `2ⁿ` available dimensions, so
there is no information-density speedup. The interesting research
question isn't "can we scale N?" but **"can we leave the
product-state manifold without losing structured tier control and
polynomial analytic overlap?"** — which is the subject of Part 2.

---

## Part 2 — What "leaving the product-state manifold" means

### The manifold and its constraint

Product states are
`|c⟩ = |ψ_0⟩ ⊗ |ψ_1⟩ ⊗ ... ⊗ |ψ_{n-1}⟩`. With `Ry`-only preps, each
factor is a single angle, so concepts live on an **n-torus** `T^n`
inside the full state space `CP^(2ⁿ − 1)`. For n=3: product states
have 6 real parameters, the full state space has 14. You use a
sliver.

The sliver buys you the factorized overlap
`⟨c_i | c_j⟩ = ∏_k cos((θ_{i,k} − θ_{j,k})/2)` — `O(n)`, closed-form,
per-axis independent. The moment you leave, that factorization
dies. Inner products become contractions, amplitudes become
correlated, and the analytic helper needs more machinery.

### The unification analogy

The transition from product states to entangled states maps cleanly
onto the **unification hierarchy** used in `concept-encoding-
efficiency.md`:

| ansatz class | unification analog | decidability / cost |
|---|---|---|
| product state, Ry only | first-order unification | `O(n)` closed-form |
| MPS bond χ | Miller pattern fragment (restricted higher-order) | `O(n · χ⁶)` contraction |
| HEA depth L | full higher-order unification (Huet, undecidable in general) | `O(2ⁿ)` statevector |
| stabilizer / Clifford | equational unification modulo Clifford algebra | `O(n³)` by Gottesman–Knill |
| MUBs / SIC-POVMs | E-unification modulo theory-specific equations | known closed-form per theory |

Each rung trades expressivity for computability. Rung 1 (MPS) is the
Miller pattern fragment of the state-preparation world: strictly
more expressive than rung 0, but still polynomial in all parameters.

### The four rungs

#### Rung 0 — product states (shipped)

- **Effect**: `Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)`
- **Parameters per concept**: `n`
- **Overlap**: `O(n)` closed-form
- **Capacity at clean tiers**: `N = O(n²)`
- **What it can express**: isotropic block Gram with uniform
  intra-cluster tier
- **What it cannot**: graded within-cluster similarity, sub-cluster
  hierarchies, overlap patterns that don't factor per-axis
- **Shipped in**: `examples/larql-polysemantic-clusters.q.orca.md`

#### Rung 1 — MPS with bond dimension 2

- **Effect**: `Ry(qs[0], a); CNOT(qs[0], qs[1]); Ry(qs[1], b); CNOT(qs[1], qs[2]); Ry(qs[2], c)`
- **Parameters per concept**: `n` (same as rung 0, but they now
  couple)
- **Overlap**: `O(n · χ⁶)` transfer-matrix contraction at χ=2 —
  polynomial, closed-form-ish
- **Capacity at clean tiers**: `N = O(n³)` by available hierarchy
  depth
- **What it can express**: graded intra-cluster similarity,
  nearest-neighbor sub-cluster structure, two-level hierarchies
- **What it cannot**: non-local correlations across the qubit line,
  arbitrary 2-designs
- **Q-orca surface**: already-parsed gates (CNOT, Ry), multi-gate
  effect string, same parametric-expansion path as rung 0
- **Proposed in**: `openspec/changes/add-mps-concept-encoding/`

#### Rung 2 — hardware-efficient ansatz, depth L

- **Effect**: `L` alternating layers of single-qubit rotations and a
  fixed entangling pattern (ring of CNOTs or CZs). Effect string
  length grows to `O(L · n)` gates.
- **Parameters per concept**: `L · n`
- **Overlap**: no closed form. Either `O(2ⁿ)` statevector simulation
  or quantum-native SWAP / Loschmidt estimate.
- **Capacity at clean tiers**: up to `O(2ⁿ)` at `L = poly(n)`
  (2-design regime).
- **What it can express**: arbitrary Gram structure, full
  expressivity bounded by circuit depth.
- **Analyst tools needed**: variational fitting (pick angles to
  target a given Gram), or tolerance-based design-by-construction.
- **Q-orca surface**: current grammar bloats — each concept needs
  `L · n` angle literals, which is how the language-extension
  question **A** in the companion research note becomes load-
  bearing. Tuple-valued parameters are the minimum grammar that
  keeps rung 2 pedagogically clean.

#### Rung 3 — designed non-product families

Specific constructions with known overlap structure:

- **Mutually unbiased bases**. In dimension `d = 2ⁿ`, up to `d + 1`
  bases with inter-base overlap exactly `1/d`. Packs
  `d(d+1) = O(4ⁿ)` states with two-tier Gram. Preparation via
  Clifford circuits; overlap known analytically per construction.
- **Dicke / symmetric states**. `|D^n_k⟩` = symmetric superposition
  over weight-k basis strings. Combinatorial overlaps. Natural for
  bag-of-words / multiset concepts.
- **Stabilizer / graph states**. Clifford-preparable. Overlaps in
  `{0, 1/2^k}`. Gottesman–Knill makes classical simulation cheap;
  good for discrete-tier dictionaries.
- **QFT basis**. `|c_i⟩ = QFT|i⟩`. Mutually unbiased with
  computational basis; the "dual-basis" flavor of polysemy.

These are not a continuous ansatz family — each is its own algebra
with its own closed-form overlap. From an analyst's point of view,
each one needs its own helper.

### Signature of each rung

| rung | overlap cost | capacity `N` at clean tiers | q-orca effect | analyst tool |
|---|---|---|---|---|
| 0: product | `O(n)` | `O(n²)` | `n` Ry | `compute_concept_gram` ✓ |
| 1: MPS χ=2 | `O(n · 64)` | `O(n³)` | `n` Ry + `n−1` CNOT | **new** `compute_concept_gram_mps` |
| 2: HEA depth L | `O(2ⁿ)` or SWAP | up to `O(2ⁿ)` | `L·n` Ry + `L·n` CNOT | variational fitter |
| 3: algebraic | theory-specific | up to `O(4ⁿ)` | Clifford circuit | per-theory helper |

---

## Part 3 — Recommendation and roadmap

### Rung 1 is the natural next step

Three reasons:

1. **Minimal grammar departure.** Rung 1 needs no new parser surface
   — CNOT is already in the gate set, effect strings already accept
   multiple gates, parametric expansion already binds angle literals
   per call site. All work is in a new compiler analysis helper and
   a new example/demo pair.

2. **Preserves the analytic-benchmark property.** The pedagogical
   value of the existing polysemantic demos is that empirical
   Monte-Carlo results can be compared to a closed-form analytic
   Gram matrix. Rung 1 keeps this — transfer-matrix contraction at
   `χ = 2` is polynomial in `n`, `N`, and `χ`. Rung 2 does not: at
   depth `L = poly(n)` the overlap requires `O(2ⁿ)` work.

3. **Answers a concrete research question.** Rung 1 produces a Gram
   matrix with **graded intra-cluster similarity** (adjacent-qubit
   correlations induce non-uniform within-block entries), and the
   option of **two-level hierarchies** (super-clusters containing
   clusters). These are the structures real SAE dictionaries show
   (Elhage et al., `2209.10652`; Anthropic interpretability,
   `2309.08600`) and the rung-0 scheme provably cannot express.

### What rung 1 does not answer

It does not solve the capacity problem for real-SAE scales
(`N = 10⁵`+). That requires rung 2 or rung 3, and the grammar-
surface work implied by language-extension question A in
`concept-encoding-efficiency.md`. Rung 1 is the step that shows
whether the "analytic benchmark + empirical demo" pattern survives
leaving the product manifold at all; rungs 2 and 3 become scoped
proposals only after rung 1 has landed.

### Suggested sequencing

1. **Ship rung 1** via the OpenSpec change
   `add-mps-concept-encoding` (this repo, drafted alongside this
   note).
2. **Measure** what rung 1 actually gives us: are graded tiers
   useful pedagogically? Does the helper's `O(n · χ⁶)` cost stay
   manageable for `n ≤ 8`?
3. **Only then** open language-extension question A (tuple-valued
   parameters, named sub-circuits) as a precondition for rung 2.
   Rung 2 bundled together with grammar changes is too much scope
   at once.
4. **Defer** rung 3 (algebraic constructions like MUBs) until there
   is a concrete research use-case; each construction needs its own
   helper and the closed-form analyses are less pedagogically
   unified.

---

## Part 4 — Open research questions (specific to this direction)

1. **Does rung 1 produce graded intra-cluster tiers for any
   angle-choice strategy, or only for specifically-designed choices?**
   The CNOT staircase induces adjacent-qubit correlations; whether
   this translates into useful tier gradation depends on how cluster
   centers are placed relative to the CNOT structure. Needs
   experimental exploration in the demo.

2. **What's the right hierarchy topology for rung 1?** Linear CNOT
   chain induces 1D locality. A "brick-wall" or tree CNOT pattern
   would induce 2D or hierarchical locality. The choice affects
   which sub-cluster structures are natural.

3. **Can the compiler auto-detect the ansatz family?** Today the
   caller picks between `compute_concept_gram` and
   `compute_concept_gram_mps`. Auto-detection would let a future
   verifier rule check "this effect is product-state / MPS-1D /
   HEA-depth-L" structurally, which is a precondition for
   capacity-based warnings ("your Gram target needs rung ≥ 2").

4. **Is there a polynomial-depth rung 2 family with closed-form
   overlap?** Matchgate circuits (Bravyi, `quant-ph/0507002`) are
   classically simulable in `O(poly(n))` and are strictly more
   expressive than product states. They occupy a slot between rung 1
   and rung 2 that this note does not separately enumerate. Worth a
   KB pass via `search_papers` with wing `q-orca-implementations`,
   room `circuits`.

---

## KB references

Primary (already indexed or worth confirming):

- `2209.10652` — Elhage et al., "Toy Models of Superposition"
- `2309.08600` — Anthropic, sparse autoencoders on Claude-family
  models
- `quant-ph/0604066` — Vidal, efficient MPS simulation
- `quant-ph/0604035` — Perez-García, Verstraete, Wolf, Cirac,
  "Matrix Product State Representations"
- `1208.0692` — Brandao et al., random circuits as 2-designs

Worth indexing specifically for rung-1 through rung-3 work (not yet
confirmed in KB — see `mcp__q-orca-kb__batch_index`):

- `quant-ph/0507002` — Bravyi, matchgate circuits
- `1605.00674` — Harrow et al., random quantum circuits and 2-designs
- Schollwöck, "DMRG in the age of matrix product states" (2011)
- Zauner's conjecture manuscript (SIC-POVM existence)

---

## Connection to existing and queued work

- **`add-polysemantic-clusters`** (shipped, PR #31): the rung-0
  example this note builds on. Status: merged to main.
- **`add-mps-concept-encoding`** (drafted alongside this note): the
  rung-1 proposal. Adds example + demo + `compute_concept_gram_mps`
  helper. No grammar changes.
- **`concept-encoding-efficiency.md`** (companion research note):
  language-extension questions A/B/C. Question A becomes
  load-bearing for rung 2; this note does not require it.
- **`add-resource-estimation`** (queued, 0/34 tasks): shares
  infrastructure with future rung-detection verifier work (language
  question C). Both are static analyses over gate-sequence
  structure.
