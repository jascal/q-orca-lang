## 1. Shared gate mapping

- [ ] 1.1 Factor the Clifford gate→Stim mapping out of
  `stabilizer_entanglement.build_state_simulator` into a shared helper that can
  emit onto either a `stim.TableauSimulator` (verify path) or a `stim.Circuit`
  (sampling path), so both apply identical gates. Keep the verify path's
  behaviour bit-for-bit (existing parity tests must stay green).

## 2. compile_to_stim

- [ ] 2.1 `compile_to_stim(machine) -> stim.Circuit`: walk the action/transition
  stream, emit Clifford gates via 1.1; build a `bit-index → record-position` map
  as measurements are emitted.
- [ ] 2.2 Measurement: `measure(qs[i]) -> bits[j]` → `MR i` when a `reset(qs[i])`
  effect follows on the same qubit in the stream, else `M i`.
- [ ] 2.3 Feedforward: `if bits[j] == 1: X(qs[k])` → `CX rec[-N] k`,
  `… Z(qs[k])` → `CZ rec[-N] k`, converting `bits[j]`'s absolute record position
  to the relative `rec[-N]` at emit time. **Highest-risk step** — see design D3.

## 3. Aer-stabilizer target

- [ ] 3.1 `compile_to_qiskit_stabilizer(machine) -> QuantumCircuit`: reuse
  `q_orca/compiler/qiskit.py`; run under `AerSimulator(method="stabilizer")`.
  Secondary engine / fallback when Stim is absent but qiskit-aer is present.

## 4. Sampling helper

- [ ] 4.1 A helper that runs a compiled circuit and returns an outcome→count
  dict (Stim `compile_sampler().sample(shots)`; seeded), plus a QuTiP-path
  counterpart for the parity comparison.

## 5. Examples

- [ ] 5.1 `examples/surface-code-3.q.orca.md`: distance-3 rotated surface code,
  one stabilizer round (~17 physical qubits). Validate it parses, classifies
  Clifford, and verifies on the shipped stim backend before adding sampling.
- [ ] 5.2 `examples/bit-flip-repeated.q.orca.md`: three rounds of the 3-qubit
  bit-flip code, each extracting a fresh syndrome with conditional corrections.

## 6. Tests

- [ ] 6.1 `compile_to_stim` gate mapping: H/CNOT/CZ/SWAP/S and π/2 rotations emit
  the expected Stim instructions.
- [ ] 6.2 Measurement mapping: measure→`M`; measure-then-reset→`MR`.
- [ ] 6.3 Feedforward record indexing: `bits[0]` (measured first) drives
  `rec[-2]` when a later bit was measured after it; assert the exact `rec[-N]`.
- [ ] 6.4 Distribution parity (terminal): Bell + GHZ Stim sample counts match the
  QuTiP distribution within a Wilson-score bound at `shots=10000`, seeded.
- [ ] 6.5 Distribution parity (feedforward): `active-teleportation` teleported
  distribution matches QuTiP within the bound — the gate on the `rec[-N]` mapping.
- [ ] 6.6 The two new examples parse, verify (stim backend), and sample.

## 7. Docs

- [ ] 7.1 Extend `docs/language/stabilizer-backend.md` with a "Sampling" section
  (`compile_to_stim`, measurement/feedforward mapping, distribution parity).
