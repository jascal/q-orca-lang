## Why

Q-Orca currently only supports end-of-circuit measurement. Mid-circuit measurement with classical feedforward is required to express quantum error correction, active teleportation, and adaptive VQE in a single linear circuit. Without it, these algorithms must be spread across multiple branching state machines, losing the circuit semantics. IBM Dynamic Circuits (2025) and Quantinuum's Guppy language validate that this is now a standard expectation of quantum programming languages.

## What Changes

- Add `list<bit>` as a new context field type for classical bit registers
- Add `measure(qs[N]) -> bits[M]` mid-circuit measurement effect syntax
- Add `if bits[M] == val: Gate(qs[K])` conditional gate effect syntax
- Extend Qiskit compiler to emit `qc.measure(...)` mid-circuit and `with qc.if_test(...):` dynamic circuit blocks
- Extend QASM compiler to emit `measure q[N] -> bits[M];` and `if(bits[M]==val) gate q[K];`
- Add two new verifier rules: `MidCircuitCoherenceRule` and `FeedforwardCompletenessRule`
- Add `examples/active-teleportation.q.orca.md` and `examples/bit-flip-syndrome.q.orca.md`

## Capabilities

### New Capabilities

*(none — extends existing language, compiler, and verifier capabilities)*

### Modified Capabilities

- `language`: add `list<bit>` type, `measure(...) -> bits[N]` effect, and `if bits[N] == val: Gate(...)` conditional effect to the grammar
- `compiler`: emit mid-circuit measurement and classical feedforward in QASM and Qiskit backends
- `verifier`: add mid-circuit coherence and feedforward completeness checks

## Impact

- `q_orca/ast.py` — new AST nodes: `QEffectMeasure`, `QEffectConditional`; new type: `QTypeList(element_type="bit")`
- `q_orca/parser/markdown_parser.py` — new effect string patterns
- `q_orca/compiler/qiskit.py` — dynamic circuit emission
- `q_orca/compiler/qasm.py` — conditional gate emission
- `q_orca/verifier/` — two new rule classes
- New: `examples/active-teleportation.q.orca.md`, `examples/bit-flip-syndrome.q.orca.md`, `tests/test_mid_circuit_measurement.py`
