## MODIFIED Requirements

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
