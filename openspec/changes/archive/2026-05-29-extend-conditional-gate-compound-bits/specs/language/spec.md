## ADDED Requirements

### Requirement: Conditional gate effects

A conditional gate effect SHALL be of the form
`if <condition> [and <condition> [and …]] : <gate>` where each
`<condition>` is `bits[<int>] == <0|1>`. The parser SHALL produce a
single `QEffectConditional` whose `conditions` attribute is the
ordered list of `(bit_idx, value)` pairs and whose `gate` attribute
is the parsed `<gate>`.

The legacy single-condition form (`if bits[i] == v: gate`) SHALL
parse to a `QEffectConditional` with a one-element `conditions`
list. The legacy `bit_idx` and `value` attributes SHALL remain
populated from `conditions[0]` for backward compatibility with
read-only consumers.

Whitespace around `==`, `and`, `:`, `[`, and `]` SHALL be flexible
(zero or more spaces). The keyword `and` SHALL be lowercase.

A conditional gate effect that lists the same `bits[i]` index twice
with conflicting values SHALL be rejected as a parse error citing
the offending bit index and both declared values.

#### Scenario: Single-condition form parses unchanged

- **WHEN** an action declares `if bits[0] == 1: X(qs[0])`
- **THEN** the parser produces a `QEffectConditional` with
  `conditions == [(0, 1)]`, `bit_idx == 0`, and `value == 1`

#### Scenario: AND-conjoined two-bit condition

- **WHEN** an action declares `if bits[0] == 1 and bits[1] == 1: X(qs[1])`
- **THEN** the parser produces a `QEffectConditional` with
  `conditions == [(0, 1), (1, 1)]` and the gate parsed normally

#### Scenario: Mixed-value AND-conjoined condition

- **WHEN** an action declares `if bits[0] == 1 and bits[1] == 0: X(qs[0])`
- **THEN** the resulting `conditions == [(0, 1), (1, 0)]`

#### Scenario: Three-bit AND-conjoined condition

- **WHEN** an action declares
  `if bits[0] == 1 and bits[1] == 0 and bits[2] == 1: X(qs[3])`
- **THEN** the resulting `conditions == [(0, 1), (1, 0), (2, 1)]`

#### Scenario: Conflicting clauses are rejected

- **WHEN** an action declares
  `if bits[0] == 1 and bits[0] == 0: X(qs[0])`
- **THEN** the parser raises a parse error naming `bits[0]` and the
  conflicting values `1` and `0`

#### Scenario: Whitespace flexibility

- **WHEN** an action declares
  `if bits[0]==1  and  bits[1] == 1: X(qs[1])`
- **THEN** the parser produces the same `QEffectConditional` as the
  canonical single-spaced form
