## ADDED Requirements

### Requirement: Classical Context Update — Scalar Numeric Typing

The verifier SHALL accept a scalar (non-indexed) `+=` / `-=` context-update target whose declared type is any numeric scalar — `int` or `float` — and SHALL reject only non-numeric scalar targets with `CONTEXT_FIELD_TYPE_MISMATCH`.

This relaxes the earlier `int`-only rule for scalar targets. The runtime's context-update interpreter already performs `float` arithmetic, and the field-reference RHS rule already admits `int` or `float`; restricting the scalar LHS to `int` was stricter than the runtime and made a learnable bare-scalar angle unusable (it must be both a rotation-gate argument and a mutation target, and list-index angles do not resolve in the circuit builder). Indexed (`list<float>`) targets and the bit-condition / index-bounds / undeclared-field rules are unchanged.

#### Scenario: Scalar float target accepted

- **WHEN** a machine declares `| theta_0 | float | 0.5 |` and an action's effect is `if bits[0] == 1: theta_0 -= eta else: theta_0 += eta`
- **THEN** the verifier reports no `CONTEXT_FIELD_TYPE_MISMATCH` for `theta_0`

#### Scenario: Scalar int target still accepted

- **WHEN** a machine declares `| iteration | int | 0 |` and an action's effect is `iteration += 1`
- **THEN** the verifier reports no `CONTEXT_FIELD_TYPE_MISMATCH` for `iteration`

#### Scenario: Non-numeric scalar target still rejected

- **WHEN** a machine declares `| label | string | "x" |` and an action's effect is `label += 1`
- **THEN** the verifier emits `CONTEXT_FIELD_TYPE_MISMATCH` at error severity
