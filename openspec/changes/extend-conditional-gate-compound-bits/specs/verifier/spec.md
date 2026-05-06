## MODIFIED Requirements

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
