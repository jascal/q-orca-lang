## 1. Shared gate mapping

- [x] 1.1 Factor the Clifford gate→Stim mapping out of
  `stabilizer_entanglement.build_state_simulator` into a shared helper that can
  emit onto either a `stim.TableauSimulator` (verify path) or a `stim.Circuit`
  (sampling path), so both apply identical gates. Keep the verify path's
  behaviour bit-for-bit (existing parity tests must stay green).

## 2. compile_to_stim

- [x] 2.1 `compile_to_stim(machine) -> stim.Circuit`: walk the action/transition
  stream, emit Clifford gates via 1.1; build a `bit-index → record-position` map
  as measurements are emitted.
- [x] 2.2 Measurement: `measure(qs[i]) -> bits[j]` → `M i`, tracking the
  `bit → record` map. (`MR` is unreachable — q-orca has no `reset` syntax; see
  design D2. Deferred to when reset syntax ships.)
- [x] 2.3 Feedforward: `if bits[j] == 1: X(qs[k])` → `CX rec[-N] k`,
  `… Z(qs[k])` → `CZ rec[-N] k`, converting `bits[j]`'s absolute record position
  to the relative `rec[-N]` at emit time. **Highest-risk step** — see design D3.
- [x] 2.4 Diagnostics: fail fast with a structured, located error on an
  unsupported construct — a non-Clifford machine (reuse `is_clifford` before
  emitting), a non-Pauli feedforward correction, or an unsupported feedforward
  condition / conditional-or-non-local reset — rather than emit a wrong circuit.

## 3. Aer-stabilizer target

- [x] 3.1 `compile_to_qiskit_stabilizer(machine) -> QuantumCircuit`: reuse
  `q_orca/compiler/qiskit.py`; run under `AerSimulator(method="stabilizer")`.
  Secondary engine / fallback when Stim is absent but qiskit-aer is present.

## 4. Sampling helper

- [x] 4.1 A helper that runs a compiled circuit and returns an outcome→count
  dict (Stim `compile_sampler().sample(shots)`; seeded), plus a QuTiP-path
  counterpart for the parity comparison.

## 5. Examples — DEFERRED (see design D7)

QEC syndrome corrections are inherently multi-clause AND feedforward, which the
sampling path refuses (it is a decoder concern, not in-circuit rec-control). So
these examples would exercise only the already-shipped *verify* path, not this
*sampling* path. Deferred to the decoder follow-on.

- [ ] (DEFERRED → decoder follow-on) 5.1 `examples/surface-code-3.q.orca.md`.
- [ ] (DEFERRED → decoder follow-on) 5.2 `examples/bit-flip-repeated.q.orca.md`.

## 6. Tests

- [x] 6.1 `compile_to_stim` gate mapping: H/CNOT/CZ/SWAP/S and π/2 rotations emit
  the expected Stim instructions.
- [x] 6.2 Measurement mapping: measure→`M`; measure-then-reset→`MR`.
- [x] 6.3 Feedforward record indexing: assert the exact emitted instructions for
  teleportation — `b1` → `CX rec[-1] 2`, `b0` → `CZ rec[-2] 2` (the worked
  example in design D3) — so a swapped/mis-indexed record is caught directly.
- [x] 6.4 Diagnostics: non-Clifford machine, non-Pauli feedforward correction,
  and conditional/non-local reset each raise the structured located error (2.4).
- [x] 6.5 Distribution parity (terminal): Bell + GHZ Stim sample counts match the
  QuTiP distribution within a Wilson-score bound at `shots=10000`, seeded.
  Marked slow (low-shot default in fast CI, full count opt-in) per design D6.
- [x] 6.6 Distribution parity (feedforward): `active-teleportation` teleported
  distribution matches QuTiP within the bound — the gate on the `rec[-N]` mapping.
- [x] 6.7 Multi-clause-feedforward boundary: `bit-flip-syndrome` (real QEC
  syndrome decoding) raises the structured `single-clause` diagnostic — pinning
  that multi-clause syndrome decoding is a decoder follow-on, not miscompiled.

## 7. Docs

- [x] 7.1 Extend `docs/language/stabilizer-backend.md` with a "Sampling" section
  (`compile_to_stim`, measurement/feedforward mapping, distribution parity).
