## Context

`reset` is referenced across the codebase but never made first-class. The
verifier's Ancilla Reset Lifecycle rule (`q_orca/verifier/roles.py`) detects it
with a regex `reset\s*\(\s*qs\[(\d+)\]` and requires it between successive
ancilla measurements (`ANCILLA_NOT_RESET`). But the effect parser turns
`reset(qs[i])` into a `custom` `QuantumGate`, so `is_clifford` flags it
non-Clifford (offender `RESET`), `compile_to_stim` would reject it, and the
runtime has no reset semantics. Measurement is the model to mirror: a
`measure(qs[i]) -> bits[j]` parses into `QEffectMeasure(qubit_idx, bit_idx)` on
the action signature (`q_orca/ast.py`), walked by every compiler/runtime path.

This change was scoped by two prior findings: the deferred `MR` in
`add-stabilizer-sampling` (D2: no reset syntax → `M` only) and single-round-only
decoding in `add-stabilizer-decoder` (D2/Open Q0: cross-round detectors need
reset between rounds).

## Goals / Non-Goals

**Goals:**
- A first-class `reset(qs[i])` effect: parsed, classified Clifford-compatible,
  compiled (`R` / `MR`), and executed.
- Unblock `MR` (sampling) and multi-round / circuit-level decoding (decoder).

**Non-Goals:**
- `reset` to a non-|0⟩ state, or conditional reset (`if …: reset`) — v1 is the
  unconditional reset-to-|0⟩ used by syndrome extraction.
- New decoders or observable syntax (separate follow-ons).

## Decisions

### D1 — `QEffectReset` mirrors `QEffectMeasure`
Add `QEffectReset(qubit_idx)` to `q_orca/ast.py` and a `reset: Optional[QEffectReset]`
field on the action signature. The parser gains `_parse_reset_from_effect`
(alongside `_parse_mid_circuit_measure_from_effect`) recognising
`reset(qs[k])`; the gate parser no longer emits a `custom` gate for it. An effect
may carry both a measure and a reset (the `MR` case) — see D3.

### D2 — Classifier and verifier
`is_clifford` treats `reset` as stabilizer-compatible (skip it, like a
measurement — it is not a unitary gate but is a valid stabilizer operation), so
resetting machines reach the fast path. The Ancilla Reset Lifecycle rule
(`roles.py`) switches from the regex to the parsed `QEffectReset` node (the
diagnostic `ANCILLA_NOT_RESET` and its suggestion are unchanged); the regex stays
only as a deprecated fallback for un-migrated text, removed once examples migrate.

### D3 — `compile_to_stim`: `R` and `MR`
A reset emits Stim `R i`. A `measure(qs[i]) -> bits[j]` whose action (or the
immediately-following action) also resets `qs[i]` emits `MR i` (measure-and-reset)
as a single instruction, advancing the measurement record exactly as `M` did —
so the `bit → record` map and the `rec[-N]` feedforward indexing are unchanged.
This is the deferred `MR` from the sampling change; its one change-point is the
measurement-emission branch already commented for this purpose.

### D4 — `compile_to_stim_with_detectors`: cross-round detectors (the risk)
With reset, the same ancilla is measured once per round (re-initialised between
rounds via `MR`). The compiler tracks, per stabilizer qubit, the record index of
its **previous-round** measurement. Round 1 emits a single-record detector
(`DETECTOR rec[-1]`, as today). Round ≥ 2 emits a **cross-round** detector
`DETECTOR rec[r_now] rec[r_prev]` — the parity of consecutive rounds, deterministic
absent noise, which is what makes a *measurement* error (not just a data error)
detectable. The round structure is recovered from the unrolled `[loop N]` body
(repeated identical ancilla measurements); an irregular structure raises the
actionable `[loop N]` error. This is the single fiddliest piece — it was deferred
from the decoder change for exactly this reason — and is gated by D6.

### D5 — Runtime / backends
The iterative runtime (`q_orca/runtime/iterative.py`) collapses the qubit (sample
its measurement distribution if measured) and re-initialises it to |0⟩ on a
`reset`; the QuTiP / Qiskit dynamic paths apply a reset (project to |0⟩). A reset
on an unmeasured qubit forces it to |0⟩.

## Risks / Trade-offs
- **Cross-round detector indexing** (D4) off-by-one → wrong matching graph.
  Mitigation (D6): a multi-round repetition code whose logical error rate
  **improves with more rounds under measurement noise** (the signature that
  cross-round detectors work — single-round can't catch measurement errors), plus
  a unit test asserting the exact emitted cross-round `DETECTOR` records.
- **Ancilla-reset rule regression** — rewiring `roles.py` from regex to the
  parsed node could change diagnostics on existing examples. Mitigation: the
  existing role tests must stay green; keep the regex as a fallback initially.
- **`MR` vs `M+R` two-action form** — a user may write measure and reset as two
  separate actions/transitions. The compiler must coalesce them into `MR` only
  when the reset immediately follows on the same qubit with nothing between;
  otherwise emit `M` then `R`. Pinned by a unit test on both forms.

## Migration Plan
Additive. Machines without `reset` are unchanged. Existing `reset(qs[k])` text
(only in comments/suggestions today, not real effects) starts parsing as a real
effect — a strict improvement. Rollback = revert.

## Open Questions
1. Conditional reset (`if bits[j]==1: reset(qs[k])`) and reset-to-|1⟩ — deferred;
   v1 is unconditional reset-to-|0⟩.
2. Whether multi-round decoding warrants its own follow-on if D4 grows beyond a
   tractable size — split out `compile_to_stim_with_detectors` cross-round work
   if needed, keeping `reset` + `MR` as the shippable core.
