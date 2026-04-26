## MODIFIED Requirements

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

## ADDED Requirements

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
