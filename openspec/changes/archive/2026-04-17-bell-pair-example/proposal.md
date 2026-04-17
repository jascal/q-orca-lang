## Why

The compiler spec defines scenarios for CNOT translation across backends and Bell-pair Qiskit simulation, but `bell-entangler.q.orca.md` has no dedicated pipeline tests for QASM, Qiskit, or Mermaid output — only a parse/AST snapshot. This gap means compiler regressions against the canonical two-qubit entanglement circuit go undetected.

## What Changes

- Add `tests/test_bell_pair_pipeline.py` covering all three compiler backends against the existing Bell-pair machine
- Fix `bell-entangler.q.orca.md` to mark `|00>` as `[initial]`, align guard syntax with the verifier's `prob()` form, and ensure it passes strict `q-orca verify --strict`
- Pin the pipeline assertions to the exact output strings required by the compiler spec scenarios

## Capabilities

### New Capabilities

*(none — this change adds tests and fixes an existing example, not new language or compiler features)*

### Modified Capabilities

- `compiler`: add pipeline scenarios for CNOT-across-backends and Bell-pair Qiskit simulation that the spec already describes but tests do not yet cover

## Impact

- `examples/bell-entangler.q.orca.md` — minor corrections (initial annotation, guard syntax)
- `tests/test_bell_pair_pipeline.py` — new file
- `tests/test_examples.py` — update AST snapshot if state/transition counts change
- No API or dependency changes
