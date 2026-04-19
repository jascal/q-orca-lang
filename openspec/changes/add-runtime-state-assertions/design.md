## Context

Q-Orca's verifier today is split across two stages: Stage 4 runs purely
structural checks (unitarity of the gate set, no-cloning, completeness,
reachability) on the AST without ever touching a quantum-state vector;
Stage 4b is an opt-in numeric stage that re-simulates the compiled circuit
on QuTiP (or, when present, cuQuantum) and evaluates machine-level
invariants like `entanglement(q0, q1) = True` against the *final*
state. Authors who want to know whether their **mid-circuit** state is what
they think it is have no surface for asking — they have to drop out of
Q-Orca and read state vectors by hand. This is the gap the spec at
`docs/specs/spec-runtime-assertions.md` proposes to close.

The shape of the solution is settled by two prior choices in the codebase:

1. **The state heading is the right anchor.** Every named `## state`
   already corresponds to an identifiable point in the compiled gate
   sequence (the Qiskit compiler emits a state-label snapshot at exactly
   these points). Adding a `[assert: …]` annotation to the heading is
   syntactically free — it slots in alongside `[initial]`, `[final]`,
   `[loop …]` (queued), and `[send]` / `[receive]` (queued).

2. **Stage 4b is the right verifier hook.** The dispatcher in
   `q_orca/verifier/dynamic.py` already knows how to materialize a numeric
   simulation and reduce its output to invariant pass/fail diagnostics.
   The same machinery extended to "snapshot at state X, evaluate this
   predicate, repeat N times for statistical confidence" is the
   `check_state_assertions` module proposed below.

The literature anchor is Huang & Martonosi (ISCA 2019), which the
formal-methods survey (`2109.06493`, indexed in q-orca-kb) calls out as
the canonical statistical-assertion approach, defensible against
destructive measurement and quantum non-determinism. Proq (2023) is the
QHL-projection alternative we deliberately defer.

## Goals / Non-Goals

**Goals:**

- Let an author annotate any named `## state` with an expected category of
  quantum register configuration: `classical`, `superposition`,
  `entangled(qs[i], qs[j])`, or `separable(qs[i], qs[j])`.
- Mechanically validate those claims at verify time using statistical
  sampling on the Stage 4b backend, with a configurable confidence
  threshold and shot count.
- Surface assertion failures as first-class verifier diagnostics
  (`ASSERTION_FAILED`, `ASSERTION_INCONCLUSIVE`,
  `ASSERTION_BACKEND_MISSING`) consistent with existing diagnostic codes.
- Compose cleanly with mid-circuit measurement (already shipped) and the
  existing execution-backends spec.
- Keep the QASM and Qiskit emitted artifacts free of any new
  *instructions* — assertions are out-of-band metadata, not gates.

**Non-Goals:**

- QHL-projection assertions. Proq-style projection assertions are more
  expressive but require a full Hilbert-space projector formalism and
  cannot share Stage 4b's existing sampling harness. Defer.
- Parameterized assertions. Assertions evaluate against the default
  parameter values for now; a later extension can let users sweep
  assertion parameters alongside gate parameters.
- Real-device assertion checking. Assertions on a hardware target are
  silently skipped with a single informational diagnostic; we do not try
  to replay-and-sample on a real QPU.
- New simulator backend. Assertion sampling reuses the QuTiP /
  cuQuantum dispatch already shipped with execution-backends — no new
  hard dependencies.

## Decisions

### Decision 1: Reuse the existing state-annotation grammar rather than introducing a new section

The annotation `[assert: …]` lives on the `## state` heading itself,
sharing the bracketed annotation slot with `[initial]`, `[final]`, the
queued `[loop …]`, and the queued protocol-state annotations
`[send: q -> Bob]` / `[receive]`. Multiple bracketed annotations on the
same heading are conjunctive. Inside `[assert: …]`, multiple category
expressions are separated by `;`.

**Why:** The state heading is the only AST node that uniquely identifies
a probe point in the compiled gate sequence. Putting assertions there
makes the locality immediate — the author and the verifier agree on
which state is being claimed about — and avoids a second
"name-the-state-twice" syntax. It also keeps the file-level structure
(headings + tables + bullet lists) unchanged, which the parser-rule
priority work in PR #11 has already invested in.

**Alternatives considered:**

- A new top-level `## assertions` table keyed by state name. Rejected
  because it forces the author to name each asserted state twice (in
  `## state` and again in the table) and because it puts the locality
  one level of indirection away from the place the author is actually
  reasoning about the circuit.
- Inline assertion bullets in the body of the state's blockquote (e.g.
  `> assert: superposition(qs[0])` inside the `> …` description).
  Rejected because the blockquote is currently free-text descriptive
  prose; making it semantically significant breaks the existing parser
  contract that everything outside recognized headings/tables is
  ignored.

### Decision 2: Statistical sampling, not symbolic projection

Each assertion is evaluated by replaying the circuit prefix to the
annotated state, then drawing `shots_per_assert` Z-basis samples (for
`classical` / `superposition`) or extracting the reduced density matrix
via partial trace (for `entangled` / `separable`) and applying a Wilson
score interval against the configured `confidence` threshold.

**Why:** Sampling is the only approach that survives destructive
measurement and the inherently non-deterministic measurement output of a
real circuit. It is also the approach validated as practical at scale by
Fang & Tsai et al. (`2411.09121`, AutoQ 2.0, up to 100 qubits) and
recommended as the default in the formal-methods survey §8.4.

**Alternatives considered:**

- QHL projection assertions (Proq, 2023). More expressive — a projection
  assertion can specify a continuous family of states — but they require
  a full Hilbert-space projector and a different verifier harness. The
  spec deliberately defers this to a follow-up change, so that the
  Huang–Martonosi vocabulary can ship first and earn its keep.
- Exact density-matrix comparison. Possible at small qubit counts but
  blows up exponentially and gives the user no obvious knob to trade
  precision against verifier runtime. The shot-count + confidence pair
  is a more honest knob.

### Decision 3: One module, four predicates, shared partial-trace primitive

`q_orca/verifier/assertions.py` exposes a single entry point
`check_state_assertions(machine, backend) -> list[Diagnostic]`. Internally
it dispatches on `QAssertion.category`:

- `classical(qs[…])` → Z-basis joint sample, check that one outcome
  carries probability ≥ `confidence`.
- `superposition(qs[…])` → marginal Z-basis sample per qubit in the
  slice, check that *some* qubit in the slice has both outcomes appearing
  non-trivially under a binomial bound at `confidence`.
- `entangled(qs[i], qs[j])` → reduced density matrix on `(i, j)` via
  partial trace, check `Tr(ρ²) < 1 − ε` (Kissinger–van de Wetering
  separability bound).
- `separable(qs[i], qs[j])` → same partial trace, check
  `Tr(ρ²) ≥ 1 − ε`.

The partial-trace primitive is ~60 LOC of NumPy and is reusable from any
QuTiP tutorial; we explicitly do NOT call into QuTiP's `ptrace` to keep
the predicate evaluation backend-agnostic (the same predicate runs
against a cuQuantum-produced state vector unmodified).

**Why:** Keeping the predicates in one module means each new category
added later (e.g. `bell_pair(qs[i], qs[j])`, `magic_state(qs[i])`) is a
single function with a single test fixture rather than a new module.

### Decision 4: `superposition(qs[a..b])` means "some qubit in the slice", not "every qubit"

A GHZ state has every qubit in a maximally mixed marginal, so "every qubit
is in superposition" would be false in the case the author most plausibly
wanted to assert. The "some qubit" reading matches the debug intent and
is the formulation Huang & Martonosi adopted.

**Why:** The user-debug case ("did my superposition propagate at least
this far?") is the one we expect to dominate. The stricter
"every-qubit-superposed" claim is rare in practice and can be expressed
explicitly as a conjunction: `superposition(qs[0]); superposition(qs[1]);
superposition(qs[2])`.

This subtlety MUST be documented in `docs/language/assertions.md`.

### Decision 5: `## assertion policy` is a separate optional section, not an inline annotation

Per-machine policy (shot count, confidence, on-failure behavior, backend
override) lives in a small `## assertion policy` table near the bottom
of the machine, parsed into `QMachine.assertion_policy: AssertionPolicy`.
Absent section → defaults (`shots=512`, `confidence=0.99`,
`on_failure='error'`, `backend='auto'`).

**Why:** Putting policy on individual `[assert: …]` annotations would
force the author to repeat `shots=512, confidence=0.99` on every state.
A machine-wide policy with a small surface area is the right granularity
for the debug workflow this targets.

**Alternative considered:** Inline `[assert: …, shots=128]`
syntax. Rejected as noisy and as encouraging copy-paste drift across
states.

### Decision 6: Compilers emit metadata, not instructions

The Qiskit compiler attaches an `assertion_probe: list[QAssertion]` field
to the existing per-state metadata block. The QASM compiler emits one
comment line per assertion: `// assert: superposition(q[0..2]) @ state
encoded`. Neither emits any new gates.

**Why:** Real-hardware execution must be unaffected. Emitting comments
in QASM keeps the file fully forward-compatible with all external tools
(Qiskit, BQSKit, OpenQASM linters) and lets a human reader of the
generated QASM still see the assertion intent at the right point.

## Risks / Trade-offs

- **[Risk] Assertion sampling is not free in verifier wall time.**
  → Mitigation: default `shots_per_assert=512` is small enough to keep
  the Bell-pair example test under one second on QuTiP; the policy is
  per-machine so a slow CI suite can drop to `shots=64` for development.

- **[Risk] An asserted state can be unreachable from `[initial]`.**
  Static reachability checks already exist; they will fire before the
  assertion checker sees the unreachable state, so no new error path is
  needed. → Mitigation: the assertion checker MUST short-circuit on
  states already flagged unreachable, returning no diagnostic for those
  states.

- **[Risk] Statistical false positives at the boundary.**
  A truly entangled state with `Tr(ρ²) = 1 − ε − δ` for tiny δ may
  occasionally fail the bound at low shot counts. → Mitigation: the
  Wilson-score-interval logic emits `ASSERTION_INCONCLUSIVE` rather than
  `ASSERTION_FAILED` when the bound straddles the threshold, so a
  borderline case prompts the author to raise `shots_per_assert` rather
  than silently failing CI.

- **[Risk] Mid-circuit-measured states need outcome-conditional replay.**
  → Mitigation: the Stage 4b backend already handles this for
  measurement-aware simulation; the assertion probe hooks into the same
  post-measurement state snapshot. The first assertion test added MUST
  exercise a state that lives downstream of a `measure` action.

- **[Trade-off] Assertions evaluate against default parameter values
  only.** A QAOA machine with `gamma` defaulting to 0.5 will assert
  against `gamma=0.5`. This is acceptable for the debug-loop use case
  (the author can edit the default to sweep) but is a known limitation;
  parameterized assertions are deferred to a later change.

- **[Trade-off] No assertion checking on real-device targets.** A single
  informational `ASSERTIONS_SKIPPED_NO_SIMULATOR` is emitted instead.
  This avoids any pretence that we can replay a destructive measurement
  on real hardware, but it does mean that "verify CI passes against the
  simulator, run on hardware, get a wrong-answer surprise" remains a
  possible failure mode. The author retains the responsibility to
  re-run the simulator path before each hardware run.
