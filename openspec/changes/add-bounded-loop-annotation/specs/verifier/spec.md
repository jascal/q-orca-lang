## ADDED Requirements

### Requirement: Loop Body Well-Formedness

The verifier SHALL identify each `[loop …]`-annotated state's loop body as the strongly-connected component entered through that state and exited via a `loop_done`-tagged transition, and SHALL emit `LOOP_AMBIGUOUS_BODY` at error severity when the body cannot be uniquely determined.

A body is ambiguous when two distinct `[loop …]`-annotated states share a cycle, when there are multiple back-edges to distinct annotated states, or (for v1) when a `[loop …]` body structurally contains another `[loop …]` state (nested loops are out of scope for v1). The existing per-transition unitarity check applies once over the body — a non-unitary action (e.g. a measurement) inside a fixed `[loop N]` body emits the existing `NON_UNITARY_ACTION` (since `U^N` is unitary iff `U` is); a measurement on the `loop_done` exit edge is outside the body and is allowed.

#### Scenario: Ambiguous body rejected

- **WHEN** two states are both annotated `[loop N]` with overlapping back-edges (a shared cycle)
- **THEN** the verifier emits `LOOP_AMBIGUOUS_BODY` naming the conflicting states

#### Scenario: Non-unitary action inside a fixed body rejected

- **WHEN** a `[loop 5]` body contains a `measure(...)` action on an in-body transition
- **THEN** the verifier emits `NON_UNITARY_ACTION` pointing at the measurement row

#### Scenario: Well-formed single-cycle body accepted

- **WHEN** a `[loop N]` state dominates exactly one cycle with a single `loop_done` exit and a unitary body
- **THEN** the verifier reports no `LOOP_AMBIGUOUS_BODY`

### Requirement: Loop Termination Reachability

The verifier SHALL, for a `[loop until: P]` adaptive loop, attempt to prove that `P` becomes satisfiable on some path through the body, emitting `LOOP_TERMINATION_UNCHECKED` at warning severity when it cannot (rather than rejecting).

When `P` is over bounded integer context counters the check is static (the counter must make monotone progress toward `P`); when `P` involves floating-point context fields the static proof is skipped and the warning is emitted, naming the predicate.

#### Scenario: Integer-counter predicate is checked

- **WHEN** an adaptive loop's predicate is `rank >= n - 1` over integer counters that the body increments
- **THEN** the verifier emits no `LOOP_TERMINATION_UNCHECKED`

#### Scenario: Float predicate falls back to a warning

- **WHEN** an adaptive loop's predicate compares a `float` context field (e.g. `error < 0.01`)
- **THEN** the verifier emits `LOOP_TERMINATION_UNCHECKED` at warning severity naming the predicate

## MODIFIED Requirements

### Requirement: Syndrome Measurement Completeness

The verifier SHALL enforce, automatically for every qubit tagged `syndrome`, that the qubit is measured on every cyclic path it participates in, emitting `SYNDROME_NOT_MEASURED` at error severity for a cycle that prepares but never measures it.

When the syndrome qubit's cycle is a `[loop …]`-annotated body, the check SHALL be the exact per-iteration form: the qubit MUST be measured within the annotated body on every path before the `loop_back` edge. When no loop annotation is present, the check uses the strongly-connected-component fallback: every cyclic SCC of the transition graph in which the syndrome qubit is acted upon SHALL contain at least one `measure(qs[k])` on it. The diagnostic SHALL carry an actionable suggestion (e.g. `measure the syndrome qubit q_k on every loop iteration before loop_back`).

#### Scenario: Annotated loop body without a per-iteration measure fails

- **WHEN** a `[loop N]` body acts on a `syndrome` qubit but has a path back to the loop entry that does not measure it
- **THEN** the verifier emits `SYNDROME_NOT_MEASURED` for that body

#### Scenario: Unannotated cycle uses the SCC fallback

- **WHEN** a syndrome qubit participates in a cyclic SCC with no `[loop …]` annotation
- **THEN** the verifier applies the SCC fallback (a measure anywhere in the SCC satisfies the check)
