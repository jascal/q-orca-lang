## ADDED Requirements

### Requirement: Reset Effect

The parser SHALL recognize `reset(qs[i])` as a first-class action effect that
re-initialises qubit `i` to |0⟩, producing a structured `QEffectReset(qubit_idx)`
on the action signature (mirroring `QEffectMeasure`) rather than a `custom`
quantum gate. An action effect MAY carry a measurement and a reset together (the
measure-and-reset form), and `reset` MAY appear as its own action.

#### Scenario: Reset parses to a structured effect

- **WHEN** an action effect is `reset(qs[1])`
- **THEN** the action's parsed `reset` is `QEffectReset(qubit_idx=1)` and the
  effect is not parsed as a `custom` gate

#### Scenario: Measure-and-reset in one effect

- **WHEN** an action effect is `measure(qs[3]) -> bits[0]; reset(qs[3])`
- **THEN** the action carries both a `QEffectMeasure(qubit_idx=3, bit_idx=0)` and
  a `QEffectReset(qubit_idx=3)`
