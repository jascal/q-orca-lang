## 1. Dependency

- [ ] 1.1 Add `pymatching` to the `stabilizer` extra in `pyproject.toml`; detect
  it at module load (mirror the `stim` `AVAILABLE` pattern).

## 2. Detector + observable emission

- [ ] 2.1 Classify each `measure(qs[i]) -> bits[j]` by role via
  `roles.role_of(machine, i)`: `ancilla`/`syndrome` → stabilizer (detector),
  `data` → logical readout (observable). Raise actionable, located errors on the
  edge cases: no `ancilla`/`syndrome` roles ("add roles: ancilla/syndrome to your
  stabilizer qubits"), no stabilizer measurements, and a data readout that
  doesn't cover the logical operator.
- [ ] 2.2 `compile_to_stim_with_detectors(machine) -> stim.Circuit`: reuse the
  `compile_to_stim` gate/measurement/noise walk; emit `DETECTOR` per stabilizer
  measurement and `OBSERVABLE_INCLUDE(0)` over the data-readout records.
- [ ] 2.3 Cross-round detectors: track each stabilizer qubit's previous-round
  record; round ≥ 2 emits `DETECTOR rec[-k] rec[-k-stride]` (parity of
  consecutive rounds). Derive the round structure from repeated ancilla
  measurements (unrolled loop); raise the actionable irregular-rounds error
  (name the offending qubit, suggest a `[loop N]` body) if rounds aren't uniform.

## 3. Decoder

- [ ] 3.1 Build the detector error model:
  `circuit.detector_error_model(decompose_errors=True)`.
- [ ] 3.2 `pymatching.Matching.from_detector_error_model(dem)`; decode sampled
  detector batches → predicted logical flips.

## 4. Benchmark

- [ ] 4.1 `logical_error_rate(machine, shots, seed)` in `q_orca/evaluation/qec.py`:
  `compile_detector_sampler(seed)` → `(detectors, observables)`; decode; rate =
  fraction where prediction ≠ observable. Clear "decoder unavailable" error when
  PyMatching is absent.

## 5. Examples (now unblocked)

- [ ] 5.1 `examples/bit-flip-repeated.q.orca.md`: 3 syndrome rounds, ancilla
  role-tagged, with a `## noise_model` so there is something to decode.
- [ ] 5.2 `examples/surface-code-3.q.orca.md`: distance-3 rotated surface code,
  one+ stabilizer round, role-tagged + noise.

## 6. Tests

- [ ] 6.1 Detector emission: an `ancilla` measurement emits a `DETECTOR` over its
  record (assert exact target); a `data` measurement feeds `OBSERVABLE_INCLUDE`.
- [ ] 6.2 Edge-case diagnostics: untagged machine raises "tag syndrome qubits";
  irregular rounds raises the actionable `[loop N]` error; no-measurements raises.
- [ ] 6.3 Cross-round detectors on a real multi-round example: assert the exact
  emitted `DETECTOR rec[-k] rec[-k-stride]` strings pairing consecutive rounds.
- [ ] 6.4 Reproducibility: `logical_error_rate` is identical across two runs at a
  fixed seed.
- [ ] 6.5 Trend — distance: logical error rate falls with code distance at a fixed
  sub-threshold physical error rate (the observable-correctness gate).
- [ ] 6.6 Trend — noise: logical error rate rises with the physical error rate.
- [ ] 6.7 Decoder-unavailable path raises the structured error (monkeypatch
  PyMatching absent).
- [ ] 6.8 The two examples compile-with-detectors and decode end-to-end.
- [ ] 6.9 Mark the decode tests `skipif`-no-`pymatching` (and the multi-shot
  trend sweeps slow / low-shot-in-fast-CI), mirroring the stim/qutip test gating.

## 7. Docs

- [ ] 7.1 Add a "Decoding" section to `docs/language/stabilizer-backend.md`:
  role-tagged detectors, the observable, `logical_error_rate`, the
  errors→chains→endpoints→MWPM model, and a short **end-to-end snippet**
  (encode → sample+decode → logical error rate). Update the multi-clause note to
  point here.
