## Why

`add-stabilizer-sampling` shipped `compile_to_stim` but deliberately **refused**
multi-clause feedforward — real QEC syndrome decoding (`if b0 == 1 and b1 == 1:
X(...)`). That refusal is correct: a syndrome correction is a function of the
*whole* syndrome, computed by a classical **decoder**, not an in-circuit Clifford
`rec[-N]` control. This change adds that decoder path — the piece that makes
q-orca actually useful for error-correction work: encode a logical qubit, inject
noise, extract syndromes over rounds, decode with minimum-weight perfect
matching, and report the **logical error rate**. It also unblocks the two QEC
examples deferred from the sampling change.

## What Changes

- Add `compile_to_stim_with_detectors(machine) -> stim.Circuit` in
  `q_orca/compiler/stabilizer.py`: like `compile_to_stim`, but instead of
  refusing syndrome feedforward it emits Stim `DETECTOR` annotations on
  **stabilizer measurements** (measurements of qubits whose declared role is
  `ancilla` / `syndrome`, via the shipped `roles.qubits_with_role`) and
  `OBSERVABLE_INCLUDE` on the **logical readout** (the data-qubit measurements
  defining the logical operator). Noise comes from the machine's `## noise_model`
  section (without noise the syndrome is trivially zero — there is nothing to
  decode). **v1 is single-round (code-capacity):** one syndrome extraction over
  noisy data, each ancilla measurement its own detector. Multi-round /
  circuit-level decoding (cross-round detectors) needs `reset` between rounds,
  which q-orca lacks — deferred to a reset-syntax change (which also unblocks the
  `MR` deferred from the sampling change).
- Add a decoder over the detector error model: build the DEM via Stim's
  `circuit.detector_error_model(...)`, construct a PyMatching
  `Matching.from_detector_error_model(dem)`, and decode sampled syndromes to
  predicted logical flips (minimum-weight perfect matching).
- Add a benchmark helper `logical_error_rate(machine, shots, seed)` that samples
  detectors + observables under the declared noise, decodes each shot, and
  returns the logical error rate (fraction of shots whose decoded correction
  disagrees with the true logical observable).
- Unblock and author the two deferred QEC examples as decoder demonstrations:
  `examples/bit-flip-repeated.q.orca.md` (three syndrome rounds) and
  `examples/surface-code-3.q.orca.md` (distance-3 rotated surface code).

Out of scope: a Union-Find / correlated decoder (MWPM only); a live
`q-orca decode` CLI (a thin follow-on); wiring into `q-orca run`.

## Capabilities

### New Capabilities
<!-- none — extends compiler (detector emission) and evaluation (benchmark) -->

### Modified Capabilities
- `compiler`: add **Detector and Observable Emission** — a
  `compile_to_stim_with_detectors` target that annotates stabilizer measurements
  as detectors and the logical readout as an observable, replacing the refused
  multi-clause feedforward.
- `evaluation`: add a **Logical Error Rate Benchmark** — sample under the
  declared noise model, decode each shot's syndrome with PyMatching, and report
  the logical error rate.

## Impact

- New code: `compile_to_stim_with_detectors` + a `decode_syndromes` /
  `logical_error_rate` helper in `q_orca/compiler/stabilizer.py` (or a sibling
  `q_orca/evaluation/qec.py`); two example files.
- New optional dependency: `pymatching` (added to the `stabilizer` extra,
  detected at module load like `stim`; absence yields a clear "decoder
  unavailable" error rather than a crash).
- New tests: detector/observable annotation on a known code; logical error rate
  decreases with code distance / increases with physical error rate; the two
  examples decode.
- **Dependencies**: builds on shipped `compile_to_stim` (the gate/measurement
  walk), `is_clifford`, the **qubit-role tags** (`ancilla`/`syndrome`, from
  `add-qubit-role-types`), and the **`## noise_model`** section (the noise to
  decode). The detector-annotation mapping and the logical-observable definition
  are the highest-risk pieces (see design).
