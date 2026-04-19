# Feature: Runtime State-Category Assertions

> Generated: 2026-04-17 — weekly feature spec session

---

**Summary:** Add runtime-checked assertions to q-orca that let a machine author annotate any state with an expected *category* of quantum-register configuration — `classical`, `superposition`, or `entangled(qs[i], qs[j])` — and have that claim validated by repeated statistical sampling on a simulator. This is the Huang–Martonosi–style "coarse-grained" assertion approach, which trades the expressiveness of QHL-style full-projection assertions for a verification method that works around destructive measurement and non-determinism. The feature closes the loop between q-orca's existing static verifier (which checks unitarity, coherence, and reachability) and the actual quantum-state behaviour of a compiled circuit by giving the user a way to say "here, at state |ψ⟩, the register `qs[0]` should be in a superposition, and `qs[0]–qs[1]` should be entangled" and to have that assertion mechanically verified by the Stage 4b QuTiP / cuQuantum backend.

---

**Motivation:** The algorithms and use cases this unlocks include:

- **Debug workflow for new users** — there is currently no way to assert at a midpoint of a machine that "by this state, I expect entanglement between q0 and q1". Users debug by reading out full state vectors and eyeballing them. A `[assert: entangled(qs[0], qs[1])]` annotation converts this into a machine-checked property.
- **Error-correction syndrome sanity** — the `bit-flip-syndrome.q.orca.md` example depends on the syndrome qubits being correctly entangled with the data qubits after the stabilizer round. A state-category assertion catches silent wiring bugs (wrong CNOT targets) that produce a well-typed but semantically wrong circuit.
- **Regression pinning for variational algorithms** — VQE / QAOA circuits can have their ansatz state categories pinned at each layer (`|uniform>` is expected to be in superposition; `|cost_applied>` is expected to remain in superposition but entangled). Assertion failures surface parameter-coordinate bugs that static verification misses.
- **Fragmented-execution debugging** — because assertion sampling is destructive, the assertion checker automatically re-runs the circuit prefix N times to build a statistical distribution. This gives q-orca users a deterministic pass/fail signal (with configurable confidence) even on non-deterministic quantum output — exactly the pattern recommended in the formal-methods survey (`2109.06493`).
- **Complements existing invariants** — the current `## invariants` table already supports `entanglement(q0, q1) = True` and `schmidt_rank(q0, q1) >= 2` at the *machine* level (i.e. at the final state). This spec promotes the same vocabulary to be checkable at any *named state*, not just the terminal one, turning invariants into localizable assertions.

---

**Proposed Syntax:**

```markdown
# machine BitFlipSyndromeAssert

## context

| Field  | Type        | Default                      |
|--------|-------------|------------------------------|
| qubits | list<qubit> | [d0, d1, d2, s0, s1]         |
| bits   | list<bit>   | [b0, b1]                     |

## events
- encode
- stabilize
- readout

## state |raw> [initial]
> All qubits in |00000⟩

## state |encoded> [assert: superposition(qs[0..2]); entangled(qs[0], qs[1]); entangled(qs[1], qs[2])]
> Three data qubits encode a logical |+⟩ across the bit-flip code

## state |stabilizer_round>
  [assert: entangled(qs[0], qs[3]); entangled(qs[2], qs[4]); superposition(qs[3..4])]
> Syndrome qubits coupled to data; parities mapped into s0, s1

## state |measured> [final, assert: classical(qs[3..4])]
> Syndrome qubits collapsed; data still in superposition

## transitions

| Source             | Event       | Guard | Target              | Action           |
|--------------------|-------------|-------|---------------------|------------------|
| |raw>              | encode      |       | |encoded>           | encode_code      |
| |encoded>          | stabilize   |       | |stabilizer_round>  | stabilize_round  |
| |stabilizer_round> | readout     |       | |measured>          | measure_syn      |

## actions

| Name            | Signature   | Effect                                                                     |
|-----------------|-------------|----------------------------------------------------------------------------|
| encode_code     | (qs) -> qs  | Hadamard(qs[0]); CNOT(qs[0], qs[1]); CNOT(qs[0], qs[2])                    |
| stabilize_round | (qs) -> qs  | CNOT(qs[0], qs[3]); CNOT(qs[1], qs[3]); CNOT(qs[1], qs[4]); CNOT(qs[2], qs[4]) |
| measure_syn     | (qs) -> qs  | measure(qs[3]) -> bits[0]; measure(qs[4]) -> bits[1]                        |

## assertion policy

| Setting           | Value  | Notes                                                          |
|-------------------|--------|----------------------------------------------------------------|
| shots_per_assert  | 512    | Statistical sample size per assertion                          |
| confidence        | 0.99   | Required confidence that category claim holds                  |
| on_failure        | error  | `error` fails verification; `warn` downgrades to warning       |
| backend           | auto   | `auto` → QuTiP; overridden by `--backend cuquantum`            |
```

**Assertion vocabulary** (evaluable on a register slice `qs[a..b]` or a single `qs[k]`):

| Category                        | Predicate                                                         | Sampled via                                                                 |
|---------------------------------|-------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `classical(qs[k])`              | Measuring in Z basis yields one outcome with probability ≥ confidence | Z-basis sampling                                                            |
| `classical(qs[a..b])`           | Joint Z-basis outcome is deterministic                            | Z-basis joint sampling                                                      |
| `superposition(qs[k])`          | Z-basis sampling yields both outcomes non-trivially               | Z-basis sampling + binomial bounds                                          |
| `superposition(qs[a..b])`       | Some qubit in the slice is in superposition                       | Marginal Z-basis check on each qubit                                        |
| `entangled(qs[i], qs[j])`       | Subsystem (i,j) is not separable                                  | Reduced density matrix purity `Tr(ρ²) < 1 − ε` or sampled concurrence       |
| `separable(qs[i], qs[j])`       | Subsystem is separable                                            | Reduced density matrix purity `Tr(ρ²) ≥ 1 − ε`                             |

Assertions compose with `;` inside a single `[assert: …]` annotation. Multiple annotations on the same state are conjunctive. Assertions inside `[…]` state annotations share the `[loop …]` / `[final]` annotation syntax already used by the queued loop and protocol-state features, so there is no new outer-syntax design.

---

**Implementation Sketch:**

**Parser changes (`q_orca/parser/`):**
- Extend `parse_state_header()` to recognize `assert:` as a new annotation kind alongside `initial`, `final`, and the queued `loop`, `send`, `receive`. The parser collects the payload (one-or-more semicolon-separated category expressions) into `QState.assertions: list[QAssertion]`.
- New AST node `QAssertion` with fields `category: Literal['classical','superposition','entangled','separable']`, `targets: list[QubitSlice]`, `source_span: Span`.
- Reuse the existing `QubitSlice` AST that handles `qs[k]` and `qs[a..b]` references in the invariants grammar.
- New `## assertion policy` section parser — a one-column table of settings with typed values. Stored as `QMachine.assertion_policy: AssertionPolicy` with sensible defaults (`shots=512`, `confidence=0.99`, `on_failure='error'`).

**Compiler changes:**
- **Qiskit:** no changes to the emitted circuit. Assertions are not gates; they are out-of-band checks driven by the verifier. The Qiskit compiler's existing state-label metadata (each named state has a point in the gate sequence) is extended with an `assertion_probe: list[QAssertion]` field so the Stage 4b backend knows where to snapshot state vectors.
- **QASM:** same — assertions emit a comment line `// assert: superposition(q[0..2]) @ state encoded` in the QASM output but no instruction. This keeps the QASM output fully compatible with all external tools.
- **New module** `q_orca/verifier/assertions.py` implementing `check_state_assertions(machine, backend)`:
  1. For each state with assertions, build the circuit prefix up to the probe point.
  2. Run `shots_per_assert` samples on the chosen backend.
  3. Evaluate each `QAssertion`'s predicate against the sample distribution (Z-basis counts for `classical` / `superposition`; reduced density matrix purity via partial trace for `entangled` / `separable`).
  4. Compute a confidence bound using Wilson score interval or analogous; fail if the bound doesn't clear the `confidence` threshold.
  5. Emit one verifier diagnostic per assertion: `ASSERTION_PASSED`, `ASSERTION_FAILED`, or `ASSERTION_INCONCLUSIVE` (when `shots_per_assert` is too small for the requested confidence).

**Verifier changes:**
- Activates under a new verification rule name `state_assertions` in `## verification rules`.
- New diagnostic codes: `ASSERTION_FAILED`, `ASSERTION_INCONCLUSIVE`, `ASSERTION_BACKEND_MISSING` (when the backend can't support the check, e.g. QuTiP is not installed).
- Tied into the existing Stage 4b backend dispatcher — reuses `q_orca.backends.qutip` and `q_orca.backends.cuquantum` defined in the execution-backends spec.
- The `superposition_leak` check already computes coherence; `check_state_assertions` reuses the same coherence-tracking machinery where possible to avoid duplicate simulation passes.

**New tests / examples needed:**
- `tests/test_state_assertions.py` — one test per category (classical, superposition, entangled, separable), plus a test that a false assertion fails with the expected diagnostic, a test that an inconclusive assertion fires `ASSERTION_INCONCLUSIVE` when `shots=16`, and a test that the backend-missing path emits `ASSERTION_BACKEND_MISSING` gracefully.
- `tests/test_parser.py` — parse-only tests for the `[assert: …]` annotation forms and the `## assertion policy` section.
- New example `examples/bell-entangler-asserts.q.orca.md` — the existing Bell pair annotated with `[assert: superposition(qs[0])]` on the Hadamard state and `[assert: entangled(qs[0], qs[1])]` on the post-CNOT state. Ships with `shots_per_assert=256` for fast CI.
- Updated example `examples/bit-flip-syndrome.q.orca.md` — add `[assert: entangled(qs[0], qs[1])]` etc. at the encoded state to demonstrate real debugging value.
- New doc `docs/language/assertions.md` explaining the full vocabulary, statistical semantics, and the destructive-measurement caveat (assertions require re-running the circuit prefix; they are a *debug-time* cost, not a runtime cost of the compiled circuit on real hardware).

**Edge cases:**
- Assertions on states *after* a mid-circuit measurement need the circuit replay to honour the measurement outcome. The Stage 4b backend's existing `measure` handling already does this; the assertion probe just hooks into the same post-measurement state snapshot.
- `superposition(qs[a..b])` is defined as "some qubit in the slice is in superposition", not "every qubit" — because "every qubit is in superposition" is often false for GHZ-like states (individual marginals are mixed, not in superposition). Document this subtlety.
- Parameterized angles: assertions evaluate against the default parameter values. A later extension can parameterize assertions themselves.
- Assertion evaluation is skipped silently when running in a non-simulation compile target (e.g. raw QASM export to a real device); a single informational diagnostic `ASSERTIONS_SKIPPED_NO_SIMULATOR` is emitted instead.

---

**Complexity:** Medium. The parser extension and new AST node are ~100 LOC. The `assertions.py` module (simulation harness + category predicates + statistical thresholds) is ~300 LOC, of which the reduced-density-matrix partial trace is the main new piece (~60 LOC, reusable from any existing QuTiP tutorial). New tests are ~350 LOC. No new hard dependencies — QuTiP is already an optional dependency for Stage 4b, and NumPy / SciPy (already in the dependency tree) supply the statistical bounds.

**Priority:** High. Debugging and testing are the single most-cited pain points of quantum program development in the formal-methods survey (`2109.06493`, §8.4). q-orca's current verifier is strong on static structural checks but silent on "is the quantum state at this midpoint what I think it is?" — this spec adds exactly that capability with a lightweight, industry-proven (Huang & Martonosi 2019 in ISCA) statistical method.

**Dependencies:** None hard. Composes with:
- Execution backends spec (spec-execution-backends.md) — reuses the QuTiP / cuQuantum backend dispatch.
- Mid-circuit measurement (already shipped in 0.4.0) — supplies the mid-circuit state-snapshot hook.
- Extended invariant expressions (queued) — per-state assertions generalize what invariants already do at the machine level.
- Qubit role types (queued) — once `role: syndrome` exists, `classical(syndrome[0..n])` can be implicitly asserted at the post-measurement state without the user typing it.

**Literature:**
- Pérez-Delgado & Pérez-Delgado *et al.*, *Formal Methods for Quantum Algorithms*, `2109.06493.pdf` (q-orca-kb, `formal-methods`) — §8.4 "Runtime assertion checking" is the direct reference. Summarises Huang & Martonosi's three-category annotation language (classical / superposition / entangled) and the destructive-measurement / non-determinism challenges that make statistical sampling the right tool.
- Huang & Martonosi, *"Statistical Assertions for Validating Patterns and Finding Bugs in Quantum Programs"* (ISCA 2019) — the original paper behind the three-category approach. (Referenced by 2109.06493 §8.4, not indexed as a standalone PDF.)
- Li et al., *"Proq: Projection-based Runtime Assertions for Testing and Debugging Quantum Programs"* (2023) — QHL-projection assertions; the more expressive alternative that this spec deliberately defers.
- Fang, Tsai, Havlíček et al., *AutoQ 2.0*, `2411.09121.pdf` (q-orca-kb, `formal-methods`) — automated verification of repeat-until-success and weak-measurement Grover up to 100 qubits; an existence proof that the statistical approach scales.
- Kissinger, van de Wetering — reduced-density-matrix purity bounds as the canonical separable/entangled criterion.

---
