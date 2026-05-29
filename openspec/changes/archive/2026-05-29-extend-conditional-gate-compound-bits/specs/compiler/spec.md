## ADDED Requirements

### Requirement: Conditional gate compilation

The OpenQASM 3.0 emitter SHALL serialize a `QEffectConditional` with
N conditions as `if (<clause_1> && <clause_2> && … && <clause_N>) {
<gate>; }`, where each clause is `c[i]` for value `1` and `!c[i]`
for value `0` — matching the bare-bit / negated-bit shape already
used for single-condition emit. Single-condition effects SHALL emit
`if (c[i]) { <gate>; }` or `if (!c[i]) { <gate>; }` (unchanged).
Conditions SHALL appear in the order declared in the source.

The Qiskit emitter SHALL serialize a `QEffectConditional` with N
conditions as N nested `with qc.if_test((c[i_k], v_k)):` blocks,
with the gate call inside the innermost block. Single-condition
effects SHALL emit a single `with qc.if_test(...)` block (unchanged).

Resource estimation SHALL count a compound conditional gate as a
single gate of the underlying gate type — the conjunction is
classical control flow and SHALL NOT inflate `gate_count`,
`cx_count`, or `t_count` past the count of the gate inside the
conditional.

#### Scenario: OpenQASM emits compound condition

- **GIVEN** an action with effect
  `if bits[0] == 1 and bits[1] == 1: X(qs[1])`
- **WHEN** the OpenQASM compiler emits the action body
- **THEN** the output contains `if (c[0] && c[1]) { x q[1]; }`

#### Scenario: OpenQASM emits mixed-value compound condition

- **GIVEN** an action with effect
  `if bits[0] == 1 and bits[1] == 0: X(qs[0])`
- **WHEN** the OpenQASM compiler emits the action body
- **THEN** the output contains `if (c[0] && !c[1]) { x q[0]; }`

#### Scenario: OpenQASM emits single-condition unchanged

- **GIVEN** an action with effect `if bits[0] == 1: X(qs[0])`
- **WHEN** the OpenQASM compiler emits the action body
- **THEN** the output contains `if (c[0]) { x q[0]; }`

#### Scenario: Qiskit emits nested if_test blocks

- **GIVEN** an action with effect
  `if bits[0] == 1 and bits[1] == 1: X(qs[1])`
- **WHEN** the Qiskit compiler emits the action body
- **THEN** the output contains a `with qc.if_test((c[0], 1)):`
  block, nested inside which is `with qc.if_test((c[1], 1)):` whose
  body is `qc.x(q[1])`

#### Scenario: Resource estimation counts compound conditional as one gate

- **GIVEN** a machine where a single transition fires
  `if bits[0] == 1 and bits[1] == 0 and bits[2] == 1: X(qs[3])`
- **WHEN** resource estimation runs
- **THEN** the contribution to `gate_count` is 1, not 3
