## Why

`reset` is the gap that bit the stabilizer work **three times**: the deferred
`MR` (measure-and-reset) in `add-stabilizer-sampling`, and multi-round /
circuit-level decoding in `add-stabilizer-decoder` (an ancilla can't be reused
across syndrome rounds without re-initialising it to |0⟩). Today `reset` is
half-supported and inconsistent: the verifier's **Ancilla Reset Lifecycle** rule
already requires and suggests `reset(qs[k])` (string-matched by regex), but the
parser swallows `reset(...)` as a `custom` gate — so any machine that resets is
classified **non-Clifford** (`is_clifford` rejects it), isn't compiled to Stim,
and isn't executed by the runtime. This change makes `reset` a first-class effect
and threads it through the classifier, compiler, and runtime — unblocking `MR`
and multi-round decoding.

## What Changes

- **Language / AST**: add a `reset(qs[i])` effect (a `QEffectReset(qubit_idx)`
  node on the action signature, mirroring `QEffectMeasure`) that re-initialises a
  qubit to |0⟩. The parser produces the structured node instead of a `custom`
  gate.
- **Verifier**: `reset` is recognised (no longer a `custom`/non-Clifford
  offender); the existing Ancilla Reset Lifecycle rule keys off the structured
  reset effect (keeping its `ANCILLA_NOT_RESET` diagnostic, now off the parsed
  node rather than a regex).
- **Classifier**: `is_clifford` treats `reset` as stabilizer-compatible (a reset
  is a valid stabilizer operation), so resetting machines route to the fast path.
- **`compile_to_stim`**: emit Stim `R` for a reset; a `measure(qs[i])`
  immediately followed by `reset(qs[i])` on the same qubit emits `MR`
  (measure-and-reset) — the **deferred `MR`** from the sampling change.
- **`compile_to_stim_with_detectors`**: enable **multi-round / circuit-level
  decoding** — with reset, an ancilla is re-initialised between rounds, so the
  compiler emits cross-round detectors (a stabilizer's record XOR its
  previous-round record), the piece deferred from the decoder change.
- **Runtime / backends**: the iterative runtime and the QuTiP / Qiskit backends
  execute `reset` (collapse + re-initialise the qubit to |0⟩).

## Capabilities

### New Capabilities
<!-- none — extends language, verifier, compiler, runtime -->

### Modified Capabilities
- `language`: add the `reset(qs[i])` effect to the gate-effect grammar.
- `verifier`: recognise `reset` as a structured effect; the Ancilla Reset
  Lifecycle rule keys off the parsed node.
- `compiler`: `reset` is Clifford-compatible; `R` / `MR` emission in
  `compile_to_stim`; cross-round detectors in `compile_to_stim_with_detectors`.
- `runtime`: execute `reset` (re-initialise to |0⟩) in the iterative runtime.

## Impact

- New AST node `QEffectReset`; parser `_parse_reset_from_effect`; classifier
  reset handling; `compile_to_stim` `R`/`MR`; `compile_to_stim_with_detectors`
  cross-round detectors; iterative-runtime + backend reset execution; the
  verifier role rule rewired to the parsed node.
- New tests: reset parses to `QEffectReset`; a resetting machine is Clifford;
  measure+reset → `MR`; multi-round repetition code decodes with cross-round
  detectors (logical error rate improves with rounds under measurement noise);
  the runtime re-initialises a reset qubit.
- New example: a multi-round QEC machine (now expressible) — e.g. promote the
  deferred `bit-flip-repeated` (3 syndrome rounds, ancilla reset between rounds).
- Backward compatible: machines that never `reset` are unchanged; the verifier's
  ancilla-reset diagnostic keeps firing (now off the parsed node).
- **Dependencies**: builds on shipped `compile_to_stim`,
  `compile_to_stim_with_detectors`, `is_clifford`, qubit roles, and the iterative
  runtime. **Risk**: the cross-round detector indexing (deferred precisely
  because it is fiddly) and the interaction with the existing ancilla-reset rule.
