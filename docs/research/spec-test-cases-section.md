# Spec: Declarative `## test_cases` Section

**Status:** Draft
**Date:** 2026-05-15
**Priority:** High

> Generated: 2026-05-15 — weekly feature spec session

---

## Summary

Add a top-level `## test_cases` section to `.q.orca.md` files
that embeds concrete input → expected-output scenarios as
declarative table rows. A new Stage 5 verifier rule
`behavioral_test_cases` runs each row against the Stage 4b
backend, checks the measured statistics against the declared
expectation (with a Wilson-score confidence bound), and reports
pass / fail through the existing `verify_skill` diagnostics
surface. The section turns every shipped example into a
self-checking specification: today the `examples/*.q.orca.md`
files only have to *parse* and *verify structurally* to land on
main; in practice, they were also expected to produce the
quantum behavior described in the surrounding prose, but no
automated check pinned that. The result was the bit-flip
syndrome bug
(`extend-conditional-gate-compound-bits`, in-flight) shipping
silently for two months because the example "verified valid"
without anyone running it through the simulator and asserting
the expected logical-state output. Test cases close that
window: the moment an example claims an output, the verifier
runs it.

This is the **endpoint-checking** complement to the **midpoint-
checking** assertions in the in-flight
`add-runtime-state-assertions` proposal. The two are orthogonal
in scope (assertions probe intermediate states; test cases
check input → output behavior), backend (assertions need a
specific simulator stage; test cases reuse Stage 4b), and
failure semantics (assertion failure halts a single execution;
test-case failure is a verifier-level diagnostic).

---

## Motivation

**The user problem.** A `.q.orca.md` file today is a
specification of a state machine, not of its observable
behavior. Stage 1–4 verify that the machine is *well-formed*
(parse, structural unitarity, no-cloning, reachability,
feedforward completeness, resource budgets); Stage 4b can
*simulate* it but only the human reading the prose decides
whether the simulator output matches what the example was
supposed to demonstrate. There is no place in the file to
write down "after running on initial state `|01>`, the
measured outcome should be `10` with probability ≥ 99%."

The recent history of the repo is a parade of bugs that this
gap let through:

- `extend-conditional-gate-compound-bits` (in-flight) is
  fixing a 25%-of-syndromes silent-X bug in
  `bit-flip-syndrome.q.orca.md` that survived two months
  because the example "verified valid".
- Commit `c2d8eb9` ("teleportation correction gates target
  Bob's qubit (qs[2] not qs[0])") caught a published-example
  bug where the Pauli corrections in
  `quantum-teleportation.q.orca.md` were being applied to
  Alice's qubit instead of Bob's. Pure prose described the
  protocol correctly; the gate sequence didn't implement the
  prose; nothing checked.
- `tech-debt-backlog §5.4` ("fill test coverage gaps for
  shipped examples") explicitly names "every shipped example
  needs at least one behavioral assertion" as outstanding
  work. PR #63 added some by writing dedicated Python test
  files in `tests/`; that approach scales as `O(examples ×
  test-files)` and divorces the test scenarios from the
  example file they describe.

**The current workaround.** Authors write a separate Python
test file (e.g., `tests/test_bell_entangler.py`) that loads
the example, runs the simulator, and asserts on the result
distribution. This works but has three structural problems:

1. The test scenario lives in a different file from the
   example, so reading the example does not show the user
   what it is supposed to do.
2. Adding a new example requires authoring two files and
   wiring the test into pytest — a friction point that PR #63
   triaged six examples at once because it had built up.
3. The test file uses the Python simulator API directly,
   bypassing the language. A future backend change (e.g., the
   drafted `spec-stabilizer-fast-path-backend.md`) has to
   teach every Python test to choose the right backend; a
   declarative section in the markdown would let the verifier
   pick the backend automatically.

**Why now.** Three forces converge in this release window:

- The recently-merged `add-resource-estimation` work shipped a
  similar pattern — a markdown section (`## resources`,
  `## resource invariants`) that the verifier evaluates as a
  Stage 4c rule. That established the precedent for "the
  markdown declares an expectation; the verifier runs it." Test
  cases follow the same shape one stage later.
- The in-flight `add-runtime-state-assertions` proposal
  introduces statistical testing infrastructure (Wilson-score
  bounds, configurable `shots_per_assert`) that test cases
  can reuse verbatim. Landing both proposals against the same
  underlying sampling helper avoids two implementations of
  the same statistics.
- Stage 4b already runs the Qiskit simulator on every
  `verify_skill` invocation; adding a behavioral check is a
  ~50-line hook into the existing pipeline plus the grammar.

**KB grounding.** The formal-methods survey
[`2109.06493` §8.4 (`Formal methods for quantum algorithms`)]
explicitly notes that "instead of mathematical proofs, these
assertions are probed by statistical testing over program
fragments. The challenges faced by such [methods] are…"
naming the Huang–Martonosi (ISCA 2019) statistical-testing
approach as the right tool when destructive measurement and
non-determinism rule out QHL-style projection assertions. The
deductive verification framework in
[`2003.05841` (Voichick et al.)] notes that ZX-calculus and
QHL-style proofs cannot handle parametric or stochastic
endpoints, leaving statistical testing as the practical
fallback for the input → output check this proposal targets.
The `symQV` paper
[`2212.02267`] models exactly this surface — branching
execution paths each weighted by probability — and argues
that input-output assertions are the unit of behavioral
testing for non-trivial circuits.

---

## Proposed Syntax / API

### `## test_cases` section

A new optional top-level section, recognised after `## machine`
blocks (or after the per-machine `## resources` /
`## resource invariants` sections in multi-machine files):

```markdown
## test_cases

| Case          | Inputs                | Expect              | Tolerance     |
|---------------|-----------------------|---------------------|---------------|
| basic         | qs=|00>               | bits ∈ {00, 11}     | p_each ≥ 0.45 |
| flipped       | qs=|01>               | bits ∈ {01, 10}     | p_each ≥ 0.45 |
| superposition | qs=|+0>               | bits ∈ {00, 01, 10, 11} | p_total ≥ 0.99 |
```

Column semantics:

- **Case** — case identifier; must be unique within the file.
  Used in diagnostic messages.
- **Inputs** — comma-separated `<context_field>=<value>`
  bindings. The qubit register accepts Dirac kets (`|01>`,
  `|+>`, `|GHZ>`) drawn from a small recognised vocabulary.
  Classical context fields use literal values
  (`theta=π/4, n_iter=3`).
- **Expect** — one of:
  - `bits ∈ {<set>}` — measurement-basis outcome must lie in
    the set. Combined with a Tolerance giving per-outcome or
    summed probability bounds.
  - `bits = <value> with p ≥ <bound>` — single deterministic
    outcome with confidence bound.
  - `expectation(<observable>) ≈ <value> ± <eps>` — sampled
    expectation value within `eps` of target. `<observable>`
    is one of the `## resources`-style observable names
    (`Z(qs[0])`, `ZZ(qs[0..1])`, `H_xxx`).
  - `state_vector ≈ |φ⟩ with fidelity ≥ <bound>` — full state
    fidelity check. Available only when no measurement is on
    the path (verifier rejects with
    `STATE_VECTOR_AFTER_MEASURE` otherwise).
- **Tolerance** — Wilson-score confidence bounds on the
  measured statistics. Defaults to `confidence=0.99,
  shots=1024` taken from a per-machine `## test policy`
  section if present, else from compile-time defaults.

### `## test policy` (optional)

```markdown
## test policy

| Field         | Value     |
|---------------|-----------|
| shots         | 4096      |
| confidence    | 0.999     |
| backend       | qiskit    |
| on_failure    | error     |
| seed          | 0xC0FFEE  |
```

Mirrors `## assertion policy` from
`add-runtime-state-assertions`. `seed` makes failures
reproducible.

### CLI

`q-orca verify ./bell-entangler.q.orca.md` runs the test
section by default. New flags:

- `--no-test-cases` — skip Stage 5 behavioral checks (useful
  for fast feedback during edit cycles).
- `--only-test-case <name>` — run a single named case.
- `--update-tolerances` — DO NOT auto-fit tolerances. Instead,
  emit a *suggested* tolerance row to stdout based on observed
  statistics; never write to the file.

A new diagnostic surface `verify_skill --json` includes a
`test_cases: list[{case: str, status: 'pass' | 'fail' |
'inconclusive', p_observed: float, …}]` field for tooling
consumption.

---

## Implementation Sketch

**Parser** — `q_orca/parser/markdown_parser.py`:

- Recognise `## test_cases` and `## test policy` headings, parse
  the pipe-delimited tables. New AST nodes `QTestCase(name,
  inputs, expect, tolerance)` and `QTestPolicy(...)` on
  `QMachineDef`.
- Dirac-ket parser — small grammar covering `|0⟩, |1⟩, |+⟩,
  |−⟩, |i⟩, |−i⟩, |GHZ_n⟩, |W_n⟩, |Bell_xy⟩` (xy ∈ Φ+, Φ−,
  Ψ+, Ψ−). Larger states supported via direct amplitude
  arrays as a fallback. ~180 LOC plus tests. The Dirac-ket
  parser shares its symbol table with the `dirac-rewriter-
  synthesis.md` research note's lexer where the parser already
  has a partial implementation.
- Expectation predicate parser — small recursive-descent on the
  three expect-shape grammars above. ~80 LOC.

**Verifier** — new module `q_orca/verifier/behavioral.py`:

- `check_test_cases(machine, backend) -> list[TestCaseResult]`.
  For each case:
  1. Build the input-state preparation circuit (Dirac ket → gate
     sequence using the existing `q_orca/compiler/state_prep.py`
     helper if present, else a thin new helper).
  2. Compose with the machine's compiled circuit.
  3. Run `tolerance.shots` shots on the configured backend.
  4. Evaluate the Expect predicate against the histogram /
     density matrix.
  5. Produce a structured `TestCaseResult` carrying observed
     vs. expected values and the Wilson-score bound.
- Statistical helpers (`wilson_lower_bound`,
  `binomial_two_sided_ci`) live in a new
  `q_orca/verifier/_statistics.py` module shared with
  `add-runtime-state-assertions` (which lifts them out of its
  own module if it lands first).
- ~250 LOC plus tests.

**Pipeline integration** —
`q_orca/verifier/__init__.py`:

- Stage 5 gains a new `behavioral_test_cases` rule, registered
  next to the existing rules. Wired into `verify_skill`.
- New diagnostic codes: `TEST_CASE_FAILED`,
  `TEST_CASE_INCONCLUSIVE` (CI bound straddles target),
  `TEST_CASE_BACKEND_MISSING`, `TEST_CASE_INPUT_PARSE_FAILED`,
  `STATE_VECTOR_AFTER_MEASURE`.
- ~40 LOC plus wire-up tests.

**Compiler** — no compiler changes required. Test cases never
emit gates into the user's circuit; they only run alongside it
during verification.

**Examples** — every shipped `examples/*.q.orca.md` gets at
least two test cases as part of the rollout PR. The bit-flip
syndrome example gets four (one per syndrome pattern), which
would have caught the silent-X bug the in-flight
`extend-conditional-gate-compound-bits` change is fixing.

**Specs** — `openspec/specs/language/spec.md`,
`openspec/specs/verifier/spec.md` get delta sections.

**Total estimate:** ~550 LOC of code + ~600 LOC of tests +
~120 LOC of new test-case rows in shipped examples.

---

## Test Cases

(Test cases for the test-cases feature itself.)

1. **Bell entangler — happy path**:
   `qs=|00>` → `bits ∈ {00, 11}` with `p_each ≥ 0.45` passes
   on the Bell-entangler example with `shots=4096`.

2. **Bell entangler — wrong tolerance**: same inputs, but
   `Tolerance: p_each ≥ 0.49` deliberately exceeds the
   theoretical 0.5 bound; verifier reports
   `TEST_CASE_INCONCLUSIVE` (the Wilson-score lower bound
   straddles the target) rather than a false positive
   `TEST_CASE_FAILED`.

3. **Bit-flip syndrome regression**: insert the four-syndrome
   test cases from the planned example update; verify that
   the *current* (pre-`extend-conditional-gate-compound-bits`)
   example fails on syndrome `(1,1)` with the expected logical-
   X smoking gun. Confirms the section would have caught the
   shipped bug.

4. **State-fidelity check across measurement boundary**:
   declaring `state_vector ≈ |Φ+⟩ with fidelity ≥ 0.99` on a
   path that contains a mid-circuit measurement raises
   `STATE_VECTOR_AFTER_MEASURE` at parse time, not at run
   time.

5. **Reproducibility under seed**: the same case run twice
   with the same `seed` in `## test policy` produces the same
   measurement histogram bit-for-bit.

6. **Multi-machine routing**: when a file has more than one
   `## machine` block (post-`add-parameterized-invoke`), each
   `## test_cases` row may name a `machine: <name>` column to
   target a specific child; default is the file's root
   machine.

---

## Dependencies

**Composes with `add-runtime-state-assertions` (in-flight)** —
both proposals share the Wilson-score statistics helper. If
`add-runtime-state-assertions` lands first, this proposal
imports `q_orca/verifier/_statistics.py` from there; if this
proposal lands first, it ships the helper and the assertions
work imports it.

**Composes with `extend-conditional-gate-compound-bits`
(in-flight)** — the bit-flip syndrome example update is the
canonical demo case for the section. The two changes can land
in either order; landing
`extend-conditional-gate-compound-bits` first means the
example's test cases all pass on first introduction, which is
the cleaner story.

**Composes with the merged `add-resource-estimation`** —
both proposals follow the "declarative section evaluated as a
verifier stage" pattern. Stage 5 is the natural slot for
behavioral checks (one stage after Stage 4c's resource budget
check).

**Independent of `add-parameterized-invoke`** — single-machine
test cases work regardless of multi-machine composition.
Multi-machine routing (test 6 above) layers on top once
`add-parameterized-invoke` lands.

**Sequencing recommendation:** ship
`add-runtime-state-assertions` first (it lifts the statistics
helper into a clean shared module), then this proposal. The
reverse order works but produces an awkward "extract from
behavioral.py into _statistics.py" follow-up commit.

---

## Open Questions

1. **Dirac-ket vocabulary scope.** The proposed parser
   recognises a fixed list of named states (`|GHZ_n⟩, |W_n⟩,
   |Bell_xy⟩`). A richer surface (parameterised
   superpositions, tensor-product expressions like `|0⟩ ⊗ |+⟩`)
   would compose better with the in-flight
   `dirac-rewriter-synthesis` research. Worth scoping
   together?

2. **`shots` budget on CI.** Default `shots=1024` per case
   times ~30 cases across the example library is ~30k
   simulator shots per `verify_skill --all-examples` run.
   Acceptable on the current example library; will need a
   sampled-subset mode if the library grows past ~100
   examples. Probably future work.

3. **Backend selection.** Some test cases (e.g.,
   `state_vector ≈ |φ⟩ with fidelity ≥ …`) need a statevector
   backend; some (`bits ∈ {…}`) need a sampling backend. The
   verifier should pick automatically per-case, but the
   `## test policy` `backend` field overrides. Is that
   precedence right?

4. **Tolerance ergonomics.** The Wilson-score CI is correct
   but unfamiliar to most users. The `--update-tolerances`
   flag prints a *suggested* row, but should the spec
   recommend authors paste the suggestion verbatim, or write
   tighter bounds (and accept occasional flakes)? Worth a
   short worked example in the rollout docs.

5. **Cross-test invariants.** Should the section support a
   row of "for ALL `theta ∈ [0, 2π)` sampled at N points,
   `expectation(Z(qs[0])) ≈ cos(theta) ± 0.05`"? That's a
   property-based testing surface; useful but a meaningful
   scope expansion. Probably v2.
