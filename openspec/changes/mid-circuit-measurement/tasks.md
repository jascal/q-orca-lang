## 1. AST

- [x] 1.1 Add `QEffectMeasure` and `QEffectConditional` dataclasses to `q_orca/ast.py`;
      extend `QActionSignature` with `mid_circuit_measure: Optional[QEffectMeasure] = None`
      and `conditional_gate: Optional[QEffectConditional] = None`

## 2. Parser

- [x] 2.1 Add `_parse_mid_circuit_measure_from_effect(effect_str)` in
      `q_orca/parser/markdown_parser.py` — matches `measure(qs[N]) -> bits[M]`,
      returns `QEffectMeasure(qubit_idx=N, bit_idx=M)`; also ensure `list<bit>`
      is parsed as `QTypeList(element_type="bit")` (add `"bit"` as recognized element type
      in `_parse_q_type_string`)
- [x] 2.2 Add `_parse_conditional_gate_from_effect(effect_str)` — matches
      `if bits[M] == val: Gate(qs[K])`, returns
      `QEffectConditional(bit_idx=M, value=val, gate=QuantumGate(...))`
- [x] 2.3 Call both helpers in `_parse_actions_table` and store results on
      `QActionSignature.mid_circuit_measure` and `QActionSignature.conditional_gate`

## 3. Qiskit compiler

- [x] 3.1 Add `_infer_bit_count(machine)` helper in `q_orca/compiler/qiskit.py` that
      returns the classical bit count from `list<bit>` context fields (count items in
      default value like `[b0, b1]`)
- [x] 3.2 In `compile_to_qiskit`, switch from `QuantumCircuit({n})` to
      `QuantumCircuit({n_qubits}, {n_bits})` when `n_bits > 0`; in the gate emission
      loop, emit `qc.measure(N, M)` for `mid_circuit_measure` actions and
      `with qc.if_test((qc.clbits[M], val)):\n    qc.<gate>(K)` for
      `conditional_gate` actions

## 4. QASM compiler

- [x] 4.1 In `compile_to_qasm` (`q_orca/compiler/qasm.py`), emit
      `c[M] = measure q[N];` inline (in the gate sequence loop) for
      `mid_circuit_measure` actions, and `if(c==val) <gate> q[K];` for
      `conditional_gate` actions; also declare `bit[n_bits] c;` when the machine has
      mid-circuit measurements

## 5. Verifier

- [x] 5.1 Add `check_mid_circuit_coherence(machine)` in `q_orca/verifier/quantum.py` —
      activated by `"mid_circuit_coherence"` rule; walk the BFS gate sequence and
      error if any action applies a unitary gate to a qubit that a prior action
      already measured mid-circuit (uses `mid_circuit_measure`)
- [x] 5.2 Add `check_feedforward_completeness(machine)` — activated by
      `"feedforward_completeness"` rule; warn if the machine has actions with
      `mid_circuit_measure` but no action with `conditional_gate` referencing that
      bit index
- [x] 5.3 Register both checks in `verify_quantum` so they run automatically

## 6. Examples and tests

- [x] 6.1 Add `examples/bit-flip-syndrome.q.orca.md` — 5-qubit bit-flip syndrome
      circuit: 3 data qubits + 2 ancilla; prepare |000>, measure two syndromes
      mid-circuit into `bits`, apply corrections conditioned on syndrome values
- [x] 6.2 Add `examples/active-teleportation.q.orca.md` — 3-qubit active teleportation:
      prepare Bell pair, mid-circuit Bell measurement on data + Alice qubit, feedforward
      X and Z corrections on Bob's qubit
- [x] 6.3 Create `tests/test_mid_circuit_measurement.py` covering:
      parser round-trip for `QEffectMeasure` and `QEffectConditional`,
      Qiskit emission with `qc.measure` and `qc.if_test`,
      QASM emission with `c[M] = measure` and `if(c==val)`,
      and verifier acceptance of well-formed machines
- [x] 6.4 Run `pytest tests/test_mid_circuit_measurement.py` and confirm all tests pass;
      run full `pytest` suite and confirm no regressions
