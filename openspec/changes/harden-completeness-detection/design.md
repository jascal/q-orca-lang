## Context

The verifier's Completeness Check normally enforces that every
`(state, event)` pair in a machine has at least one transition.
Quantum preparation-path machines — linear measurement-bearing chains
that prepare, entangle, and measure in sequence — don't fit that
model, so `has_quantum_preparation_path` in
`q_orca/verifier/completeness.py` relaxes the rule when:

1. The machine has at least one "measurement event" AND
2. More than 50% of its non-final states have exactly one outgoing
   transition.

Today condition (1) is evaluated by lowercasing the event name and
checking whether any of the substrings `measure`, `collapse`, or
`readout` appear. This proxy works for every shipped example because
they all follow the naming convention, but it is not a property of
the machine's semantics — it is a property of its spelling.

The proposal surfaced a concrete failure: the
`PredictiveCoderMinimal` example has a measurement-bearing action
(`measure(qs[2]) -> bits[0]`) attached to an event named
`read_error`. Structurally it is a preparation path, but because
`read_error` misses the substring set, completeness fires 16
`INCOMPLETE_EVENT_HANDLING` errors. Renaming the event to
`measure_error` flips the verdict to VALID without any structural
change. That name dependence is the defect we want to remove.

## Goals / Non-Goals

**Goals:**

- Detect preparation paths by the *presence of a measurement in a
  transition's action*, not just by event name.
- Keep the existing name-based heuristic as a fallback so current
  machines (e.g., `vqe-rotation.q.orca.md`'s actionless `collapse`
  event) keep passing.
- No change to the >50% single-outgoing rule — that second condition
  is untouched.
- Update the verifier spec so "measurement events" is defined
  consistently with the code.
- Add targeted regression tests that pin both detection paths and
  guard against silent regressions if the heuristic is tightened
  later.

**Non-Goals:**

- Not redesigning the completeness stage, its error codes, or the
  >50% threshold.
- Not changing the public verifier API or `VerifyOptions`.
- Not relaxing completeness for general non-linear measurement
  machines — the preparation-path shape still has to hold.
- Not producing a full taxonomy of "quantum machine shapes" —
  preparation paths stay the only recognized relaxation.

## Decisions

### Detect measurement events by action effect, union with name match

Replace the single name-substring check with a union:

```
event_is_measurement(e) =
    name_matches_measurement(e)  OR  any_action_on_e_has_measurement_effect(e)
```

Where `any_action_on_e_has_measurement_effect(e)` iterates
`machine.transitions` filtered to `t.event == e.name`, looks up each
`t.action` in `machine.actions` (already a `Dict[str, QActionSignature]`
on the parsed AST), and returns true if any looked-up action has a
non-None `measurement` or `mid_circuit_measure` field.

The `QActionSignature` dataclass already carries those fields
(`q_orca/ast.py`) and `q_orca/parser/markdown_parser.py` already
populates them from effect-string parsing — we're reading state the
parser already produces, not inventing new AST.

**Alternatives considered:**

- *Pure structural detection (drop name matching entirely).* Rejected
  because actionless transitions (e.g., the `collapse` event in
  `vqe-rotation.q.orca.md`, which has no associated action) have no
  `QActionSignature` to inspect. Removing the name check would
  regress that file. Keeping it as a fallback is cheaper than
  inventing a second structural signal.

- *Event-level annotation (e.g., `## events` carries a flag).*
  Rejected because it requires a syntax change and adds surface area
  for no user-visible benefit. The existing action AST already tells
  us everything we need.

- *Classify actions by effect-string regex.* Rejected because the
  parser already tokenizes effect strings into structured
  `Measurement` / `QEffectMeasure` objects — scanning raw strings
  would duplicate work and miss parser-level edge cases the existing
  tokenization already handles.

### Keep both signals in a union (OR), not an intersection

Structural-only would regress `vqe-rotation.q.orca.md`. Name-only is
the status quo bug. The union is strictly more permissive than
either alone: every machine that passes today continues to pass, and
machines with measurement-bearing actions on non-conventional event
names newly pass.

### Scope boundary: do not touch the >50% single-outgoing rule

The second half of `has_quantum_preparation_path` (the >50% check)
is orthogonal to the detection bug. Leaving it as-is keeps the
change minimal and keeps blast radius to just the measurement-event
test.

## Risks / Trade-offs

- **[Risk]** A machine that *happens* to invoke a measurement in a
  non-measurement conceptual role (e.g., a mid-circuit ancilla reset
  implemented as `measure`) could get its event treated as a
  measurement event and relax completeness where it shouldn't. →
  **Mitigation:** the second condition (>50% single-outgoing) still
  has to hold. A machine with branching behavior won't be
  misclassified just because one of its actions measures — it will
  fail the structural majority test.

- **[Risk]** Future actions that should count as "measurements"
  (e.g., channel-based noisy measurement) land as a different AST
  field and the detector silently misses them. → **Mitigation:** the
  regression tests anchor on the two currently-parsed fields
  (`measurement`, `mid_circuit_measure`); any new measurement-style
  AST node added later will need an explicit test update, which is
  the right place to notice this.

- **[Trade-off]** The detector now takes `O(|transitions|)` instead
  of `O(|events|)` on the relaxation path. The absolute cost is
  negligible for machines we see (<100 transitions), and we only run
  during completeness — not in a hot loop.

## Migration Plan

No user-facing migration. No existing machines change verdict. New
machines with measurement-bearing actions on custom-named events
newly pass. Rollback is a one-function revert in
`q_orca/verifier/completeness.py` if something surprising surfaces.

## Open Questions

None. The AST fields involved (`measurement`, `mid_circuit_measure`)
are stable and already used elsewhere in the compiler/verifier, so
reading them here doesn't introduce a new contract.
