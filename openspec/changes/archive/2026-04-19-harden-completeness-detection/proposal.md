## Why

The verifier's completeness stage has a "quantum preparation path"
relaxation — linear measurement-bearing machines skip the
every-state-handles-every-event rule and only require each state to
handle its own next event. Today, whether a machine is *treated as* a
preparation path hinges on a substring check over event names:
`"measure" in e.name.lower() or "collapse" in e.name.lower() or
"readout" in e.name.lower()` (see
`q_orca/verifier/completeness.py::has_quantum_preparation_path`).

That works for the conventional naming (`measure_alice_x`,
`measure_s0`, `collapse`) but silently breaks on valid machines that
use other names for the same structural role — e.g., an event named
`read_error` whose action is literally `measure(qs[2]) -> bits[0]`.
The `PredictiveCoderMinimal` example written for the quantum predictive
coder research proposal hit exactly this case: its action is a
measurement, its structural shape is a single-path preparation chain,
but renaming the event from `read_error` to `measure_error` flipped
verification from INVALID (16 `INCOMPLETE_EVENT_HANDLING` errors) to
VALID without any structural change. Detecting preparation paths by
the *presence of a measurement effect* in transition actions is the
root-cause fix — the name happens to be a reliable proxy today only
because every existing example happens to spell it that way.

## What Changes

- Extend `has_quantum_preparation_path` in
  `q_orca/verifier/completeness.py` to union two detectors:
  1. The existing name-substring heuristic (for actionless transitions
     like `collapse` in `vqe-rotation.q.orca.md`).
  2. A new structural detector: for every transition with an action
     name, look up the `QActionSignature` in `machine.actions` and
     treat its event as a measurement event if the action has a
     non-None `measurement` or `mid_circuit_measure` field.
- Update the verifier spec (`openspec/specs/verifier/spec.md`) so the
  "measurement events" phrase used by the Completeness Check requirement
  is defined in terms of either a name match OR a measurement-bearing
  action, matching the new code.
- Add regression tests covering:
  - A machine with a mid-circuit-measurement action and no name match
    (e.g., event `read_error`) is classified as a preparation path.
  - A machine with both a name match and a measurement-bearing action
    is still classified (no regression on existing behavior).
  - A machine with no measurement events and no measurement actions is
    not classified as a preparation path (negative case unchanged).
  - `examples/predictive-coder-minimal.q.orca.md` (once merged) passes
    under both `read_error` and `measure_error` event names.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `verifier`: the Completeness Check's preparation-path classifier
  becomes structural-first with name-matching as a fallback. No other
  stage is affected.

## Impact

- `q_orca/verifier/completeness.py` — extend
  `has_quantum_preparation_path` to consider action effects. Small,
  localized change; no public API.
- `openspec/specs/verifier/spec.md` — update the Completeness Check
  requirement's language and add one new scenario.
- `tests/test_verifier.py` — add focused tests on
  `has_quantum_preparation_path` and on the end-to-end completeness
  behavior for both event-name and action-effect detection.
- No new runtime dependencies. No compiler, parser, or example-file
  changes required (the branch that adds
  `examples/predictive-coder-minimal.q.orca.md` is already named the
  now-supported way and continues to work; this change makes the
  structural alternative also acceptable).
