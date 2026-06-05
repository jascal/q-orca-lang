## Context

`add-stabilizer-sampling` shipped `compile_to_stim` (gates + `M` + single-clause
`rec[-N]` feedforward) and refuses multi-clause feedforward with a diagnostic
pointing here. The pieces this builds on are all shipped: `is_clifford`, the
gate/measurement walk in `compile_to_stim`, the qubit-role tags
(`roles.qubits_with_role(machine, "ancilla"|"syndrome")`), and the
`## noise_model` section (`QMachineDef.noise_model`). Stim 1.16 provides
`DETECTOR` / `OBSERVABLE_INCLUDE` and `circuit.detector_error_model()`;
PyMatching consumes the DEM directly.

The conceptual model (errors are chains, the syndrome is their endpoints,
decoding is minimum-weight perfect matching) is exactly what Stim's DEM + a
PyMatching `Matching` implement — Stim builds the matching graph, PyMatching runs
Edmonds' blossom algorithm.

## Goals / Non-Goals

**Goals:**
- Compile a noisy Clifford QEC machine to a Stim circuit with detectors +
  observable, decode sampled syndromes with MWPM, and report the logical error
  rate.
- Unblock `bit-flip-repeated` and `surface-code-3` as decoder demonstrations.

**Non-Goals:**
- Decoders other than MWPM (Union-Find, correlated/neural) — follow-ons.
- A `q-orca decode` CLI or `q-orca run` wiring — thin follow-ons.
- Inventing QEC syntax: detectors/observable are *inferred* from existing role
  tags + measurement structure, not a new section (Open Q1 revisits this).

## Decisions

### D1 — Stabilizer vs logical measurements come from role tags
A `measure(qs[i]) -> bits[j]` is a **stabilizer** measurement when `qs[i]` has
role `ancilla` or `syndrome` (`roles.role_of`), and a **logical readout** when
`qs[i]` has role `data`. Stabilizer measurements get `DETECTOR` annotations;
data measurements feed the `OBSERVABLE_INCLUDE`. A machine with no role tags
(all `data`) cannot be decoded — `compile_to_stim_with_detectors` raises a clear
error directing the user to tag ancilla/syndrome qubits.

### D2 — Detector definition (single- and multi-round)
A detector is a set of measurement records whose parity is deterministic absent
noise. For the **first** round, a freshly-prepared ancilla measuring a stabilizer
of the encoded state is deterministic, so each ancilla measurement record gets
its own `DETECTOR rec[-k]`. For **subsequent** rounds (the repeated
syndrome-extraction structure, recovered from the unrolled loop / repeated
actions), a detector compares the *same* stabilizer across consecutive rounds:
`DETECTOR rec[-k] rec[-k-stride]` — a flipped detector marks where an error
chain crosses between rounds. The compiler tracks, per stabilizer qubit, the
record index of its previous-round measurement to form the cross-round pair.

### D3 — Logical observable (the risk)
`OBSERVABLE_INCLUDE(0)` collects the measurement records that define the logical
operator — for a repetition/bit-flip code, the parity of the final data-qubit
measurements; for the surface code, the data measurements along a logical
boundary. v1 derives it from the data-qubit final measurements (logical-Z
readout). Getting this wrong silently inflates/deflates the logical error rate,
so it is pinned by D6's distance/noise sweep (a correct observable makes the
logical error rate *fall* with distance; a wrong one does not).

### D4 — Decode via the detector error model + PyMatching
`circuit.detector_error_model(decompose_errors=True)` yields the matching graph;
`pymatching.Matching.from_detector_error_model(dem)` builds the decoder.
`circuit.compile_detector_sampler(seed=...)` samples `(detectors, observables)`;
`matching.decode_batch(detectors)` predicts the logical flips; a shot is a
**logical error** when the prediction disagrees with the sampled observable.

### D5 — Optional dependency
`pymatching` joins the `stabilizer` extra, detected at module load like `stim`.
Absent, `logical_error_rate` / the decode path raise a clear
"decoder unavailable — pip install 'q-orca[stabilizer]'" error; nothing else
regresses.

### D6 — Validation by sweep, not a fixed number
A decoder is only meaningful under noise, and its correctness shows up as a
*trend*, not a single value. Tests assert the **direction**: the logical error
rate falls as code distance grows (at fixed sub-threshold physical error rate),
and rises with the physical error rate. This catches a wrong observable or
mis-paired detector (both of which flatten or invert the trend) without pinning a
brittle exact rate.

## Risks / Trade-offs
- **Detector cross-round pairing** off-by-one → flips the wrong detectors →
  decoder mispredicts. Mitigation: D6 trend tests + a single-round unit test
  asserting the exact emitted `DETECTOR` targets on a hand-checked code.
- **Wrong logical observable** → plausible-but-wrong logical error rate.
  Mitigation: the distance sweep (a wrong observable does not improve with
  distance).
- **Round structure recovery** from the action stream (which measurements form
  one round) — relies on the repeated syndrome-extraction actions / unrolled
  loop being regular (each round measures the same set of stabilizer qubits in
  the same order). Mitigation: derive rounds from repeated ancilla measurements
  of the same qubit; if the structure is irregular (a stabilizer qubit measured
  a different number of times than its peers), raise an **actionable** error —
  *"irregular syndrome rounds: stabilizer qubit q3 measured 2×, q5 measured 3×;
  express repeated rounds with a `[loop N]` body so every round is identical"* —
  rather than emit mis-paired detectors.
- **No measurements / mismatched records** — a machine with no stabilizer
  measurements, or a data readout that does not cover the logical operator,
  cannot define detectors/observable; `compile_to_stim_with_detectors` raises a
  located error rather than emit an empty or degenerate DEM.

## Migration Plan
Additive. `compile_to_stim_with_detectors` and `logical_error_rate` are new entry
points; `compile_to_stim` is unchanged (still refuses multi-clause, now with a
"use the decoder path" hint). The two examples are new files. Rollback = revert.

## Open Questions
1. **v2 priority:** an explicit `## logical_observable` declaration instead of
   inferring it from data-qubit measurements. v1 infers (logical-Z = parity of
   final data measurements), which is correct for repetition / bit-flip and a
   single logical-Z surface-code boundary; complex codes (multiple logical
   operators, logical-X readout) will need the explicit form. This is the most
   likely first follow-on once a code needs it.
2. Union-Find / correlated decoders as alternative backends to MWPM.
3. A `q-orca decode <file>` CLI + `q-orca run` wiring (sampler ergonomics,
   shared with the sampling change's Open Q1).
