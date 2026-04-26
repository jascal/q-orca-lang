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
completeness, determinism, quantum (static), dynamic (QuTiP),
superposition leak. If the structural stage produces any error, later
stages SHALL be skipped. Otherwise, every non-skipped stage SHALL run
and their errors SHALL be merged into a single result.

#### Scenario: Structural failure halts the pipeline

- **WHEN** a machine has no `[initial]` state and no states at all
- **THEN** `verify()` returns a result whose only errors come from the
  structural stage and no other stages run

#### Scenario: Merged errors from multiple stages

- **WHEN** a valid machine declares a `## verification rules` bullet
  for `unitarity` and also has an orphan event
- **THEN** the result includes an `ORPHAN_EVENT` warning from the
  structural stage AND runs the Stage-4 unitarity check

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

