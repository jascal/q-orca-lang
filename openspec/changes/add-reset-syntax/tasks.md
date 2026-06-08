## 1. Language / AST / parser

- [x] 1.1 Add `QEffectReset(qubit_idx)` to `q_orca/ast.py` and a
  `reset: Optional[QEffectReset]` field on the action signature (mirror
  `mid_circuit_measure`).
- [x] 1.2 Parser `_parse_reset_from_effect`: recognise `reset(qs[k])` → set the
  action's `reset`; the gate parser no longer emits a `custom` gate for `reset`.
  An effect may carry both a measure and a reset.

## 2. Classifier / verifier

- [x] 2.1 `is_clifford`: treat `reset` as stabilizer-compatible (skip, like a
  measurement) — a resetting machine is Clifford.
- [x] 2.2 Verifier: `reset` no longer raises `UNVERIFIED_UNITARITY` (not a custom
  gate); rewire the Ancilla Reset Lifecycle rule (`roles.py`) to key off the
  parsed `QEffectReset` node, keeping `ANCILLA_NOT_RESET` behaviour (regex kept
  only as a deprecated fallback).

## 3. compile_to_stim — R / MR

- [x] 3.1 Emit Stim `R i` for `reset(qs[i])`.
- [x] 3.2 Coalesce a `measure(qs[i])` immediately followed by `reset(qs[i])` (same
  qubit, nothing between) into a single `MR i`; the `bit → record` map and
  `rec[-N]` feedforward indexing stay unchanged (`MR` advances one record like `M`).

## 4. compile_to_stim_with_detectors — multi-round

- [x] 4.1 Track each stabilizer qubit's previous-round measurement record; round 1
  emits a single-record `DETECTOR`, round ≥ 2 emits a cross-round
  `DETECTOR rec[r_now] rec[r_prev]`. Recover the round structure from the unrolled
  `[loop N]` body; raise the actionable irregular-rounds error otherwise.

## 5. Runtime / backends

- [x] 5.1 Iterative runtime executes `reset` (re-initialise the qubit to |0⟩); the
  QuTiP / Qiskit dynamic paths apply a reset (project to |0⟩).

## 6. Example

- [ ] (DEFERRED → quick follow-on; capability test-validated via a generated machine) 6.1 `examples/bit-flip-repeated.q.orca.md`: 3 syndrome rounds with ancilla
  `reset` between rounds (the example deferred from add-stabilizer-decoder), with
  a `## noise_model` including measurement (`readout_error`) so multi-round helps.

## 7. Tests

- [x] 7.1 Parser: `reset(qs[1])` → `QEffectReset`; measure+reset in one effect →
  both nodes; not a `custom` gate.
- [x] 7.2 Classifier: a resetting machine is Clifford; verifier emits no
  `UNVERIFIED_UNITARITY` for reset; the Ancilla Reset Lifecycle scenarios stay green.
- [x] 7.3 `compile_to_stim`: `reset` → `R`; measure-then-reset → `MR` (assert the
  exact instruction); two-action measure / reset → `M` then `R`.
- [x] 7.4 Multi-round detectors: assert the exact cross-round `DETECTOR rec[..] rec[..]`
  on a 2-round repetition code.
- [x] 7.5 Multi-round decoding: under `readout_error`, the logical error rate of a
  repetition code improves with more rounds (the cross-round-detector signature).
- [x] 7.6 Runtime: a reset re-initialises a |1⟩ qubit to |0⟩ (measurement yields 0).

## 8. Docs

- [x] 8.1 Document `reset(qs[i])` in `docs/language/`; update the stabilizer
  backend doc's `MR`/multi-round notes (now shipped) and the deferred-MR /
  cross-round notes in the sampling + decoder docs.
