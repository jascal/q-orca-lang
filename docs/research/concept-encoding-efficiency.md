# Research: Efficient Encoding of N Concepts into M Qubits

**Date:** 2026-04-23
**For:** q-orca-lang
**Status:** Research note — pre-design, pre-proposal
**Scope:** Language / compiler implications of moving beyond the flat
"N literal-angle call sites" parametric-action pattern toward ansatz-
family grammars that can express efficient concept dictionaries.

---

## Summary

The shipped polysemantic examples (`larql-polysemantic-2`,
`larql-polysemantic-12`) and the queued `add-polysemantic-clusters`
proposal all use the same concept-encoding shape: **one parametric
action, N independent literal-angle call sites, product-state
concepts on an M-qubit register**. That shape is the simplest viable
demonstrator for the parametric-action mechanism, but it is a
*degenerate point* on a much richer design space. This note maps
that space — what "efficient encoding of N concepts into M qubits"
means under different definitions of efficiency, what the known
bounds are in each axis, and what would need to change in the q-orca
grammar / compiler / verifier to express the non-degenerate points.

The note is written as a research input, not a build proposal. It
identifies the language-extension questions worth opening OpenSpec
changes on, flags what's currently out of reach, and cites the
relevant arXiv literature (q-orca-kb wing `q-orca-physics`, room
`vqe` / `textbook`, and `q-orca-implementations`, room `circuits`).

---

## Problem statement

Given:

- an M-qubit quantum register (Hilbert space dimension `d = 2^M`),
- a target concept count N,
- a target overlap structure `G ∈ C^{N×N}` (e.g., block-clustered,
  near-orthogonal, ETF-equiangular, or random),

produce:

- an encoding map `i ↦ |c_i>` realized as a unitary circuit `U_i`
  applied to `|0^M>`,
- such that `<c_i | c_j> ≈ G_{i,j}` for all `i, j`,
- under a chosen efficiency objective.

The user's question "is there a generalization" is really *which
definition of efficiency*. There are at least three meaningfully
distinct ones, each with its own optimal construction, its own known
bounds, and its own implications for the q-orca grammar surface.

---

## Three efficiency notions

### Notion 1 — Packing efficiency: concepts per basis dimension

**Question.** Given M qubits and a pairwise overlap bound
`|<c_i | c_j>| ≤ ε` for `i ≠ j`, how large can N be?

**Known bounds.**

- `ε → 0` (exactly orthogonal): `N ≤ d = 2^M`. Trivially tight — an
  orthonormal basis.
- `ε = 1/√(d+1)` (equiangular): `N = d + 1` achievable when a
  SIC-POVM exists in dimension `d`. Existence of SIC-POVMs for all d
  is conjectured but only proven in specific dimensions (see
  Zauner's conjecture; Scott & Grassl, `0906.4025`).
- `ε = 1/√d` (pairwise-inner-product frames): `N = d² ≈ 4^M`
  achievable via mutually unbiased bases (when they exist); gives
  `d(d+1)` states in `d+1` MUB bases of `d` states each.
- Fixed `ε ∈ (0, 1)`: Welch bound / Kabatyanskii-Levenshtein
  bound; N can grow as `exp(d · f(ε))` for a convex function
  `f(ε) ↓ 0 as ε → 1`. This is the **Johnson-Lindenstrauss regime
  for quantum states** — exponentially many concepts fit in a
  bounded-overlap ball.

**Constructive realizations.**

- ETFs / SIC-POVMs: `N = d + 1` states, all pairs at fixed overlap
  `1/√(d+1)`. Circuit depth for preparing each is `O(poly(d))` in
  the general case, `O(poly(log d))` for a handful of structured
  dimensions (primes and prime-powers).
- Random unitary ansatz: draw N Haar-random states. Pairwise
  overlaps concentrate at `1/√d` with variance `O(1/d²)` — for any
  fixed ε tolerance, this is the **typical packing**, matching the
  JL regime up to constants.

**Implication for q-orca.** The existing parametric-action pattern
hits `N = M` concepts at M qubits (one Hadamard per qubit:
`larql-polysemantic-12`), which sits two exponential gaps below both
the packing optimum and the information-theoretic maximum. Nothing
in the current language surface prevents encoding `N = 2^M` or
`N = d²` concepts — it just requires more expressive preparation
circuits than single-qubit product states.

---

### Notion 2 — Preparation-circuit complexity: gates per concept

**Question.** Given an ansatz family and a target overlap structure,
how many gates / how much depth does it take to prepare each `|c_i>`?

**Known results by ansatz family.**

| Ansatz                                                 | Gates per concept | Max packing reachable                     |
|---------------------------------------------------------|-------------------|-------------------------------------------|
| Product state, single-axis rotation (`Ry` only)         | `M`               | `2^M` (real submanifold; uniform overlap) |
| Product state, full single-qubit `U3`                   | `M`               | `2^M` (full Bloch product)                |
| Matrix Product State, bond dim `χ`                      | `O(Mχ²)`          | entanglement-limited, `log₂χ` Schmidt rank |
| Hardware-efficient ansatz (HEA), depth `D`              | `O(MD)`           | 2-design at `D = poly(M)` → JL regime     |
| Clifford + single-T: Solovay-Kitaev approx              | `O(M · log^c(1/ε))` | dense in `SU(2^M)`; any packing           |
| Arbitrary unitary (Shende-Bullock-Markov)               | `O(4^M)`          | any state (impractical for `M > ~10`)     |

References in the q-orca-kb:
- Kerenidis & Prakash, `1603.08675` (quantum-inspired dictionary
  learning, amplitude encodings).
- Cerezo et al., `2012.09265` (VQE / variational ansatz families).
- Schuld et al., `2008.08605` (expressivity of parameterized
  quantum circuits as kernels).
- Farhi & Harrow, `1602.07674` (QAOA as a concept-expressive
  ansatz with polynomial depth).

**The qualitative takeaway.** The current product-state `Ry` ansatz
pays `M` gates per concept and gets a *linear submanifold* of the
full state space. A depth-`D` HEA pays `O(MD)` gates per concept
and gets an approximate 2-design — enough to hit the JL packing
limit. That's a polynomial-in-M overhead to gain an exponential-in-M
packing gain. For the polysemanticity demo family, this is the
"realistic" regime: real mechanistic-interpretability dictionaries
live in the 2-design / random-matrix part of state space, not on a
low-dim product submanifold.

**Implication for q-orca.** The language currently expresses each
`|c_i>` by literally spelling out its gate sequence as the effect
string of a parametric action. For product states this is fine — the
effect string is short. For HEA-depth-D ansätze, the effect string
becomes `O(MD)` gates long, and worse, **every concept has the same
structural pattern differing only in angle values**. That's a
grammar / duplication problem the current parametric-action surface
doesn't solve: it lets you vary per-site *arguments* but not
per-site *structural patterns*. See §4 below.

---

### Notion 3 — Dictionary parameter count: bits to specify the dictionary

**Question.** How many real numbers does it take to pin down all N
concepts jointly, as a function of (N, M, ansatz)?

**Upper bounds by scheme.**

| Scheme                                       | Params total       |
|-----------------------------------------------|--------------------|
| Independent concepts, product-state `Ry`      | `NM`               |
| Independent concepts, full single-qubit `U3`  | `3NM`              |
| Shared backbone + per-concept linear head     | `P_shared + NP_head` |
| Sparse autoencoder factorization (Elhage)     | `≪ NM` at training optimum |
| Low-rank concept tensor, rank `r`             | `r(N + Md)`        |
| MPS dictionary, bond dim `χ`, shared core     | `O(Mχ² + Nχ)`      |

References:
- Elhage et al., `2209.10652` — toy models of superposition; the
  SAE-factorization framing originates here.
- Anthropic interpretability team, `2309.08600` — sparse
  autoencoders on Claude-family models; empirical dictionary-param
  counts ≪ `NM`.

**The qualitative takeaway.** For large N, independent-concept
parametrization wastes parameters whenever the concepts have any
shared structure. The research conjecture powering mechanistic
interpretability is that *natural* concept dictionaries always have
shared structure — clusters, hierarchies, part-whole decompositions
— and the effective free-parameter count is closer to `O(NM + P_shared)`
than `NM` alone. An expressive language for concept encoding should
make that sharing explicit.

**Implication for q-orca.** The current grammar assumes each call
site is fully independent — N triples of angle literals, no sharing.
For N = 12 this is fine (36 literals). For N = 10⁶ — the scale of
real SAE dictionaries — it's impossible as a literal table. A
language extension for *compressed concept dictionaries* would
need a way to say "the N concepts share backbone `U_θ` and differ
only in per-concept tails `V_{φ_i}`."

---

## Q-orca language implications

The three notions above translate into three concrete language
questions, ordered by increasing grammar scope.

### Language question A — Ansatz-family call sites

**Sketch.** Allow a parametric action to declare a *structural
template* (a gate sequence with placeholder angle variables) and
have each call site supply **only** the angle values, not the
structure.

Today's grammar already does this — `query_concept(a: angle,
b: angle, c: angle)` + `Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)`
is exactly an ansatz-family template with 3 angle slots. The gap is
quantitative: a depth-`D` HEA template has `O(MD)` angle slots, which
bloats the signature. A reasonable extension:

- **Tuple-valued parameters**: `query_concept(θ: angle_tuple[MD])`
  with effect `HEA(qs, θ)` where `HEA` is a gate-expansion macro.
  Call sites pass a single tuple literal (`[0.1, 0.2, ...]`) instead
  of `MD` positional arguments.
- **Named sub-circuits**: allow the effect string to reference
  another action by name, enabling decomposition
  (`query_concept` effect = `layer(qs, θ[0:M]); layer(qs, θ[M:2M]); ...`).

### Language question B — Shared-backbone + per-concept-tail actions

**Sketch.** Let an action declare a *shared* parameter vector
(bound at machine-definition time, not per call site) plus
*per-concept* angle parameters.

Syntax proposal:

```
## actions
| Name             | Signature                               | Effect                                            |
|------------------|-----------------------------------------|---------------------------------------------------|
| prepare_concept  | (qs, ~backbone, tail: angle_tuple[M])   | HEA(qs, backbone); Ry_layer(qs, tail)             |
```

where `~backbone` is a context-bound tuple and `tail` is per-call.
This separates `P_shared` from `N × P_tail` in the grammar,
matching the sparse-autoencoder parametrization directly.

Open question: is `backbone` best expressed as a new `## context`
field type (`list<angle>`), a new kind of action parameter with a
sigil-marked binding mode (`~` for shared), or as a separate
`## ansatz` top-level section? Each has tradeoffs in how the parser,
verifier, and compiler see it.

### Language question C — Structural verification of ansatz properties

**Sketch.** Extend the verifier with rules that check *ansatz-level*
properties rather than per-call-site properties.

Current verifier rules operate at the level of individual gate
sequences — unitarity per call site, control/target overlap per
call site, etc. Ansatz-level questions include:

- **Expressivity**: does the ansatz family reach enough of the
  state space for its intended N? (E.g., a product-state `Ry` ansatz
  over 3 qubits can't reach `N = 12` nearly-orthogonal states.)
- **Depth bound**: does the specified ansatz fit within a target
  depth budget?
- **Entanglement structure**: does the ansatz produce states with
  bounded Schmidt rank (MPS-expressible) or full entanglement?
- **2-design approximation**: is the ansatz deep enough to
  approximate a 2-design, i.e., suitable for random-matrix
  packing arguments?

These rules would consume an `## ansatz` section or annotations on
a parametric action and run once per machine, not per call site.
They sit adjacent to the `check_resource_invariants` rule proposed
in `openspec/changes/add-resource-estimation/` — same shape (static
analysis of circuit-structure properties), different axis (ansatz
properties vs. resource counts).

---

## Connection to existing and queued work

- **`extend-gate-set-and-parametric-actions`** (shipped, archiving
  next): shipped the minimum-viable parametric-action surface. Every
  notion-1, notion-2, notion-3 point discussed above builds on top
  of that surface.

- **`add-polysemantic-clusters`** (proposed, this session): stays
  inside the current grammar. Uses product-state `Ry` on 3 qubits
  for 12 concepts with structured clustering. Sits at the degenerate
  point of the design space — notion-1 reaches `N = 12 ≪ 2^M = 8`
  (actually exceeds 2^M via non-orthogonal packing), notion-2 pays
  just `M` gates per concept, notion-3 pays `3N = 36` independent
  literals. This is *the right scope* for a pedagogical demo; it is
  *not* the right scope for a real dictionary.

- **`add-resource-estimation`** (proposed, 0/34 tasks): shares
  infrastructure with language question C above. A shared analysis
  backend that computes circuit-structure properties (depth, gate
  count, 2-design distance, Schmidt rank) would serve both
  resource-bound verification and ansatz-property verification.

- **`add-runtime-state-assertions`** (proposed, 0/48 tasks): shares
  vocabulary with ansatz-level entanglement-structure checks. If a
  machine's concepts are declared MPS-expressible, runtime
  assertions on Schmidt rank validate that at simulation time.

---

## Framing note — parametric actions as unification

A useful framing for readers coming from a logic / type-systems
background rather than a physics background: **the parametric-action
grammar is a unification system, and "ansatz" is the physics-side
name for the same move**.

Both are instances of one pattern: *commit to a schematic form with
holes, then determine the holes by constraint-solving*.

| Step                       | Physics side (ansatz)              | Logic side (unification)           |
|----------------------------|------------------------------------|------------------------------------|
| Commit to a structure      | trial wavefunction `ψ(x; a, b)`    | term with metavariables `f(X, g(Y))` |
| Identify the holes         | coefficients / angles              | metavariables                      |
| Assert a constraint        | satisfies a PDE or cost function   | matches another term               |
| Solve for the holes        | substitute + solve                 | unification algorithm              |
| Result                     | a specific state                   | a substitution                     |

Under this framing, the three language questions in §4 map onto the
unification hierarchy:

- **Question A** (tuple-valued parameters, named sub-circuits) is
  *first-order* unification at scale — same expressive power as
  today's grammar, just more compact surface syntax.
- **Question B** (shared backbone + per-concept tail) is
  *higher-order* unification — you're leaving the *shape* of the
  backbone as a hole, not just angle values. Undecidable in the
  general case (Huet, 1973); tractable only for restricted patterns
  (Miller's pattern fragment, λ-Prolog).
- **Question C** (ansatz-property verification) is *unification
  modulo an equational theory* (E-unification) — the verifier plays
  the role of the theory, and ansatz properties (depth, entanglement
  structure, 2-design distance) are the equations you're unifying
  modulo.

This matters for scoping: **each step up the unification hierarchy
carries decidability and complexity costs that are well-characterized
in the logic literature**. A build in this direction should not
rediscover those costs from scratch. In particular, any "shared
backbone" extension should lean on the Miller pattern fragment (or
Nipkow's higher-order patterns) rather than full higher-order
unification, to keep the grammar tractable.

Concrete suggested reading for a future implementer:

- Baader & Snyder, "Unification Theory" (in the Handbook of
  Automated Reasoning, 2001) — the reference text for E-unification
  and decidable fragments.
- Miller, `A logic programming language with lambda-abstraction,
  function variables, and simple unification` (1991) — the pattern
  fragment of higher-order unification, decidable in linear time.
- Solar-Lezama, "Program Sketching" (PLDI 2006 onward) — the
  software-synthesis community's term of art for "ansatz," with
  SMT as the constraint solver. Structurally closer to the q-orca
  parametric-action surface than the physics literature.

---

## Open research questions

These are questions the existing q-orca-kb does **not** cleanly
answer and that a real build in this direction would need to address:

1. **What's the shortest-circuit family that achieves ETF packing
   in `d = 2^M`?** Known constructions for specific dimensions exist
   (e.g., Weyl-Heisenberg SICs) but a general recipe polynomial in
   both M and N = d+1 is an open problem.

2. **Is there a q-orca-expressible ansatz family that provably
   approximates a 2-design at polynomial depth and is interpretable
   at the call-site level?** The research term here is "brick-wall
   random circuits" (Brandao et al., `1208.0692`), but encoding
   their structure in a parametric-action grammar without losing
   per-concept readability is open.

3. **For a clustered concept dictionary, can the cluster assignment
   be encoded as a small classical side-channel (int-typed action
   parameter) and the intra-cluster geometry as an angle-typed
   ansatz tail?** This is the q-orca-native analog of the sparse-
   autoencoder factorization and would be a clean fit for the
   existing parametric-action grammar if the shared-backbone
   question above is answered.

4. **Does a machine-checkable notion of "concept dictionary
   interpretability" exist?** Real SAE work measures interpretability
   via downstream behavioral tests (feature ablation, steering). A
   declarative equivalent in q-orca would be a verifier rule that
   asserts some invariant connecting concept encodings to machine
   transitions. It is not obvious what that invariant should be.

---

## Recommendation

Do **not** extend the parametric-action grammar in the
`add-polysemantic-clusters` proposal's scope. Keep that change at
its current "product-state Ry on 3 qubits, 12 call sites" size —
it's the right pedagogical step after `larql-polysemantic-12`, and
bundling a grammar extension into it would bloat scope.

Instead, if this direction gains traction:

1. Open a dedicated OpenSpec change for **language question A**
   (tuple-valued parameters + named sub-circuits) — this is the
   minimal extension that unlocks depth-`D` HEA call sites without
   needing shared-backbone grammar.
2. Ship a second clustered-polysemantic example using that
   extension, this time with HEA depth 2 or 3 on 4–5 qubits,
   targeting a richer Gram matrix than product-state Ry can
   express.
3. Only then open a change for **language question B** (shared
   backbones), once there's a concrete second example demonstrating
   why the split is worth the grammar cost.
4. Defer **language question C** (ansatz-property verification)
   until the shared-backbone grammar is in use — at that point
   there is real code to verify *about*, rather than speculating
   about invariants on unfinished language surface.

---

## KB references used

Papers in q-orca-kb that directly informed this note (add via
`batch_index` if not yet present):

- `2209.10652` — Elhage et al., "Toy Models of Superposition"
- `2309.08600` — Anthropic interpretability, sparse autoencoders
- `1603.08675` — Kerenidis & Prakash, amplitude encodings / qRAM
- `2012.09265` — Cerezo et al., variational quantum algorithms
- `2008.08605` — Schuld et al., PQCs as kernel methods
- `1602.07674` — Farhi & Harrow, QAOA expressivity
- `1208.0692` — Brandao et al., random circuits as 2-designs
- `0906.4025` — Scott & Grassl, SIC-POVM constructions

Papers worth indexing specifically for a build in this direction
(not yet confirmed in KB):

- Zauner's conjecture manuscript (SIC-POVM existence)
- Welch bound original paper (1974) — foundational for packing
- Levenshtein's 1998 extensions to the Kabatyanskii-Levenshtein
  bound for spherical codes
