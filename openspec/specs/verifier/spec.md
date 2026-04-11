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
`H, X, Y, Z, CNOT, CZ, SWAP, T, S, Rx, Ry, Rz, CCNOT, CSWAP` as
known-unitary; any `custom` gate SHALL produce an
`UNVERIFIED_UNITARITY` warning. Gate target or control indices at or
beyond the inferred qubit count SHALL produce
`QUBIT_INDEX_OUT_OF_RANGE`. A controlled gate whose control and target
sets overlap SHALL produce `CONTROL_TARGET_OVERLAP`.

#### Scenario: Out-of-range qubit

- **WHEN** a 2-qubit machine has an action `X(qs[5])`
- **THEN** the verifier emits `QUBIT_INDEX_OUT_OF_RANGE` at error severity

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

#### Scenario: No entanglement when expected

- **WHEN** a machine declares `entanglement(q0, q1) = True` but the
  simulated circuit produces a product state
- **THEN** the verifier emits `DYNAMIC_NO_ENTANGLEMENT` at error severity

#### Scenario: QuTiP unavailable

- **WHEN** `qutip` cannot be imported
- **THEN** the dynamic stage returns a passing result with no errors

### Requirement: Superposition Leak Detection

The verifier SHALL infer superposition states from their expressions,
names, or incoming gates (`H`, `Rx`, `Ry`, `Rz`, `CNOT`, `CZ`,
`SWAP`, `CCNOT`, `CSWAP`). For each superposition state it SHALL
warn when measurement transitions leave the state unguarded to a
non-final target, or when a collapse-sensitive gate moves the machine
to a non-superposition state.

#### Scenario: Unguarded measurement from a superposition state

- **WHEN** a state `|+>` has an outgoing measurement transition with
  no probability guard and the target is not final
- **THEN** the verifier emits a `SUPERPOSITION_LEAK` warning

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
