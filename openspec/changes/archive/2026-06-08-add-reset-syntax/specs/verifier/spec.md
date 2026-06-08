## ADDED Requirements

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
