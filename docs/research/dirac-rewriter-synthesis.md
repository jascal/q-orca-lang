# Dirac Notation Symbolic Rewriter — Synthesis Report

**Date:** 2026-04-18  
**For:** q-orca-lang  
**Status:** Research synthesis, pre-build  
**Scope:** Design decisions for a Python Dirac-notation symbolic rewriter exposed as MCP tools

---

## KB Coverage Delta

Before this investigation, the KB held 12,101 drawers. The formal-methods room already
contained:

- `2109.06493` — Chareton et al., "Formal Methods for Quantum Algorithms" (comprehensive survey;
  covers SQIR, VOQC, QWIRE, Qbricks, ZX-calculus, path-sum methods)
- `quant-ph/0402130` — Abramsky & Coecke, "A Categorical Semantics of Quantum Protocols"
- `0906.4725` — Coecke & Kissinger, "Picturing Quantum Processes" (monoidal categories,
  ZX foundations)
- `quant-ph/0412135` — Danos et al., measurement calculus rewriting system

**Gaps filled by this session's batch_index:** van de Wetering's ZX-calculus primer (2012.13966),
PyZX paper (1904.04735), egg/equality-saturation (2004.03082), Quartz quantum superoptimizer
(2204.09033), and DiracDec candidates. See KB delta note at end.

---

## Q1 — Decidability and Complexity of Dirac-Notation Fragments

The most important architectural decision is knowing which questions are decidable before
choosing a proof strategy.

**Closed (no symbolic parameters):** Any closed Dirac expression over a fixed finite-dimensional
Hilbert space with rational-coefficient amplitudes reduces to a matrix evaluation. Equality
checking is poly-time: compute both matrices numerically, compare. This fragment handles the
common case — fixed-angle circuits, basis-state arithmetic, standard protocol verification.

**Parameterized (symbolic angles θ):** Gate matrices become trigonometric polynomials.
Equality becomes polynomial identity testing over ℝ[sin θ, cos θ]. This is decidable: the
Schwartz-Zippel lemma gives a randomized poly-time test (evaluate at random θ, repeat
k times for 2⁻ᵏ error probability). Deterministic identity testing is a major open problem
in general, but for trigonometric polynomials of bounded degree the range [0, 2π) suffices
to distinguish non-identical polynomials by Chebyshev-node sampling.

**Universal equational theory (forall θ):** Requires real closed field quantifier elimination
(Tarski-Seidenberg). Decidable but EXPTIME in the worst case. Practically fine for
one-variable angle identities (e.g., Rx(θ)Rx(-θ) = I); expensive for multi-parameter goals.

**Consequence for the build:** The rewriter should have three modes:

1. **Numeric fast-path:** evaluate both sides as QuTiP/NumPy matrices at random angles;
   fast filter, catches 99% of equivalences in practice.
2. **Symbolic TRS:** term-rewriting to a normal form for common structural identities
   (inner products, tensor absorption, Hermitian adjoint rules).
3. **SMT fallback:** hand a polynomial equality goal to Z3 (which supports nonlinear real
   arithmetic) for parameterized cases the TRS cannot normalize.

The existing QuTiP dynamic verifier in q-orca already provides the numeric layer; the build
adds layers 2 and 3.

---

## Q2 — Rule Engine: egg (Equality Saturation) vs. Confluent TRS

Both are legitimate choices; the right answer depends on what the tool is *optimizing for*.

**Confluent TRS** (e.g., SymPy's `rewrite`, hand-written pattern-match) produces a unique
normal form when the rule set is confluent and terminating. This is ideal when you want
*canonical Dirac expressions* — a deterministic simplification that returns the same thing
regardless of evaluation order. It is simple to implement, easy to explain to an LLM ("here
is your expression in normal form"), and easy to audit.

The Dirac-notation rules *can* be made confluent: orient rules left-to-right toward simpler
forms (contracted inner products, distributed scalars, sorted tensor factors). DiracDec
(Jia et al.) uses exactly this approach — a convergent equational theory over kets/bras/operators.

**egg (equality saturation)** builds an e-graph of all expressions reachable by applying
rules in any order, then extracts the *cheapest* one by a cost function (e.g., fewest gates,
lowest T-count). It avoids the phase-ordering problem: you never commit to a bad rewrite
early. The POPL 2021 paper reports 1000× speedups over traditional optimizers on compiler
benchmarks. Quartz (2204.09033) applies egg directly to quantum circuit superoptimization.

**Recommendation for q-orca:**

Use a **two-layer architecture**:

- **Layer 1 — Confluent TRS (SymPy):** Normalize Dirac expressions structurally. Handle
  inner-product contraction (⟨i|j⟩ → δᵢⱼ), linearity (α|ψ⟩ + β|ψ⟩ → (α+β)|ψ⟩), tensor
  distribution, adjoint propagation. Output is canonical Dirac AST.
- **Layer 2 — egg circuit optimizer:** When the goal is circuit-level equivalence or gate
  count reduction, translate the normalized expression to a gate sequence and apply egg
  (or PyZX) at the circuit level.

This separation means the LLM interacts with clean normal forms (Layer 1), while hard
optimization is hidden in Layer 2. Do not try to run equality saturation over raw Dirac
expressions — the e-graph explosion will be severe without good term-size bounds.

---

## Q3 — ZX-Calculus vs. Dirac Notation for Circuit Equivalence

These are complementary, not competing. Each is stronger in a different regime.

**ZX-calculus strengths:**
- Provably complete for Clifford circuits (Backens 2014) and for all stabilizer circuits.
  Jeandel, Perdrix & Vilmart (2020) showed completeness over rational angles. Van de Wetering's
  2012.13966 gives the full working-scientist treatment.
- PyZX implements the standard simplification strategies (Clifford simplification, graph-like
  diagrams, T-count reduction) and is production-ready.
- Handles circuit identities that are hard to see in matrix notation: spider fusion,
  Hadamard color-change, π-commutation rules.
- Best for: automated gate-count reduction, T-count optimization, circuit equivalence at
  the gate-composition level.

**Dirac notation strengths:**
- Natural for state-level reasoning: teleportation protocols, error-correction syndromes,
  QRAM state preparation.
- Better for expressing *what a circuit computes* (output state) rather than *how it
  computes it* (gate sequence).
- What LLMs already know well — ket/bra expressions appear throughout training data.
- Best for: protocol verification, assertion checking, human-readable proof steps.

**Recommended bridge architecture:**

```
LLM writes ket-sequence spec
        ↓
 dirac_simplify (TRS layer)
        ↓
 canonical Dirac AST
        ↓ (for equivalence queries)
 translate_to_ZX()        ← thin bridge (~100 lines using PyZX API)
        ↓
 pyzx.full_reduce()       ← check if ZX diagram reduces to identity
        ↓
 return result to LLM in Dirac notation
```

This gives completeness at the circuit level (via PyZX) while keeping the user-facing
interface in Dirac notation. The bridge is light: PyZX accepts circuits as lists of gates;
translating a ket-sequence through the q-orca gate set to PyZX's Circuit object is
straightforward.

---

## Q4 — Representing Unitarity in the Verified-Compiler Lineage

The main design question is whether unitarity is a *type-level* invariant (structural
guarantee) or a *runtime check* (verified post-hoc).

**SQIR/VOQC approach** (Hietala et al., PLDI/POPL): circuits are *sequences of unitary
gate applications*; unitarity is structural because only unitary primitives are in the
grammar. VOQC proves optimization passes preserve semantic equivalence via Coq proofs.
No runtime check needed; correctness is a proof object.

**CoqQ approach** (Dong et al., POPL 2023, arxiv 2207.XXXXX): density-matrix semantics
with Dirac-style specifications. Unitarity is a property of the operator type. Verification
is by Coq proof terms over the density-matrix model.

**QWIRE approach** (Rand et al.): linear type system at the host language level. Qubit
linearity ensures no-cloning structurally. No separate unitarity proof needed for well-typed
circuits.

**For the q-orca Dirac rewriter:** q-orca already enforces structural unitarity (only
named gate primitives in the grammar). The rewriter should:

1. Tag operator AST nodes with a `unitary: bool` flag. Single-qubit rotations and named
   gates are `unitary=True` by construction; symbolic operators start `unitary=None`.
2. For the `dirac_check_unitary` MCP tool: symbolically verify U†U = I using SymPy
   matrix multiplication and `simplify`. For parameterized gates this is algebraically
   exact (Rx(θ)† Rx(θ) = I holds symbolically).
3. Measurement and partial-trace operators get `unitary=False`; the type system prevents
   them from appearing where a unitary is expected.
4. The long-term Lean 4 export path maps each `unitary=True` gate to a Lean4 proof term
   that the corresponding matrix is unitary; these are library lemmas, not regenerated
   each time.

---

## Q5 — Scalar Discharge Strategies

Scalars (complex amplitudes, normalization factors, global phases) are the thorniest part
of symbolic Dirac computation. ⟨ψ|φ⟩ can produce expressions like
`(1/√2) · e^(iθ) · (sin θ + i cos θ)` that SymPy's `simplify` may not reduce without help.

**Strategy hierarchy (apply in order, stop at first success):**

1. **Numeric witness (fast filter):** Evaluate scalar at 3–5 random angle values.
   If values differ, expressions are not equal — done. Cost: microseconds.
   
2. **SymPy trigsimp + simplify:** Handles sin²θ + cos²θ = 1, double-angle identities,
   Euler e^(iπ) = -1. Covers ~80% of realistic cases.
   
3. **Global phase quotient:** If checking circuit equivalence (not state preparation),
   identify up to global phase: equal if `simplify(expr1 / expr2)` yields a unit-modulus
   constant. Reduces many normalization headaches.
   
4. **Polynomial reduction (Gröbner basis):** Express sin θ and cos θ as algebraic elements
   satisfying s² + c² = 1; reduce both scalars via `sympy.groebner` over ℝ[s,c].
   Decides equality of trigonometric polynomials exactly.
   
5. **Z3 nonlinear arithmetic:** For expressions involving products of multiple symbolic
   angles or transcendental functions beyond trig, export to Z3's `RealVal` solver.
   Decidable but slower (~100ms per query).

This cascade is the same pattern DiracDec and most CAS-backed provers use. The key insight
is that the numeric witness (step 1) eliminates the vast majority of *non-equal* pairs
without any symbolic computation, leaving the expensive machinery for confirmed equalities.

---

## Q6 — LLM Feedback Loop Patterns

Three interaction patterns from the literature are directly applicable to q-orca's
MCP architecture.

**Pattern 1 — Proof Sketch + Step Check:**
LLM generates a sequence of Dirac expressions as proof steps; the rewriter verifies that
each step is a valid application of a named rewrite rule. Failed steps get a structured
error: `{rule: "inner_product_orthogonality", applied_to: "⟨1|0⟩", result: "0", expected: "1"}`.
The LLM revises based on the counter-evidence. This pattern works with any TRS that can
*explain* which rule applied or failed.

**Pattern 2 — Counter-Example Guided:**
The `dirac_prove_equal` tool, on failure, runs both expressions through the numeric evaluator
at a concrete angle (e.g., θ = π/4) and returns the numeric values. The LLM sees that
`expr1 = 0.707 + 0.000i` and `expr2 = 0.500 + 0.500i` — a concrete witness to inequality.
This is far more actionable than "expressions are not equal."

**Pattern 3 — Lemma Bank Growth:**
Each time a new identity is verified (e.g., `CRz(θ) ≡ (|0⟩⟨0| ⊗ I + |1⟩⟨1| ⊗ Rz(θ))`),
it is stored as a named lemma accessible to future calls. The LLM can call `dirac_apply`
with a lemma name to apply it in context, building proofs compositionally. This mirrors
Lean 4's `simp [lemma_name]` pattern and makes the growing lemma library the reusable
artifact of the proof effort.

**Implementation note:** The MCP tool signatures should always return Dirac notation
(not matrices or raw SymPy trees) so the LLM can reason over the output in natural language.
Include a `proof_steps: list[str]` field in the response so the LLM sees what the rewriter
actually did.

---

## Q7 — Lean 4 Export Path

Lean 4 is the right long-term target; Coq (used by SQIR/VOQC) is an alternative but
Lean 4's mathlib is growing faster and has better meta-programming for quantum applications.

**Short-term (MVP + v1):** Do not target Lean 4 directly. Instead, emit *proof certificates* —
a JSON list of rewrite rules applied in order with their premises. Example:

```json
{
  "claim": "Rx(θ) Rz(φ) Rx(-θ) = Rz(φ) (up to global phase)",
  "method": "matrix_equality",
  "steps": [
    {"rule": "expand_Rx", "before": "Rx(θ)", "after": "[[cos(θ/2), -i·sin(θ/2)], ...]"},
    {"rule": "matrix_multiply", ...},
    {"rule": "trigsimp", ...},
    {"rule": "global_phase_cancel", ...}
  ],
  "verified_numerically": true,
  "verified_symbolically": true
}
```

This certificate can be independently reconstructed and checked. It's also what a Lean 4
tactic would consume.

**Long-term (stretch):** Each named rewrite rule in the Python TRS has a corresponding
Lean 4 simp lemma. The proof certificate becomes a Lean 4 tactic script:

```lean4
example (θ φ : ℝ) : rx θ * rz φ * rx (-θ) = globalPhase _ * rz φ := by
  simp [expand_Rx, expand_Rz, Matrix.mul_assoc]
  ring_nf
  simp [Complex.exp_add, Real.sin_neg, Real.cos_neg]
```

The Python rewriter generates this script; Lean 4 checks it. This is the "certificate
exchange" pattern used by SMT-backed Lean tactics (e.g., `omega`, `polyrith`).

Practical prerequisite: someone needs to seed a Lean 4 library with the base gate
definitions (Rx, Ry, Rz, CNOT, CRz as `Matrix ℂ (Fin 2) (Fin 2)` or `Matrix ℂ (Fin 4) (Fin 4)`)
with their unitarity proofs. This is ~500 lines of Lean 4 and is the prerequisite to any
useful export. It is not a blocker for MVP.

---

## Q8 — Reuse vs. Rebuild

**Reuse (do not reimplement):**

| Component | What to use | Why |
|-----------|-------------|-----|
| Symbolic math | SymPy | Matrix arithmetic, trig simplification, polynomial GCDs, Gröbner basis — all production-ready |
| ZX-calculus engine | PyZX | ~10k LOC of validated rewriting; completeness proofs in the literature |
| Matrix simulation | QuTiP | Already in q-orca's dynamic verifier |
| SMT solving | Z3 (Python API) | Nonlinear real arithmetic, polynomial equality — pip install z3-solver |
| Quantum gate definitions | Qiskit | Already used by q-orca; gate matrix implementations are correct |
| MCP protocol | FastMCP / JSON-RPC stdio | Existing q-orca MCP pattern |

**Rebuild (thin layers, ~1000 lines total):**

- **Dirac AST** (~150 lines): `Ket`, `Bra`, `Outer`, `Inner`, `Tensor`, `Op`, `Scalar` dataclasses.
  SymPy doesn't have these natively; they wrap SymPy expressions at the quantum-mechanics level.
- **TRS rules** (~200 lines): Oriented rewrite rules for inner-product contraction, linearity,
  adjoint propagation, tensor distribution. Apply via pattern matching on the AST.
- **Normalizer** (~100 lines): Drive TRS to fixed point; detect loops; return canonical form.
- **ZX bridge** (~100 lines): Translate `Ket` sequence to PyZX `Circuit` object and back.
- **MCP tool wrappers** (~200 lines): Thin FastMCP handlers for the 8 proposed tools.
- **Lemma store** (~50 lines): JSON-backed dict of verified identities, searchable by name.

Total new code: ~800 lines Python. Everything else is library calls.

---

## Recommended Phased Build Plan

### Phase 0 — Prerequisites (1 day)

Install and test integration of SymPy, PyZX, Z3. Verify PyZX can round-trip a q-orca
Qiskit circuit (Rx, CRz, RZZ) through its simplification pipeline. Write one integration
test: Rx(θ)Rx(θ) simplifies to Rx(2θ).

### Phase 1 — MVP: `dirac_simplify` + `dirac_prove_equal` (2–3 days)

Goal: LLM can simplify a Dirac expression and check two expressions for equality.

Deliverables:
- `DiracAST` dataclasses and parser from string (e.g., `"|0⟩ ⊗ |1⟩"`)
- TRS rules covering: basis inner products, linearity, tensor absorption, adjoint
- Numeric fast-path via QuTiP matrix evaluation
- `dirac_simplify(expr_str) -> {normal_form, steps}`
- `dirac_prove_equal(lhs, rhs, angle_context) -> {equal, proof_steps, counterexample}`
- Test suite: ⟨0|1⟩ = 0, ⟨+|−⟩ = 0, H|0⟩ = |+⟩, Rx(π)|0⟩ = -i|1⟩

### Phase 2 — v1: Full 8-tool MCP surface (1–2 days)

Goal: Full MCP API usable by q-orca-lang's LLM prompts.

Deliverables:
- `dirac_apply(expr, rule_name) -> {result, step}`
- `dirac_inner_product(bra, ket) -> scalar`
- `dirac_tensor(exprs) -> tensor_product`
- `dirac_partial_trace(rho, subsystem) -> reduced_operator`
- `dirac_is_entangled(state) -> {entangled, reason}`
- `dirac_check_unitary(op) -> {unitary, witness}`
- Lemma store: `dirac_add_lemma`, `dirac_list_lemmas`
- Z3 scalar solver for parameterized equalities

### Phase 3 — Stretch: ZX bridge + proof certificates (2 days)

Goal: Circuit-level completeness and exportable proof artifacts.

Deliverables:
- `translate_to_zx(ket_sequence) -> pyzx.Circuit`
- `dirac_prove_equal` delegates to PyZX for gate-sequence goals
- Proof certificate JSON format
- Lean 4 tactic script generator (stub; requires Lean 4 library seed)

**Total estimate: 5–7 focused development days.**

---

## Must-Read Papers (Before Committing to Design)

**1. Van de Wetering — "ZX-calculus for the working quantum computer scientist" (arXiv 2012.13966)**  
The definitive entry point to ZX-calculus as a practical engineering tool. Covers completeness,
PyZX's algorithms, and when ZX is and isn't appropriate. Read this before deciding how much
weight to put on the ZX bridge vs. pure Dirac rewriting. 60 pages but scannable.

**2. Willsey et al. — "egg: Fast and Extensible Equality Saturation" (POPL 2021, arXiv 2004.03082)**  
The paper that made equality saturation practical. Read sections 1–3 (the e-graph data
structure) and section 5 (cost-function extraction). Decide after reading whether the
two-layer TRS + egg architecture or a pure egg approach makes more sense for Dirac expressions.

**3. Chareton et al. — "Formal Methods for Quantum Algorithms" (arXiv 2109.06493)**  
Already in the KB. The most comprehensive survey of the verified-compiler landscape.
Read sections 5 (ZX-calculus), 7.3 (SQIR), and 5.4 (VOQC). Establishes what the state
of the art can and cannot prove. Critical for understanding the unitarity/scalar gap.

**4. Jia et al. — "DiracDec" (arXiv 2307.05492, if indexed)**  
If this arXiv ID resolves correctly, it is the most directly relevant paper — a decision
procedure operating in Dirac notation. Read it before writing any TRS rules to avoid
reinventing their normal-form theorem.

**5. Kissinger & van de Wetering — "PyZX: Large Scale Automated Diagrammatic Reasoning" (arXiv 1904.04735)**  
The implementation paper for PyZX. Read before writing the ZX bridge in Phase 3; the
API and data structures documented here save hours of reverse-engineering the library.

---

## Architectural Risks and Mitigations

**Risk: SymPy `simplify` is slow and non-deterministic on complex expressions.**  
Mitigation: Never call raw `simplify`; always use the targeted functions (`trigsimp`,
`expand`, `factor`, `groebner`). Set a 2-second timeout on any SymPy call; fall back to
numeric evaluation if exceeded.

**Risk: TRS diverges on some expressions (no fixed point).**  
Mitigation: Apply rules with a step counter; cap at 200 steps; return best-so-far with
a `converged: false` flag. Log divergent cases for rule set refinement.

**Risk: ZX bridge adds a dependency that breaks on PyZX API changes.**  
Mitigation: Isolate the bridge behind a single `effect_parser` → ZX translation function;
pin PyZX version in requirements.

**Risk: LLM generates syntactically invalid Dirac expressions.**  
Mitigation: The parser should be lenient (attempt to recover) and return a structured
parse error with the failing token, not a raw exception. The LLM can correct its output
much better with a structured parse error than a Python traceback.

---

## KB Delta

Batch indexing in progress at report time. The following papers were submitted:

- `2012.13966` — van de Wetering ZX primer (Thread B)
- `1904.04735` — PyZX paper (Thread B)
- `0906.4725` — Coecke/Kissinger categorical QM (already indexed, no-op)
- `2004.03082` — egg / equality saturation (Thread D)
- `2204.09033` — Quartz quantum superoptimizer (Thread D)
- `2012.01600` — VOQC / verified compiler candidate (Thread C)
- `2307.05492` — DiracDec candidate (Thread A)
- `2401.08922` — Jia et al. 2024 candidate (Thread A)
- `2212.09706` — Additional Thread A candidate

Run `kb_status` after indexing completes to confirm final drawer count delta.

**Threads with no KB coverage (future work):**
- Thread F (LLM theorem proving / proof repair): No papers indexed. Key papers to add in
  a follow-up batch: Llemma (2306.15626), Thor (2205.12615), LEGO-Prover (2310.00656).
