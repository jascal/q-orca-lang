## ADDED Requirements

### Requirement: Iterative-Machine Termination Warning

The verifier SHALL emit an `UNBOUNDED_CONTEXT_LOOP` warning when a
machine contains at least one action with a `QEffectContextUpdate`
effect AND no guard on any path from a context-update-bearing state
to a `[final]` state constrains loop depth. "Constrains loop depth"
is defined narrowly in v1: some guard on the relevant path compares
an `int`-typed context field to an integer literal with a bounding
operator (`<`, `<=`, `>`, `>=`).

The check SHALL run in the classical-context stage and SHALL respect
`VerifyOptions.skip_classical_context` (inherited from the archived
`add-classical-context-updates` change).

The severity SHALL be **warning**, not error. A user may legitimately
want to rely on the runtime's `iteration_ceiling` safety net rather
than encode a termination bound in the machine itself; the warning
makes the choice explicit without blocking verification.

#### Scenario: QPC learning loop verifies without warning

- **WHEN** a machine has a back-edge to a prior state, a guard
  `ctx.iteration < max_iter` on the transition into `[final]`, and
  `gradient_step` action that mutates `iteration += 1`
- **THEN** the verifier emits no `UNBOUNDED_CONTEXT_LOOP` warning

#### Scenario: Unbounded context loop warns

- **WHEN** a machine has a context-update action and a back-edge
  but no `int`-field bounding guard on any path to a `[final]`
  state
- **THEN** the verifier emits `UNBOUNDED_CONTEXT_LOOP` at warning
  severity and the machine still verifies (warning, not error)

#### Scenario: list<float>-only guards do not count

- **WHEN** a machine has a context-update action, a back-edge, and
  the only guards reference `list<float>` element values (not an
  `int` counter)
- **THEN** the verifier emits `UNBOUNDED_CONTEXT_LOOP` — v1's
  conservative analysis does not treat float-element guards as a
  termination bound

#### Scenario: skip_classical_context suppresses the warning

- **WHEN** `VerifyOptions.skip_classical_context` is set and a
  machine would otherwise trigger `UNBOUNDED_CONTEXT_LOOP`
- **THEN** the warning is not emitted (the entire
  classical-context stage is skipped, as with the existing
  archived-change checks)
