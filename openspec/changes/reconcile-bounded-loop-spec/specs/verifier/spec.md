## MODIFIED Requirements

### Requirement: Loop Body Well-Formedness

The verifier SHALL identify each `[loop …]`-annotated state's loop body as the strongly-connected component entered through that state and exited via a `loop_done`-tagged transition, and SHALL emit `LOOP_AMBIGUOUS_BODY` at error severity when the body cannot be uniquely determined.

A body is ambiguous when two distinct `[loop …]`-annotated states share a cycle, when there are multiple back-edges to distinct annotated states, or (for v1) when a `[loop …]` body structurally contains another `[loop …]` state (nested loops are out of scope for v1).

The per-transition unitarity check applies once over a **fixed** `[loop N]` body — a non-unitary action (e.g. a measurement) inside a fixed body emits `NON_UNITARY_ACTION` (since `U^N` is unitary iff `U` is); a measurement on the `loop_done` exit edge is outside the body and is allowed. An **adaptive** `[loop until: …]` body is **exempt** from this unitarity check: its per-iteration measurement on the `loop_back` edge is how the classical exit predicate advances, so a measurement inside an adaptive body does not emit `NON_UNITARY_ACTION`.

#### Scenario: Ambiguous body rejected

- **WHEN** two states are both annotated `[loop N]` with overlapping back-edges (a shared cycle)
- **THEN** the verifier emits `LOOP_AMBIGUOUS_BODY` naming the conflicting states

#### Scenario: Non-unitary action inside a fixed body rejected

- **WHEN** a `[loop 5]` body contains a `measure(...)` action on an in-body transition
- **THEN** the verifier emits `NON_UNITARY_ACTION` pointing at the measurement row

#### Scenario: Measurement inside an adaptive body allowed

- **WHEN** a `[loop until: P]` body measures a qubit on its `loop_back` edge each iteration
- **THEN** the verifier emits no `NON_UNITARY_ACTION` — the adaptive body is exempt

#### Scenario: Well-formed single-cycle body accepted

- **WHEN** a `[loop N]` state dominates exactly one cycle with a single `loop_done` exit and a unitary body
- **THEN** the verifier reports no `LOOP_AMBIGUOUS_BODY`

### Requirement: Loop Termination Reachability

The verifier SHALL, for a `[loop until: P]` adaptive loop, classify whether the exit predicate `P` can be checked statically, emitting `LOOP_TERMINATION_UNCHECKED` at warning severity (rather than rejecting) when it cannot.

The classification is by the context fields `P` references: a predicate over integer counters — and no floating-point field — is accepted; a predicate that involves a floating-point context field, or that references no bounded integer counter at all, cannot be checked statically and emits the warning, naming the predicate. No monotone-progress proof is attempted, because an integer counter may legitimately stall between iterations (e.g. Simon's `rank` on a linearly-dependent draw).

#### Scenario: Integer-counter predicate is accepted

- **WHEN** an adaptive loop's predicate is `rank >= n - 1` over integer context counters
- **THEN** the verifier emits no `LOOP_TERMINATION_UNCHECKED`

#### Scenario: Float predicate falls back to a warning

- **WHEN** an adaptive loop's predicate compares a `float` context field (e.g. `error < 0.01`)
- **THEN** the verifier emits `LOOP_TERMINATION_UNCHECKED` at warning severity naming the predicate
