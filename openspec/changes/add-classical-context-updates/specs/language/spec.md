## ADDED Requirements

### Requirement: Context-Update Effect Grammar

The parser SHALL accept a new form in the Effect column of the
`## actions` table that mutates numeric context fields, optionally
gated on a classical bit condition. The grammar is:

```
<effect>    ::= <mutation>
              | if <bit_cond>: <mut_seq> [else: <mut_seq>]
<mut_seq>   ::= <mutation> (; <mutation>)*
<mutation>  ::= <lhs> <op> <rhs>
<lhs>       ::= <ident> | <ident>[<int_literal>]
<op>        ::= = | += | -=
<rhs>       ::= <int_literal> | <float_literal> | <ident>
<bit_cond>  ::= bits[<int_literal>] == (0 | 1)
```

A parsed context-update effect SHALL produce a
`QEffectContextUpdate` AST node stored on the action's
`context_update` field. An action with a context-update effect
SHALL NOT also carry a `gate`, `measurement`, `mid_circuit_measure`,
or `conditional_gate` — mixed-kind effects are a parse error in v1.

#### Scenario: Unconditional scalar increment

- **WHEN** an actions table row is
  `| tick | (ctx) -> ctx | iteration += 1 |`
- **THEN** the action's `context_update` is
  `QEffectContextUpdate(bit_idx=None, bit_value=None,
   then_mutations=[QContextMutation(target_field="iteration",
   target_idx=None, op="+=", rhs_literal=1, rhs_field=None)],
   else_mutations=[])`

#### Scenario: Conditional list-element update with context RHS

- **WHEN** an actions table row is
  `| gradient_step | (ctx) -> ctx | if bits[0] == 1: theta[0] -= eta else: theta[0] += eta |`
- **THEN** the action's `context_update` has `bit_idx=0`,
  `bit_value=1`, one `then_mutation` with `target_field="theta"`,
  `target_idx=0`, `op="-="`, `rhs_field="eta"`, and one
  `else_mutation` that is the `+=` counterpart

#### Scenario: Mixed gate and context update rejected

- **WHEN** an actions table row is
  `| bad | (qs, ctx) -> (qs, ctx) | H(qs[0]); iteration += 1 |`
- **THEN** the parser emits a structured error indicating that
  gate and context-update effects cannot be combined in one action

#### Scenario: Malformed LHS rejected

- **WHEN** an actions table row has effect `qubits[0] += 1`
- **THEN** the parser emits a structured error — `qubits` is a
  `list<qubit>` field and SHALL NOT be a context-update target
