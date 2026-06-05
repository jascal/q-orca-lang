## Context

`add-stabilizer-backend` shipped the Clifford *verification* path:
`q_orca/compiler/stabilizer.py::is_clifford` classifies machines,
`q_orca/verifier/stabilizer_entanglement.py` computes entanglement on the
tableau, and `q_orca/backends/stim_backend.py` wires it into Stage 4b via
`dynamic_verify_stabilizer`. None of that **samples** — the entanglement check
evolves the unitary path on a `stim.TableauSimulator` and reads the check matrix;
it never builds a circuit with measurements. This change adds
`compile_to_stim(machine) -> stim.Circuit` (a runnable circuit *with*
measurements) and the shots-based parity validation that proves it correct.

Measurements and feedforward already have surface syntax (see
`examples/active-teleportation.q.orca.md`): `measure(qs[i]) -> bits[j]` and
`if bits[j] == 1: X(qs[k])`. The shared effect parser and
`q_orca/verifier/dynamic.py` already extract these.

## Goals / Non-Goals

**Goals:**
- `compile_to_stim` covering the Clifford gate set, mid-circuit `MR`/`M`, and
  `rec[-N]`-controlled Pauli feedforward.
- A seeded distribution-parity test (`shots=10000`) that the Stim sample
  distribution equals the QuTiP state-vector distribution within a statistical
  bound — including the `active-teleportation` feedforward circuit.
- Two QEC examples that showcase the sampling path.

**Non-Goals:**
- Wiring the stabilizer sampler into `q-orca run` / `simulate` — a separate
  follow-on (Open Q1).
- Clifford+T magic-state branching; Stim detector-error-model export.
- Reproducing the verify-path entanglement work (already shipped).

## Decisions

### D1 — Reuse the v1 gate→Stim mapping
`q_orca/verifier/stabilizer_entanglement.py::build_state_simulator` already maps
the Clifford gate set (incl. `π/2` rotations → `√X`/`√Y`/`S`) onto a
`TableauSimulator`, with control/target extraction mirroring
`dynamic._get_qutip_operator`. `compile_to_stim` factors that gate mapping into a
shared helper emitting onto a `stim.Circuit` instead, so the sampling circuit and
the verification tableau apply identical gates.

### D2 — Measurement: `M` only (`MR` deferred — no `reset` syntax)
`measure(qs[i]) -> bits[j]` emits `M i`. Each emitted measurement appends a
record; the compiler maintains a `bit_index -> measurement_record_position` map
so feedforward can resolve `bits[j]` to the right record. **Finding during
implementation:** q-orca has no `reset` syntax in the grammar (no `QEffectReset`
/ parser support), so the research sketch's `MR`-when-a-reset-follows rule is
unreachable — `compile_to_stim` always emits `M`. `MR` arrives with reset
syntax; measurement emission is the single line that changes. QEC examples that
would reset an ancilla between rounds (e.g. `bit-flip-repeated`) instead use a
fresh ancilla per round.

### D3 — Feedforward via `rec[-N]` (the risk)
`if bits[j] == 1: X(qs[k])` compiles to Stim's measurement-record-controlled
gate `CX rec[<rec_for_j>] k`; a `Z` correction to `CZ rec[<rec_for_j>] k`. Stim
references measurements by **relative** offset from the end of the record
(`rec[-1]` is the most recent), so the compiler converts the absolute record
position of `bits[j]` to the relative `rec[-(total_records - pos)]` at the point
the correction is emitted. This off-by-one-prone conversion is the single
highest-risk piece; D5's parity test on `active-teleportation` (which feeds two
distinct measured bits forward to two different corrections) is the gate. Worked
example — teleportation's `meas q0 (b0); meas q1 (b1); if b1: X(q2); if b0: Z(q2)`:

```
H 1
CX 1 2          # Bell pair on q1, q2
CX 0 1
H 0
M 0             # record 0  (b0)
M 1             # record 1  (b1)
CX rec[-1] 2    # if b1 == 1: X(q2)  — b1 is the most recent record
CZ rec[-2] 2    # if b0 == 1: Z(q2)  — b0 is one record back
```

The `rec[-2]` for `b0` (not `rec[-1]`) is exactly the indexing the parity test
pins.

### D4 — Aer-stabilizer as a secondary target
`compile_to_qiskit_stabilizer(machine) -> QuantumCircuit` reuses the existing
`q_orca/compiler/qiskit.py` circuit and runs it under
`AerSimulator(method="stabilizer")`. It is a fallback engine when Stim is absent
but `qiskit-aer` is present; Stim remains preferred.

### D5 — Distribution-parity validation
A test compiles to Stim, samples `shots=10000` (seeded via `stim`'s sampler
seed), tallies outcomes, and compares against the QuTiP measurement
distribution from the shipped `dynamic`/assertion simulation. Equality is
asserted per-outcome within a Wilson-score interval so the test is not flaky.
Covered circuits: Bell + GHZ (terminal measurement) and `active-teleportation`
(mid-circuit measurement + feedforward).

## Risks / Trade-offs
- **`rec[-N]` off-by-one / wrong-bit feedforward** → silently wrong corrections
  that still produce a plausible distribution. Mitigation: the
  `active-teleportation` parity test uses two *distinct* bits driving two
  *different* corrections, so a swapped/mis-indexed record fails parity.
- **Reset detection** (`MR` vs `M`) depends on recognizing a following `reset`
  effect. Mitigation: a focused unit test on a measure-then-reset action.
- **Surface-code-3 authoring** (~17 qubits, rotated layout) is fiddly to get
  right. Mitigation: validate it parses + classifies Clifford + verifies on the
  shipped stim backend before adding the sampling assertion.

## Migration Plan
Additive. `compile_to_stim` is a new entry point; nothing existing calls it. The
two examples are new files. No change to the shipped verify path. Rollback =
revert.

### D6 — Parity test cost in CI
The `shots=10000` parity tests are seeded and marked slow (a `pytest` marker, or
parametrised with a low-shot default and a `--slow` opt-in to the full count) so
the default CI run stays fast while the full-shot parity still runs on demand /
nightly. Stim sampling of 10k shots is sub-millisecond, so the cost is the QuTiP
counterpart, not Stim.

## Open Questions
1. Wiring the stabilizer sampler into `q-orca run` / `simulate` (Open Q2 from
   `add-stabilizer-backend`) — its own follow-on once `compile_to_stim` lands.
2. Stim detector-error-model export (`DETECTOR`/`OBSERVABLE_INCLUDE`) for decoder
   benchmarking — deferred; `compile_to_stim` lays the groundwork.
