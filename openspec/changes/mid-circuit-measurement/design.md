## Context

End-of-circuit measurement already exists (`Measurement` AST node, parsed from `measure(qs[N])`). Mid-circuit measurement requires measuring a qubit into a classical bit register *during* the circuit, then using that classical bit to conditionally apply a gate. The existing `QActionSignature` stores at most one `gate` and one `measurement` per action — this design adds two new optional fields for the two new effect kinds.

## Goals / Non-Goals

**Goals:**
- Add `list<bit>` as a recognised context field type (parse `list<bit>` → `QTypeList(element_type="bit")`)
- Parse `measure(qs[N]) -> bits[M]` effect → `QEffectMeasure(qubit_idx=N, bit_idx=M)`
- Parse `if bits[M] == val: Gate(qs[K])` effect → `QEffectConditional(bit_idx=M, value=val, gate=...)`
- Store both on `QActionSignature` as optional fields
- Qiskit compiler: use `QuantumCircuit(n_qubits, n_bits)` and emit `qc.measure()` + `with qc.if_test(...):`
- QASM compiler: emit `c[M] = measure q[N];` inline and `if(c==val) gate q[K];`
- Verifier: `MidCircuitCoherenceRule` (no unitary after unmeasured mid-circuit qubit) and `FeedforwardCompletenessRule` (every measure result is used)
- Examples: `bit-flip-syndrome.q.orca.md`, `active-teleportation.q.orca.md`

**Non-Goals:**
- Multi-qubit classical register operations or arithmetic on bit results
- Reset gates (`reset q[N]`) — deferred to a follow-on
- Dynamic repetition / while-measure loops
- Noise model changes for mid-circuit measurement

## Decisions

**Decision: Two new fields on `QActionSignature` rather than a polymorphic effect list**
Adding `mid_circuit_measure: Optional[QEffectMeasure]` and `conditional_gate: Optional[QEffectConditional]` follows the same pattern as the existing `gate` and `measurement` fields. It avoids a larger refactor of the action/effect pipeline while keeping the new semantics visible at the AST level.

**Decision: `measure(qs[N]) -> bits[M]` is parsed separately from the terminal `measure(qs[N])`**
The existing `_parse_measurement_from_effect` matches `measure(qs[N])` without an arrow. The new `_parse_mid_circuit_measure_from_effect` matches only the arrow form, so neither parser conflicts with the other.

**Decision: Qiskit dynamic circuits via `qc.if_test` (OpenQASM 3 style)**
IBM's `qc.if_test((clbit, val))` context manager is the current Qiskit idiom for classical feedforward. It maps cleanly to the `with qc.if_test(...):` pattern and works without importing extra packages beyond `qiskit`.

**Decision: QASM uses OpenQASM 2 `if()` syntax**
The proposal mentions OpenQASM 3 `measure q[N] -> c[M];` style but `stdgates.inc` targets QASM 3. To keep the QASM output runnable on the widest set of simulators, we emit `c[M] = measure q[N];` (QASM 3 assignment style) and `if(c==val) gate q[K];` (QASM 2 if-clause, which is also accepted by many QASM 3 parsers).

**Decision: Bit count inferred from `list<bit>` context fields**
`_infer_bit_count` inspects context fields whose `QTypeList.element_type == "bit"` and counts them from the default value (e.g. `[b0, b1]` → 2). If no `list<bit>` field exists, bit count defaults to 0 (no classical register).

## Risks / Trade-offs

- **`qc.if_test` requires Qiskit ≥ 0.45** — accepted; older Qiskit already fails on other features
- **QASM `if()` clause targets QASM 2 semantics** — a future QASM 3 upgrade pass can switch to `if (c[M] == val) { ... }` style
- **Verifier checks are conservative** — `MidCircuitCoherenceRule` only fires if it can statically prove a qubit is used after measurement; it will miss dynamic paths involving guards
