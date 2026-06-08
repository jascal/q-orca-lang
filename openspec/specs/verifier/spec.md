# Verifier Capability

## Purpose

The Q-Orca verifier runs a multi-stage pipeline over a parsed
`QMachineDef` and returns a `QVerificationResult` with errors and
warnings. The pipeline is orchestrated by
`q_orca/verifier/__init__.py::verify()` and exposes a `VerifyOptions`
dataclass with skip flags for individual stages.
## Requirements
### Requirement: Pipeline Ordering

The verifier SHALL run stages in the following order: structural,
completeness, determinism, classical-context, composition,
quantum (static), dynamic (QuTiP), superposition leak, state
assertions. If the structural stage produces any error, later stages
SHALL be skipped. Otherwise, every non-skipped stage SHALL run and
their errors SHALL be merged into a single result.

The state-assertions stage SHALL be skipped when the machine declares
no `state_assertions` verification rule, when no `## state` heading
carries an `[assert: …]` annotation, or when
`VerifyOptions.skip_state_assertions` is set.

#### Scenario: Structural failure halts the pipeline

- **WHEN** a machine has no `[initial]` state and no states at all
- **THEN** `verify()` returns a result whose only errors come from
  the structural stage and no other stages run

#### Scenario: Merged errors from multiple stages

- **WHEN** a valid machine declares a `## verification rules` bullet
  for `unitarity` and also has an orphan event
- **THEN** the result includes an `ORPHAN_EVENT` warning from the
  structural stage AND runs the Stage-4 unitarity check

#### Scenario: Composition stage runs before quantum-static

- **WHEN** a machine has an invoke state referencing an unresolved
  child machine
- **THEN** the verifier emits `UNRESOLVED_CHILD_MACHINE` from the
  composition stage, and the quantum static stage still runs

#### Scenario: State-assertions stage skipped when no rule declared

- **WHEN** a machine carries `[assert: …]` annotations on its states
  but does not declare `state_assertions` under `## verification rules`
- **THEN** the state-assertions stage SHALL NOT run and no
  assertion-related diagnostics are emitted

#### Scenario: State-assertions stage skipped when no annotations

- **WHEN** a machine declares `state_assertions` under
  `## verification rules` but no state carries an `[assert: …]`
  annotation
- **THEN** the state-assertions stage SHALL run trivially and emit no
  diagnostics

### Requirement: Structural Checks

The verifier SHALL reject machines that violate any of: missing
initial state, undeclared source/target state, unreachable state, or
deadlocked non-final state. It SHALL additionally warn on orphan
events and orphan actions.

#### Scenario: Undeclared target state

- **WHEN** a transition targets a state with no matching `## state` heading
- **THEN** the verifier emits `UNDECLARED_STATE` at error severity

#### Scenario: Deadlock

- **WHEN** a non-final state has zero outgoing transitions
- **THEN** the verifier emits `DEADLOCK` at error severity

### Requirement: Completeness Check

Unless `VerifyOptions.skip_completeness` is set, the verifier SHALL
enforce that every `(state, event)` pair has at least one transition,
with an exception for "quantum preparation paths". A machine is
treated as a preparation path if it has measurement events and more
than half of its non-final states have exactly one outgoing transition;
in that case only the first-indexed event per state is required.

#### Scenario: Missing event handler

- **WHEN** a non-final state in a non-preparation machine fails to
  handle a declared event
- **THEN** the verifier emits `INCOMPLETE_EVENT_HANDLING` at error severity

### Requirement: Determinism Check

The verifier SHALL group transitions by `(source, event)` and enforce
that no group contains more than one unguarded transition. When
multiple guarded transitions share a group, the verifier SHALL attempt
to prove mutual exclusion via (1) name-based negation pairs, (2)
syntactic equality on the guard name, (3) named guard expressions
with opposite literal values on the same field, (4) probability or
fidelity expressions that sum to ~1.0.

#### Scenario: Two unguarded transitions on the same event

- **WHEN** a state has two transitions on the same event and neither
  has a guard
- **THEN** the verifier emits `NON_DETERMINISTIC` at error severity

#### Scenario: Probability guards that sum to 1

- **WHEN** two measurement transitions from a state have probability
  guards of 0.5 and 0.5
- **THEN** mutual exclusion is proven and no `GUARD_OVERLAP` warning is emitted

### Requirement: Quantum Static Checks — Unitarity

Unless `VerifyOptions.skip_quantum` is set, the verifier SHALL run
opt-in quantum checks based on the machine's `## verification rules`
section. The unitarity check SHALL accept the gate kinds
`H, X, Y, Z, CNOT, CZ, SWAP, T, S, Rx, Ry, Rz, CCNOT, CSWAP, CCZ, MCX,
MCZ, CRx, CRy, CRz, RXX, RYY, RZZ` as known-unitary; any `custom` gate
SHALL produce an `UNVERIFIED_UNITARITY` warning. Gate target or
control indices at or beyond the inferred qubit count SHALL produce
`QUBIT_INDEX_OUT_OF_RANGE`. A controlled gate whose control and target
sets overlap SHALL produce `CONTROL_TARGET_OVERLAP`. For `MCX` and
`MCZ` the overlap check SHALL apply pairwise across the full control
list and the single target.

#### Scenario: Out-of-range qubit

- **WHEN** a 2-qubit machine has an action `X(qs[5])`
- **THEN** the verifier emits `QUBIT_INDEX_OUT_OF_RANGE` at error severity

#### Scenario: MCZ on three controls is recognized

- **WHEN** a 4-qubit machine has an action with effect
  `MCZ(qs[0], qs[1], qs[2], qs[3])` and `unitarity` declared
- **THEN** the verifier emits no `UNVERIFIED_UNITARITY` warning for
  that action

#### Scenario: MCX with overlapping control and target

- **WHEN** a 4-qubit machine has an action
  `MCX(qs[0], qs[1], qs[2], qs[2])`
- **THEN** the verifier emits `CONTROL_TARGET_OVERLAP` at error
  severity

### Requirement: Quantum Static Checks — No Cloning, Entanglement, Collapse

When the corresponding rule is declared the verifier SHALL:

- Scan action effects lexically for the tokens `copy`, `clone`,
  `duplicate` (errors) and `fanout` without `cnot` (warning)
- Verify that any state labeled as entangled (by state expression, by
  name regex matching `bell`, `ghz`, `epr`, `entangl`, or by the
  `(|a>±|b>)/√2` pattern) has at least one incoming entangling gate
  (`CNOT`, `CZ`, `SWAP`, `CSWAP`)
- Verify that probability guards on measurement branches sum to 1.0
  (±0.01)

#### Scenario: Entangled state without entangling gate

- **WHEN** a state named `|bell>` has `unitarity` + `entanglement`
  rules, but the only incoming transition uses `H(qs[0])`
- **THEN** the verifier emits `ENTANGLEMENT_WITHOUT_GATE` at warning severity

### Requirement: Dynamic Quantum Verification

Unless `VerifyOptions.skip_dynamic` is set, the verifier SHALL attempt
to simulate the gate sequence through QuTiP when QuTiP is importable.
When QuTiP is unavailable the stage SHALL return a passing result. For
states declared as entangled it SHALL compute reduced density matrices
and Schmidt rank across the declared or inferred qubit pair.

The dynamic verifier's gate-effect-string parsing SHALL delegate to
`q_orca.effect_parser` and SHALL NOT maintain a private regex block.
Every gate kind recognized by the shared parser — including two-qubit
parameterized gates (`RXX`, `RYY`, `RZZ`) and controlled rotations
(`CRx`, `CRy`, `CRz`) — SHALL be recognized by the dynamic verifier
without per-site code changes.

When a machine declares an `## encoding` section with
`kind == "hea"`, Stage 4b SHALL invoke
`q_orca.compiler.compute_concept_gram_hea(machine)` to validate
that the encoding declaration and the `## theta` block are
consistent and that the per-concept HEA states can be
constructed. Any `HeaGramConfigurationError` raised by the helper
SHALL be surfaced as a Stage 4b verifier error with code
`HEA_GRAM_INVALID`. Because the check builds per-concept
statevectors via numpy simulation, it SHALL be gated by the same
`VerifyOptions.skip_dynamic` flag as the backend dispatch and
SHALL NOT run when `skip_dynamic=True`.

This change introduces only the *consistency* check; enforcement
of tier-ordering bands (e.g. "sub-cluster mean exceeds
cross-cluster max by at least `HEA_TIER_TOLERANCE = 0.025`") is
deferred to a follow-up proposal that defines the matching
invariant grammar. For now `HEA_TIER_TOLERANCE` is exposed as a
module-level constant so downstream tests and the follow-up
proposal share a single source of truth, but the verifier does
not yet read it.

For machines without an `## encoding` section, Stage 4b dispatch
behavior is unchanged: rung-0 product-state and rung-1
CNOT-staircase MPS encodings continue to be detected via existing
mechanisms (effect-string introspection / explicit rung-1 helper
call).

#### Scenario: No entanglement when expected

- **WHEN** a machine declares `entanglement(q0, q1) = True` but the
  simulated circuit produces a product state
- **THEN** the verifier emits `DYNAMIC_NO_ENTANGLEMENT` at error severity

#### Scenario: QuTiP unavailable

- **WHEN** `qutip` cannot be imported
- **THEN** the dynamic stage returns a passing result with no errors

#### Scenario: Two-qubit parameterized gates appear in the gate sequence

- **WHEN** an action's effect is
  `RZZ(qs[0], qs[1], gamma); RZZ(qs[1], qs[2], gamma)`
- **THEN** `_build_gate_sequence` emits a step containing two
  `RZZ` gate-dicts, each with `targets=[i, j]` and
  `params={"theta": <gamma>}` — not an empty step

#### Scenario: Controlled rotations retain their control qubit

- **WHEN** an action's effect is `CRx(qs[0], qs[1], beta)`
- **THEN** `_build_gate_sequence` emits a gate-dict with
  `name="CRX"`, `controls=[0]`, `targets=[1]`,
  `params={"theta": <beta>}` — not a bare `RX` with empty `controls`

#### Scenario: HEA encoding triggers consistency check

- **GIVEN** a machine with `## encoding` declaring `kind: hea`
  and a valid `## theta` block whose tensor shapes match
  `(|rotations|, depth, n)` and whose row count matches the
  number of `query_concept` call sites
- **WHEN** `verify(machine)` runs Stage 4b
- **THEN** `compute_concept_gram_hea(machine)` is invoked exactly
  once
- **AND** Stage 4b reports no `HEA_GRAM_INVALID` errors

#### Scenario: HEA shape mismatch surfaces a Stage 4b error

- **GIVEN** an HEA machine whose `## theta` block has a row
  whose tensor shape does not equal `(|rotations|, depth, n)`,
  but the row survived initial parsing (e.g., loaded
  programmatically)
- **WHEN** Stage 4b runs
- **THEN** the verifier emits `HEA_GRAM_INVALID` at error
  severity, naming the offending concept and the shape mismatch

#### Scenario: HEA call-site / theta-row mismatch surfaces a Stage 4b error

- **GIVEN** an HEA machine whose `query_concept` action has more
  call sites than the `## theta` block has rows
- **WHEN** Stage 4b runs
- **THEN** the verifier emits `HEA_GRAM_INVALID` at error
  severity, naming the call-site count and the theta-row count

#### Scenario: Non-HEA machine bypasses the HEA dispatch

- **GIVEN** a machine without an `## encoding` section (e.g., the
  rung-0 `larql-polysemantic-clusters` example)
- **WHEN** Stage 4b runs
- **THEN** the verifier does NOT call
  `compute_concept_gram_hea`
- **AND** existing rung-0 / rung-1 dispatch behavior is preserved

#### Scenario: HEA check honors skip_dynamic

- **GIVEN** an HEA machine that would otherwise raise
  `HEA_GRAM_INVALID` (e.g., a programmatically shape-mismatched
  theta tensor that survived initial parsing)
- **WHEN** `verify(machine, VerifyOptions(skip_dynamic=True))`
  runs
- **THEN** `compute_concept_gram_hea` is NOT invoked
- **AND** no `HEA_GRAM_INVALID` error is emitted

### Requirement: Superposition Leak Detection

The verifier SHALL infer superposition states from their expressions,
names, or incoming gates (`H`, `Rx`, `Ry`, `Rz`, `CNOT`, `CZ`,
`SWAP`, `CCNOT`, `CSWAP`, `CCZ`, `MCX`, `MCZ`). For each superposition
state it SHALL warn when measurement transitions leave the state
unguarded to a non-final target, or when a collapse-sensitive gate
moves the machine to a non-superposition state.

#### Scenario: Unguarded measurement from a superposition state

- **WHEN** a state `|+>` has an outgoing measurement transition with
  no probability guard and the target is not final
- **THEN** the verifier emits a `SUPERPOSITION_LEAK` warning

#### Scenario: Multi-controlled gate creates an inferred superposition

- **WHEN** a state's only incoming transition's action contains an
  `MCZ` gate
- **THEN** that target state is treated as a superposition state for
  leak-detection purposes (parity with `CZ` and `CCNOT`)

### Requirement: Consumed Invariant Forms

The verifier SHALL consume invariant forms parsed by the language
parser. Currently this is limited to `entanglement(qN, qM) = True`
and `schmidt_rank(qN, qM) <op> k`. Other invariant forms appearing in
a machine SHALL be ignored by the verifier until the parser produces
AST nodes for them.

#### Scenario: Fidelity invariant

- **WHEN** a machine declares `fidelity(|ψ>, |Φ+>) >= 0.99` under
  `## invariants`
- **THEN** no AST node is produced for that line and the verifier does
  not attempt to check it (scoped to a future change)

### Requirement: Parametric Action Verification

The verifier SHALL run static and dynamic gate-sequence checks against
the compiler-expanded effect string at each call site of a parametric
action, not against the action template. Each call site SHALL be
verified independently of the others.

The verifier SHALL NOT raise unitarity, range, or overlap errors
against the action *template* itself when the template contains
identifier subscripts (`qs[c]`); template-only checks SHALL be
limited to: signature shape (parameters typed), effect-string
parseability (every gate kind recognized), and identifier-binding
closure (every subscript identifier appears in the signature).

For a parametric action with N call sites, range and overlap errors
SHALL be reported at the call site, naming the transition's source
location and the bound argument values. The same template
contributing N range errors SHALL produce N distinct error entries,
not one aggregated entry, so the user can see which call site failed.

If a parametric action is declared but never invoked, it SHALL produce
an `ORPHAN_ACTION` warning at the structural stage (existing
behavior), and SHALL NOT be expanded or verified beyond the
template-only checks.

#### Scenario: Expanded MCZ call sites are unitarity-checked

- **WHEN** a parametric action
  `oracle | (qs, t: int) -> qs | MCZ(qs[0], qs[1], qs[2], qs[t])` is
  invoked at three transitions with `t ∈ {3, 4, 5}` in a 6-qubit
  machine with `unitarity` declared
- **THEN** the verifier runs the unitarity check three times (once
  per call site) and emits no errors

#### Scenario: Range error reported at the call site

- **WHEN** the same `oracle` template is invoked with `t=9` in a
  6-qubit machine
- **THEN** the verifier emits a `QUBIT_INDEX_OUT_OF_RANGE` whose
  message names the transition's source location and the bound value
  `t=9`, not the action's source location

#### Scenario: Template-only check rejects unbound subscript

- **WHEN** an action declares `query | (qs) -> qs | Hadamard(qs[c])`
  with no `c` in its signature
- **THEN** the verifier (via the parser's structured error) reports
  an unbound-identifier error at the action definition, before any
  call-site expansion is attempted

#### Scenario: Orphan parametric action

- **WHEN** a machine declares a parametric action that no transition
  invokes
- **THEN** the structural stage emits `ORPHAN_ACTION` and no
  expansion-time verification runs against the template

### Requirement: Resource Bound Verification

The verifier SHALL run a `check_resource_invariants` rule that
evaluates each `Invariant(kind="resource")` against the metric
value computed by `q_orca/compiler/resources.py::estimate_resources`.
The rule SHALL be activated under the name `resource_bounds` in
`## verification rules` and SHALL be skipped (zero cost) when the
machine has no resource invariants.

For each resource invariant the rule SHALL:

1. Read the metric value from `estimate_resources(machine)`
   (memoized; one transpile pass per machine even with multiple
   invariants).
2. Apply the comparison operator from the invariant against the
   integer bound.
3. On violation, emit a `VerifyError` with code
   `RESOURCE_BOUND_EXCEEDED`, severity `error`, and a message
   containing the metric name, the measured value, the operator,
   and the bound.
4. On indeterminate measurement (the metric returns the literal
   string `"unknown"`), emit a `VerifyError` with code
   `RESOURCE_BOUND_INDETERMINATE` and severity `warning`.

The rule SHALL run after the existing structural and quantum
checks so a malformed circuit fails on its structural problems
first, before resource accounting is attempted.

#### Scenario: Resource bound is satisfied

- **WHEN** a machine has `cx_count <= 5` and the compiled circuit
  has 1 CX gate
- **THEN** `check_resource_invariants` emits no diagnostic, and the
  verify result remains valid

#### Scenario: Resource bound is exceeded

- **WHEN** a machine has `cx_count <= 0` and the compiled circuit
  contains a CNOT
- **THEN** `check_resource_invariants` emits a `VerifyError` with
  code `RESOURCE_BOUND_EXCEEDED`, severity `error`, and the
  message references the metric name `cx_count`, the measured
  value `1`, the operator `<=`, and the bound `0`

#### Scenario: T-count equality bound flags Clifford regression

- **WHEN** a machine has `t_count == 0` and the compiled circuit
  contains a `T` gate (decomposed by transpile to a non-zero T
  count)
- **THEN** `check_resource_invariants` emits
  `RESOURCE_BOUND_EXCEEDED` with the measured T-count and the
  expected `0`

#### Scenario: Multiple resource invariants share one transpile pass

- **WHEN** a machine has both `cx_count <= 12` and `t_count == 0`
- **THEN** `check_resource_invariants` evaluates both invariants
  using one memoized call to `estimate_resources` (no duplicate
  Qiskit transpile work)

#### Scenario: Rule is skipped when no resource invariants are present

- **WHEN** a machine has no `Invariant(kind="resource")` entries
- **THEN** `check_resource_invariants` returns immediately and does
  not invoke `estimate_resources`

#### Scenario: Indeterminate metric emits warning, not error

- **WHEN** a metric value is `"unknown"` (because of a runtime-bound
  loop construct that cannot be statically evaluated) and an
  invariant references that metric
- **THEN** `check_resource_invariants` emits a `VerifyError` with
  code `RESOURCE_BOUND_INDETERMINATE` and severity `warning`,
  and the verify result remains valid (warnings do not invalidate)

#### Scenario: Rule respects opt-out via verification rules

- **WHEN** a machine has resource invariants but its
  `## verification rules` block disables `resource_bounds`
- **THEN** `check_resource_invariants` is skipped and no
  `RESOURCE_BOUND_*` diagnostic is emitted

### Requirement: HEA tier-separation invariant enforcement

The verifier SHALL enforce a declared `concept_gram_tier_separation`
invariant against the analytic Gram of any HEA-encoded machine.
Specifically, when a machine declares an `## encoding` section with
`kind == "hea"` AND a `concept_gram_tier_separation` invariant in
`## invariants`, Stage 4b SHALL compute the analytic Gram via
`compute_concept_gram_hea(machine)` and evaluate the declared
inequality against the metric `tier_separation` defined as:

```
tier_separation =
    min over clusters C with |C| >= 2 of
        mean(|<c_i|c_j>|² for c_i, c_j in C, i < j)
    − max over (i, j) cross-cluster pairs of |<c_i|c_j>|²
```

Cluster membership SHALL come from the per-row `cluster` field of
the `## theta` block — rows sharing a `cluster` value form one
tier; rows with distinct values form distinct tiers. Singleton
clusters contribute no intra-cluster pairs and SHALL be ignored
by the `min`. If every cluster is a singleton, `tier_separation`
is undefined and Stage 4b SHALL emit `HEA_TIER_UNDEFINED` at error
severity.

On inequality violation, Stage 4b SHALL emit
`HEA_TIER_INVARIANT_VIOLATED` at error severity, naming the
declared bound, the actual computed `tier_separation`, and at
least one cluster pair that drives the violation.

The check SHALL be gated by the same `VerifyOptions.skip_dynamic`
flag as the existing HEA consistency check. It SHALL NOT run when
`skip_dynamic=True`.

When a machine declares `concept_gram_tier_separation` but no HEA
encoding (rung-0 or rung-1 machine, or a machine without any
`## encoding` section), Stage 4b SHALL emit
`HEA_TIER_INVARIANT_NOT_APPLICABLE` at *warning* severity — the
invariant has no Gram to evaluate against. Verification SHALL NOT
fail solely because of this warning.

#### Scenario: Tier-separation invariant satisfied

- **GIVEN** an HEA machine with three concepts grouped as `s1: a,
  b` and `s2: c`, an analytic
  Gram with intra-`s1` mean overlap 0.9999 and max cross-cluster
  overlap 0.3837, and `## invariants` declaring
  `- concept_gram_tier_separation >= 0.025`
- **WHEN** Stage 4b runs
- **THEN** the verifier emits no `HEA_TIER_*` errors
- **AND** the consistency check (`HEA_GRAM_INVALID`) is unaffected

#### Scenario: Tier-separation invariant violated

- **GIVEN** an HEA machine with the same cluster assignment but
  whose theta values produce intra-`s1` mean 0.50 and max
  cross-cluster 0.55, with
  `- concept_gram_tier_separation >= 0.025` declared
- **WHEN** Stage 4b runs
- **THEN** the verifier emits `HEA_TIER_INVARIANT_VIOLATED` at
  error severity, naming the declared bound (`>= 0.025`), the
  actual computed tier_separation (negative), and the cluster
  pair `(s1, s2)`

#### Scenario: All-singleton clusters yield HEA_TIER_UNDEFINED

- **GIVEN** an HEA machine with three concepts each in a distinct
  singleton cluster (`s1`, `s2`, `s3`) and a
  `concept_gram_tier_separation >= 0.025` invariant
- **WHEN** Stage 4b runs
- **THEN** the verifier emits `HEA_TIER_UNDEFINED` at error
  severity, explaining that no cluster has at least two members

#### Scenario: Invariant honors skip_dynamic

- **GIVEN** an HEA machine that would otherwise emit
  `HEA_TIER_INVARIANT_VIOLATED`
- **WHEN** `verify(machine, VerifyOptions(skip_dynamic=True))`
  runs
- **THEN** the verifier does NOT compute the Gram and does NOT
  emit `HEA_TIER_INVARIANT_VIOLATED`

#### Scenario: Invariant on non-HEA machine warns but does not fail

- **GIVEN** a rung-0 product-state machine with no `## encoding`
  section but whose `## invariants` mistakenly declares
  `- concept_gram_tier_separation >= 0.025`
- **WHEN** Stage 4b runs
- **THEN** the verifier emits
  `HEA_TIER_INVARIANT_NOT_APPLICABLE` at warning severity
- **AND** verification SHALL NOT fail solely because of this
  warning

### Requirement: Feedforward completeness

The verifier SHALL track the set of bit indices referenced by every
conditional gate effect across the machine. For a `QEffectConditional`
with conditions `[(i_1, v_1), …, (i_N, v_N)]`, every `i_k` SHALL be
added to the feedforward-bit set, not just the head condition's
index.

The existing per-bit completeness rule SHALL continue to apply: if a
machine declares a `feedforward_completeness` verification rule, then
every bit position written by a `measure(qs[_]) -> bits[i]` effect on
some reachable path SHALL be referenced by at least one conditional
gate's condition list.

#### Scenario: Compound condition registers every bit

- **GIVEN** a machine with a single conditional action whose effect
  is `if bits[0] == 1 and bits[1] == 1: X(qs[1])`
- **WHEN** the verifier collects feedforward bits
- **THEN** both `0` and `1` SHALL be in the feedforward-bit set

#### Scenario: Single-condition behavior unchanged

- **GIVEN** a machine with a conditional action whose effect is
  `if bits[2] == 1: Z(qs[2])`
- **WHEN** the verifier collects feedforward bits
- **THEN** `2` SHALL be in the feedforward-bit set (unchanged from
  prior behavior)

### Requirement: State Assertions Stage

The verifier SHALL run `q_orca.verifier.assertions.check_state_assertions(machine,
backend)` and merge its diagnostics into the verification result whenever
the `state_assertions` verification rule is declared and at least one
state carries an `[assert: …]` annotation.

For each `QAssertion` on each annotated state, the stage SHALL:

1. Build the circuit prefix that drives the machine from `[initial]` to
   the annotated state along its declared transitions, honouring any
   intervening mid-circuit measurements via outcome-conditional replay
   on the chosen backend.
2. Run `assertion_policy.shots_per_assert` samples on the backend
   selected by `assertion_policy.backend` (`auto` resolves to QuTiP).
3. Evaluate the assertion's predicate against the sample distribution
   (Z-basis counts for `classical` / `superposition`; reduced
   density-matrix purity via partial trace for `entangled` /
   `separable`).
4. Compute a confidence bound (Wilson score interval or analogous);
   compare against `assertion_policy.confidence`.
5. Emit exactly one diagnostic per evaluated assertion, drawn from
   `ASSERTION_PASSED`, `ASSERTION_FAILED`, or
   `ASSERTION_INCONCLUSIVE`.

When the chosen backend is unavailable (e.g. QuTiP not installed and
`backend='auto'`), the stage SHALL emit one
`ASSERTION_BACKEND_MISSING` diagnostic naming the missing backend and
SHALL NOT attempt to evaluate any assertion. When the compile target
is a real device (no simulator path), the stage SHALL emit a single
informational `ASSERTIONS_SKIPPED_NO_SIMULATOR` diagnostic and SHALL
NOT evaluate any assertion.

Assertion failures SHALL be reported at error severity when
`assertion_policy.on_failure='error'` and at warning severity when
`assertion_policy.on_failure='warn'`. `ASSERTION_INCONCLUSIVE` and
`ASSERTION_BACKEND_MISSING` SHALL always be at warning severity.
`ASSERTIONS_SKIPPED_NO_SIMULATOR` SHALL be at info severity.

If a state is already flagged unreachable by the structural stage,
the assertion-checking stage SHALL skip that state silently and emit
no diagnostic for any of its assertions.

#### Scenario: Passing classical assertion

- **WHEN** a state declared `[assert: classical(qs[0])]` is reached by
  a circuit prefix that prepares `|0>` and applies no further gates
- **THEN** the verifier emits `ASSERTION_PASSED` for that assertion at
  info severity and adds no errors

#### Scenario: Passing superposition assertion

- **WHEN** a state declared `[assert: superposition(qs[0])]` is reached
  after `Hadamard(qs[0])`
- **THEN** the verifier emits `ASSERTION_PASSED` and adds no errors

#### Scenario: Passing entangled assertion on a Bell pair

- **WHEN** a state declared `[assert: entangled(qs[0], qs[1])]` is
  reached after `Hadamard(qs[0]); CNOT(qs[0], qs[1])`
- **THEN** the verifier emits `ASSERTION_PASSED` and the reduced
  density matrix on `(0, 1)` has `Tr(ρ²) < 1 - ε`

#### Scenario: Failing entangled assertion is an error

- **WHEN** a state declared `[assert: entangled(qs[0], qs[1])]` is
  reached after `Hadamard(qs[0])` only (no CNOT)
- **THEN** the verifier emits `ASSERTION_FAILED` at error severity
  citing the state and the assertion source span

#### Scenario: Inconclusive assertion at small shot counts

- **WHEN** a machine sets `shots_per_assert=16` and an assertion at the
  Wilson-score boundary cannot clear `confidence=0.99`
- **THEN** the verifier emits `ASSERTION_INCONCLUSIVE` at warning
  severity rather than `ASSERTION_FAILED`

#### Scenario: Backend missing emits a single warning

- **WHEN** `assertion_policy.backend='auto'` and QuTiP cannot be
  imported
- **THEN** the verifier emits exactly one `ASSERTION_BACKEND_MISSING`
  warning naming `qutip`, and no per-assertion diagnostics

#### Scenario: Real-device target skips assertions

- **WHEN** the compile target is a real device with no simulator path
- **THEN** the verifier emits a single
  `ASSERTIONS_SKIPPED_NO_SIMULATOR` info diagnostic and evaluates no
  assertion predicate

#### Scenario: Slice form of `superposition` requires only one qubit

- **WHEN** a state declared `[assert: superposition(qs[0..2])]` is
  reached in a GHZ-style state where individual marginals are mixed
- **THEN** the verifier emits `ASSERTION_PASSED` because at least one
  qubit's marginal Z-basis sample shows both outcomes non-trivially

#### Scenario: `on_failure='warn'` downgrades severity

- **WHEN** a machine sets `on_failure='warn'` and an assertion fails
- **THEN** the diagnostic is `ASSERTION_FAILED` at warning severity
  rather than error severity

#### Scenario: Unreachable state assertion skipped

- **WHEN** a state with `[assert: …]` annotations is flagged
  `UNREACHABLE` by the structural stage
- **THEN** the assertion-checking stage emits no diagnostic for any
  assertion on that state

### Requirement: Composition — Child Resolution and Typing

The verifier SHALL statically check every invoke state unless
`VerifyOptions.skip_composition` is set: the child machine must
resolve to a machine reachable from the importing file, argument bindings
must type-unify with the child's context, return bindings must
type-unify with the child's `## returns` declarations. For each
invoke state:

- The child machine name SHALL resolve in the following order:
  (1) a `QMachineDef` in the same `QOrcaFile`; (2) an alias declared in this
  file's `## imports`; (3) a re-export reachable through the import graph.
  A same-file machine SHALL shadow any import of the same name. If the name
  resolves from two or more distinct non-local sources it is
  `AMBIGUOUS_CHILD_MACHINE`. If it resolves from none it is
  `UNRESOLVED_CHILD_MACHINE` at error severity, whose message SHALL list the
  closest known names (same-file machines plus import-graph aliases) ranked by
  edit distance as "did you mean…?" suggestions.
- Each argument binding SHALL have a LHS that matches a declared
  context field on the child; otherwise: `INVOKE_ARG_UNDECLARED`.
- Each argument binding's RHS parent-side type SHALL unify with
  the child-side field type; otherwise:
  `INVOKE_ARG_TYPE_MISMATCH`.
- Each return binding's RHS SHALL match a name declared in the
  child's `## returns` section; otherwise: `INVOKE_RETURN_UNDECLARED`.
- Each return binding's LHS parent-side field type SHALL unify
  with the child-side return type (for `shots=1`) or with the
  synthesized-aggregate type (for `shots>1`); otherwise:
  `INVOKE_RETURN_TYPE_MISMATCH`.

When `--no-follow-imports` is set the verifier SHALL skip import resolution
entirely and treat every non-local invoke as `UNRESOLVED_CHILD_MACHINE`, with a
message noting that import-following is disabled.

#### Scenario: Unresolved child machine

- **WHEN** an invoke state references `Missing` but no machine
  named `Missing` exists in the file or its import graph
- **THEN** the verifier emits `UNRESOLVED_CHILD_MACHINE` at error
  severity

#### Scenario: Child resolved through an import alias

- **WHEN** an invoke state references `PrepareBellPair`, the file imports
  `./lib/bell-pair.q.orca.md` aliasing `PrepareBellPair`, and that file defines
  a `PrepareBellPair` machine
- **THEN** the child resolves and its arg/return bindings are type-checked
  against the imported machine

#### Scenario: Same-file machine shadows an import

- **WHEN** a file defines a local `## machine Child` and also imports a `Child`
  alias from another file
- **THEN** the local machine is used and no `AMBIGUOUS_CHILD_MACHINE` is emitted

#### Scenario: Ambiguous child across two imports

- **WHEN** a name resolves to a `Child` alias from two different imported files
- **THEN** the verifier emits `AMBIGUOUS_CHILD_MACHINE` naming both source paths

#### Scenario: Edit-distance suggestion on a typo

- **WHEN** an invoke references `Diffser` and the import graph exposes
  `Diffuser`
- **THEN** the `UNRESOLVED_CHILD_MACHINE` message lists `Diffuser` as a suggestion

#### Scenario: Arg type mismatch

- **WHEN** a parent binds `theta=theta` but the parent's `theta`
  is `list<float>` and the child's `theta` parameter is `float`
- **THEN** the verifier emits `INVOKE_ARG_TYPE_MISMATCH` at error
  severity

#### Scenario: Return references undeclared aggregate

- **WHEN** a parent binds `hist=hist_bits_0` under `shots=1024`
  but the child's `## returns` row for `bits[0]` lists only
  `expectation` (no `histogram`)
- **THEN** the verifier emits `INVOKE_RETURN_UNDECLARED` at error
  severity

### Requirement: Composition — Shots-Flag Rules

The verifier SHALL enforce that shot-batched mode is used only
with quantum children: `shots=N` on an invoke whose resolved
child has no measurement-bearing transitions is
`SHOTS_ON_CLASSICAL_CHILD` at error severity. Quantum children
with `shots` omitted default to `shots=1`.

#### Scenario: Shots on classical child

- **WHEN** a parent state is
  `[invoke: ClassicalChild() shots=100]` and `ClassicalChild` has
  no measurement effects
- **THEN** the verifier emits `SHOTS_ON_CLASSICAL_CHILD` at error
  severity

#### Scenario: Default shots=1 on quantum child

- **WHEN** a parent state is `[invoke: QChild(theta=theta)]` (no
  shots) and `QChild` is measurement-bearing
- **THEN** no error is emitted; the invoke is treated as
  `shots=1` for return-type unification purposes

### Requirement: Composition — Recursive Verification and Cycles

The verifier SHALL run the full verifier pipeline on each
resolved child and SHALL surface child errors into the parent
result with a `child_path` breadcrumb. Any machine that invokes
itself directly or transitively SHALL be rejected with
`INVOKE_CYCLE` at error severity.

#### Scenario: Child error bubbles up with path prefix

- **WHEN** a parent invokes `Child` from state `|train>` and
  `Child` has an `INCOMPLETE_EVENT_HANDLING` error on its
  `|idle>` state
- **THEN** the parent's verification result includes an error
  whose `location` dict carries
  `{"invoke_state": "|train>", "child_path":
    [{"state": "|idle>", "event": "<event>"}]}`

#### Scenario: Direct self-invoke

- **WHEN** a machine `Loop` has a state
  `[invoke: Loop()]`
- **THEN** the verifier emits `INVOKE_CYCLE` at error severity

#### Scenario: Transitive cycle

- **WHEN** machine `A` invokes `B` and `B` invokes `A`
- **THEN** the verifier emits `INVOKE_CYCLE` on both machines

### Requirement: Import Graph Resolution

The verifier SHALL resolve a file's imports via a breadth-first walk of the
import graph that parses each file at most once (memoised by absolute path) and
detects cycles. Re-exports SHALL be followed transitively but a chain longer
than four hops SHALL be rejected. The resolver SHALL surface the following
diagnostics at error severity:

- `IMPORT_NOT_FOUND` — an import `Path` does not resolve to an existing file (or
  is an absolute path).
- `IMPORT_PARSE_FAILED` — an imported file fails to parse; the message SHALL
  re-prefix the delegated parse error with the import chain that reached it.
- `IMPORT_CYCLE` — a file imports one of its own ancestors; the message SHALL
  render the cycle as a path list.
- `IMPORT_CHAIN_TOO_DEEP` — a re-export chain exceeds four hops; the message
  SHALL render the chain.

#### Scenario: Import cycle is rejected

- **WHEN** file A imports B and B imports A
- **THEN** the verifier emits `IMPORT_CYCLE` rendering the cycle as `A → B → A`

#### Scenario: Missing import file

- **WHEN** an import row points at a path with no file on disk
- **THEN** the verifier emits `IMPORT_NOT_FOUND` naming the unresolved path

#### Scenario: Re-export chain too deep

- **WHEN** a machine is re-exported through a chain of more than four files
- **THEN** the verifier emits `IMPORT_CHAIN_TOO_DEEP` rendering the chain

#### Scenario: Imported file parse failure is re-prefixed

- **WHEN** an imported file contains a parse error
- **THEN** the verifier emits `IMPORT_PARSE_FAILED` whose message names the
  import chain and includes the underlying parse error

### Requirement: Classical Context Update — Scalar Numeric Typing

The verifier SHALL accept a scalar (non-indexed) `+=` / `-=` context-update target whose declared type is any numeric scalar — `int` or `float` — and SHALL reject only non-numeric scalar targets with `CONTEXT_FIELD_TYPE_MISMATCH`.

This relaxes the earlier `int`-only rule for scalar targets. The runtime's context-update interpreter already performs `float` arithmetic, and the field-reference RHS rule already admits `int` or `float`; restricting the scalar LHS to `int` was stricter than the runtime and made a learnable bare-scalar angle unusable (it must be both a rotation-gate argument and a mutation target, and list-index angles do not resolve in the circuit builder). Indexed (`list<float>`) targets and the bit-condition / index-bounds / undeclared-field rules are unchanged.

#### Scenario: Scalar float target accepted

- **WHEN** a machine declares `| theta_0 | float | 0.5 |` and an action's effect is `if bits[0] == 1: theta_0 -= eta else: theta_0 += eta`
- **THEN** the verifier reports no `CONTEXT_FIELD_TYPE_MISMATCH` for `theta_0`

#### Scenario: Scalar int target still accepted

- **WHEN** a machine declares `| iteration | int | 0 |` and an action's effect is `iteration += 1`
- **THEN** the verifier reports no `CONTEXT_FIELD_TYPE_MISMATCH` for `iteration`

#### Scenario: Non-numeric scalar target still rejected

- **WHEN** a machine declares `| label | string | "x" |` and an action's effect is `label += 1`
- **THEN** the verifier emits `CONTEXT_FIELD_TYPE_MISMATCH` at error severity

### Requirement: Noise Channel Well-Formedness

The verifier SHALL validate each `NoiseChannel` row against its per-channel parameter schema and emit `NOISE_CHANNEL_INVALID` at error severity for any row that is missing a required parameter, carries an out-of-range value, or is dimensionally inconsistent.

Per-channel schemas: `depolarizing`/`bit_flip`/`phase_flip` require `p ∈ [0, 1]`; `amplitude_damping`/`phase_damping` require either `gamma ∈ [0, 1]` or a time parameter (`T1`/`T2`); `thermal` requires `T1` and `T2` (optional `n_bar`); `readout_error` requires `p0given1` and `p1given0`; `pauli` requires a `probabilities` list of 4 entries (single-qubit, ordered `[I, X, Y, Z]`) or 16 (two-qubit, in Aer `PauliError` lexicographic order `[II, IX, IY, IZ, XI, …, ZZ]` with the first label as qubit 0) summing to 1; a list of any other length is `NOISE_CHANNEL_INVALID`. A row that supplies both a probability-domain and a time-domain parameter for the same effect SHALL be rejected as `NOISE_PARAMETER_AMBIGUOUS` (no silent auto-conversion). A time-domain parameter without a time unit, or a probability-domain parameter with one, SHALL be rejected as dimensionally inconsistent.

#### Scenario: Out-of-range probability rejected

- **WHEN** a row is `depolarizing | all_gates | p=1.4`
- **THEN** the verifier emits `NOISE_CHANNEL_INVALID` at error severity

#### Scenario: Mixed time and probability parameters rejected

- **WHEN** a row is `amplitude_damping | all_qubits | gamma=0.05, T1=100us`
- **THEN** the verifier emits `NOISE_PARAMETER_AMBIGUOUS` at error severity

#### Scenario: Well-formed Kandala-shaped rows pass

- **WHEN** rows are `depolarizing | single_qubit_gates | p=0.001` and `depolarizing | two_qubit_gates | p=0.012` and `readout_error | all_measurements | p0given1=0.02, p1given0=0.04`
- **THEN** the verifier reports no `NOISE_CHANNEL_INVALID` for any row

### Requirement: Noise Target Resolution

The verifier SHALL resolve each row's target selector against the machine and emit `NOISE_TARGET_NO_MATCH` at warning severity when a selector matches no extant gate, qubit, or measurement (a no-op row).

A `qs[role:R]` selector SHALL resolve against the per-qubit roles declared in `## context`, matching every qubit whose role is `R`; a role that matches no declared qubit SHALL produce `NOISE_TARGET_NO_MATCH`. `gates[...]` selectors naming gates that never appear in the machine, and `qs[N]` indices beyond the declared qubit count, SHALL also produce `NOISE_TARGET_NO_MATCH`.

#### Scenario: Role selector resolves to matching qubits

- **GIVEN** `## context` declares qubits with roles `[q0:data, q1:ancilla, q2:ancilla]`
- **WHEN** a row targets `qs[role:ancilla]`
- **THEN** the selector resolves to qubit indices `[1, 2]` and no `NOISE_TARGET_NO_MATCH` is emitted

#### Scenario: Non-matching selector warns

- **WHEN** a row targets `qs[role:nonexistent]` (or `gates[TOFFOLI]` in a machine with no Toffoli gate)
- **THEN** the verifier emits `NOISE_TARGET_NO_MATCH` at warning severity

### Requirement: Coherence Budget Check

The verifier SHALL, when the noise model declares `thermal`/`T1`/`T2` and `## resources` declares per-gate durations, estimate the worst-case path duration through the transition graph and emit `COHERENCE_BUDGET_EXCEEDED` at warning severity when that duration exceeds the declared `T2`.

The duration estimate SHALL reuse the depth/gate-duration infrastructure from the resource-estimation pipeline. When gate durations are absent the check SHALL be skipped (not an error), and the diagnostic message SHALL include the estimated circuit duration and the `T2` it exceeded.

#### Scenario: Circuit longer than T2 warns

- **WHEN** a machine declares `thermal` with `T2=8ns` and a 20-gate path with per-gate duration `2ns` (40ns > 8ns)
- **THEN** the verifier emits `COHERENCE_BUDGET_EXCEEDED` whose message names both 40ns and 8ns

#### Scenario: No declared durations skips the check

- **WHEN** a noise model declares `T1`/`T2` but `## resources` declares no per-gate durations
- **THEN** the verifier emits no `COHERENCE_BUDGET_EXCEEDED` (the check is skipped, not failed)

### Requirement: Backend Noise Compatibility

The verifier SHALL check the declared noise channels against the selected compile target and report channels a target cannot simulate, without silently dropping them.

When the target is QASM 3 (which has no native noise grammar), every declared channel SHALL produce a `NOISE_DROPPED_FOR_BACKEND` warning naming the channel and the backend, and the compiler SHALL emit the channels as comments (see the compiler spec) and still succeed. When the target is a stabilizer/Stim backend, any non-Pauli channel (`amplitude_damping`, `phase_damping`, `thermal`, `readout_error`, general `pauli`) SHALL be rejected with `STABILIZER_BACKEND_NOISE_INCOMPATIBLE` at error severity (this branch is dormant until the stabilizer backend ships). When the target is Qiskit/Aer, all channels are accepted.

#### Scenario: Non-Pauli channel rejected on stabilizer target

- **WHEN** a machine declares `amplitude_damping` and is compiled with `--target=stabilizer`
- **THEN** the verifier emits `STABILIZER_BACKEND_NOISE_INCOMPATIBLE` at error severity and the machine does not compile

#### Scenario: Channels dropped on QASM target warn but compile

- **WHEN** a machine with any `## noise_model` rows is compiled with `--target=qasm3`
- **THEN** the verifier emits `NOISE_DROPPED_FOR_BACKEND` listing the channels and the backend, and compilation still succeeds

### Requirement: Ancilla Reset Lifecycle

The verifier SHALL enforce, automatically for every qubit tagged `ancilla` (no `## verification rules` opt-in required), that the qubit starts in `|0⟩` and is explicitly `reset` between successive mid-circuit measurements, emitting `ANCILLA_NOT_RESET` at error severity otherwise.

For each `ancilla` qubit the verifier walks the per-state gate sequence and checks (a) no gate acts on it before its first appearance, and (b) some `reset(qs[k])` action occurs between every pair of mid-circuit measurements on it. The diagnostic names the offending state and the gate/measurement index, and SHALL carry an actionable suggestion (e.g. `insert reset(qs[k]) before reusing ancilla q_k after its measurement`).

This rule supersedes a hand-declared `mid_circuit_coherence` rule for `ancilla`-tagged qubits: it is the same check made mandatory and automatic, so an author no longer needs the opt-in line; an explicitly-declared `mid_circuit_coherence` rule remains honored and does not conflict.

#### Scenario: Reused ancilla without reset fails

- **WHEN** a machine tags `q1` as `ancilla` and performs two mid-circuit measurements on `q1` with no `reset(qs[1])` between them
- **THEN** the verifier emits `ANCILLA_NOT_RESET` pointing at the second measurement

#### Scenario: Reset between measurements passes

- **WHEN** the same machine inserts `reset(qs[1])` between the two measurements
- **THEN** no `ANCILLA_NOT_RESET` is emitted for `q1`

### Requirement: Syndrome Measurement Completeness

The verifier SHALL enforce, automatically for every qubit tagged `syndrome`, that the qubit is measured on every cyclic path it participates in, emitting `SYNDROME_NOT_MEASURED` at error severity for a cycle that prepares but never measures it.

When the syndrome qubit's cycle is a `[loop …]`-annotated body, the check SHALL be the exact per-iteration form: the qubit MUST be measured within the annotated body on every path before the `loop_back` edge. When no loop annotation is present, the check uses the strongly-connected-component fallback: every cyclic SCC of the transition graph in which the syndrome qubit is acted upon SHALL contain at least one `measure(qs[k])` on it. The diagnostic SHALL carry an actionable suggestion (e.g. `measure the syndrome qubit q_k on every loop iteration before loop_back`).

#### Scenario: Annotated loop body without a per-iteration measure fails

- **WHEN** a `[loop N]` body acts on a `syndrome` qubit but has a path back to the loop entry that does not measure it
- **THEN** the verifier emits `SYNDROME_NOT_MEASURED` for that body

#### Scenario: Unannotated cycle uses the SCC fallback

- **WHEN** a syndrome qubit participates in a cyclic SCC with no `[loop …]` annotation
- **THEN** the verifier applies the SCC fallback (a measure anywhere in the SCC satisfies the check)

### Requirement: Communication No-Cloning Escalation

The verifier SHALL escalate a no-cloning violation to `COMMUNICATION_NO_CLONING_VIOLATION` at error severity when the duplicated qubit is tagged `communication`; a non-`communication` qubit SHALL continue to emit the generic `NO_CLONING_VIOLATION` unchanged.

The suggestion SHALL be actionable on its own today (e.g. `a communication qubit may not be copied; route it through a single owner or transfer it explicitly`) and additionally point at `[send: q -> X]` protocol annotations as the eventual idiom — so the message is useful before the protocol-state-annotations spec lands.

#### Scenario: Cloning a communication qubit escalates

- **WHEN** a machine clones a qubit tagged `communication` in a way that today produces `NO_CLONING_VIOLATION`
- **THEN** the verifier instead emits `COMMUNICATION_NO_CLONING_VIOLATION` with a fix hint pointing at `[send: …]` annotations

#### Scenario: Cloning a data qubit unchanged

- **WHEN** the cloned qubit is `data` (or untagged)
- **THEN** the verifier emits the generic `NO_CLONING_VIOLATION` exactly as before

### Requirement: Loop Body Well-Formedness

The verifier SHALL identify each `[loop …]`-annotated state's loop body as the strongly-connected component entered through that state and exited via a `loop_done`-tagged transition, and SHALL emit `LOOP_AMBIGUOUS_BODY` at error severity when the body cannot be uniquely determined.

A body is ambiguous when two distinct `[loop …]`-annotated states share a cycle, when there are multiple back-edges to distinct annotated states, or (for v1) when a `[loop …]` body structurally contains another `[loop …]` state (nested loops are out of scope for v1).

The per-transition unitarity check applies once over a **fixed** `[loop N]` body — a non-unitary action (e.g. a measurement) inside a fixed body emits `NON_UNITARY_ACTION` (since `U^N` is unitary iff `U` is); a measurement on the `loop_done` exit edge is outside the body and is allowed. An **adaptive** `[loop until: …]` body is **exempt** from this unitarity check: its per-iteration measurement on the `loop_back` edge is how the classical exit predicate advances, so a measurement inside an adaptive body does not emit `NON_UNITARY_ACTION`.

#### Scenario: Ambiguous body rejected

- **WHEN** two states are both annotated `[loop N]` with overlapping back-edges (a shared cycle)
- **THEN** the verifier emits `LOOP_AMBIGUOUS_BODY` naming the conflicting states

#### Scenario: Non-unitary action inside a fixed body rejected

- **WHEN** a `[loop 5]` body contains a `measure(...)` action on an in-body transition
- **THEN** the verifier emits `NON_UNITARY_ACTION` pointing at the measurement row

#### Scenario: Measurement inside an adaptive body allowed

- **WHEN** a `[loop until: P]` body measures a qubit on its `loop_back` edge each iteration
- **THEN** the verifier emits no `NON_UNITARY_ACTION` — the adaptive body is exempt

#### Scenario: Well-formed single-cycle body accepted

- **WHEN** a `[loop N]` state dominates exactly one cycle with a single `loop_done` exit and a unitary body
- **THEN** the verifier reports no `LOOP_AMBIGUOUS_BODY`

### Requirement: Loop Termination Reachability

The verifier SHALL, for a `[loop until: P]` adaptive loop, classify whether the exit predicate `P` can be checked statically, emitting `LOOP_TERMINATION_UNCHECKED` at warning severity (rather than rejecting) when it cannot.

The classification is by the context fields `P` references: a predicate over integer counters — and no floating-point field — is accepted; a predicate that involves a floating-point context field, or that references no bounded integer counter at all, cannot be checked statically and emits the warning, naming the predicate. No monotone-progress proof is attempted, because an integer counter may legitimately stall between iterations (e.g. Simon's `rank` on a linearly-dependent draw).

#### Scenario: Integer-counter predicate is accepted

- **WHEN** an adaptive loop's predicate is `rank >= n - 1` over integer context counters
- **THEN** the verifier emits no `LOOP_TERMINATION_UNCHECKED`

#### Scenario: Float predicate falls back to a warning

- **WHEN** an adaptive loop's predicate compares a `float` context field (e.g. `error < 0.01`)
- **THEN** the verifier emits `LOOP_TERMINATION_UNCHECKED` at warning severity naming the predicate

### Requirement: Backend-Dispatched Dynamic Verification

Stage 4b dynamic verification SHALL be parameterized by the selected
backend, resolved from (in priority order) the `--backend` CLI flag, the
config-file backend, and the `## assertion policy` `backend` field. Under
`backend: auto`, the verifier SHALL classify the machine and route a
Clifford machine to the stabilizer backend and any other machine to the
state-vector backend. A stabilizer backend SHALL implement the shipped
`BackendAdapter.verify(machine, options) -> (QVerificationResult,
BackendResult)` contract and produce a `QVerificationResult` of the same
shape as the state-vector backend. It reproduces the state-vector
backend's checks without an exponential cost: unitarity holds by
construction for Clifford gates; the dynamic entanglement check (von
Neumann entropy and Schmidt rank across the declared bipartitions) is
computed from the stabilizer tableau via the GF(2) rank of its check
matrix rather than by evolving a state vector; and the collapse-
completeness check is structural and backend-independent. When the
stabilizer dependency (Stim, then `AerSimulator(method="stabilizer")`)
is unavailable, resolution SHALL fall back to the state-vector backend
with a warning rather than failing.

#### Scenario: Clifford machine auto-routes to the stabilizer backend

- **WHEN** a Clifford machine is verified with `backend: auto` and a
  stabilizer simulator is available
- **THEN** Stage 4b runs on the stabilizer backend and the
  `BackendResult` names the stabilizer backend

#### Scenario: Non-Clifford machine auto-routes to state-vector

- **WHEN** a machine containing `Rz(theta)` at an arbitrary angle is
  verified with `backend: auto`
- **THEN** Stage 4b runs on the state-vector backend

#### Scenario: Stabilizer unavailable falls back to state-vector

- **WHEN** a Clifford machine is verified with `backend: auto` and neither
  Stim nor the Aer stabilizer method is installed
- **THEN** Stage 4b runs on the state-vector backend with a warning and
  verification still completes

#### Scenario: Entanglement verdict agrees across backends

- **WHEN** an entangled Clifford machine (e.g. a Bell or GHZ state) is
  verified on both the stabilizer and the state-vector backend
- **THEN** both backends report the same entanglement verdict and the same
  Schmidt rank for each declared bipartition

#### Scenario: Schmidt-rank invariant is evaluated on the tableau

- **WHEN** a Clifford machine declaring `schmidt_rank(q0, q1) >= 2` is
  verified on the stabilizer backend
- **THEN** the verifier evaluates the Schmidt rank from the tableau (not a
  state vector) and reaches the same verdict as the state-vector backend

> **Deferred:** the only invariant form with no stabilizer analogue is a
> `fidelity(|ψ>, target)` against a non-stabilizer target, and the
> `## invariants` grammar does not yet express fidelity invariants (roadmap
> §4.6, unshipped). An `INVARIANT_REQUIRES_STATEVECTOR` restriction is
> therefore unreachable in v1 and is deferred to the change that adds
> fidelity invariants — every invariant the current grammar supports
> (`entanglement`, `schmidt_rank`, `resource`) is computable on the tableau.

### Requirement: Reset Is A Recognized Effect

The verifier SHALL treat `reset(qs[i])` as a recognized structured effect, not as
a `custom` quantum gate — so a reset SHALL NOT raise `UNVERIFIED_UNITARITY` and
SHALL NOT be reported as a non-Clifford gate. The Ancilla Reset Lifecycle rule
SHALL key off the parsed `QEffectReset` node (its `ANCILLA_NOT_RESET` diagnostic
and behaviour are unchanged: an `ancilla` qubit reused across mid-circuit
measurements without an intervening reset still fails).

#### Scenario: Reset does not trigger an unverified-unitarity warning

- **WHEN** a machine contains an action whose effect is `reset(qs[0])`
- **THEN** the verifier emits no `UNVERIFIED_UNITARITY` for that reset

#### Scenario: Ancilla reset rule still satisfied by a parsed reset

- **WHEN** an `ancilla` qubit is measured, then `reset(qs[k])`, then measured
  again
- **THEN** the verifier emits no `ANCILLA_NOT_RESET`

