## Context

`bell-entangler.q.orca.md` is the canonical two-qubit entanglement example. It is tested in `tests/test_examples.py` via a parse/AST snapshot, but the three compiler backends (QASM, Qiskit, Mermaid) are never invoked against it. The compiler spec already defines two normative scenarios for the Bell-pair machine ("Qiskit script with simulation options" and "CNOT translation across backends"), but no test file enforces them. Additionally, the example has two minor issues:

1. `|00>` is not annotated `[initial]` — it relies on implicit first-state semantics.
2. Guards use `fidelity(|ψ>, |00>) ** 2 ≈ 0.5` instead of the verifier's `prob('00') ≈ 0.5` form, which can cause strict-mode failures.

## Goals / Non-Goals

**Goals:**
- Fix `bell-entangler.q.orca.md` to pass `q-orca verify --strict`
- Add `tests/test_bell_pair_pipeline.py` covering parse → verify → QASM → Qiskit → Mermaid for the Bell-pair machine
- Validate the specific output strings called out in the compiler spec scenarios

**Non-Goals:**
- New language features or gate kinds
- Additional example machines
- Changes to the compiler or verifier logic

## Decisions

**Decision: Fix example in place, do not create a new file**  
The existing `bell-entangler.q.orca.md` is already referenced in `test_examples.py`. Creating a parallel file would duplicate the machine definition. Instead, fix it to be spec-compliant; update the AST snapshot in `test_examples.py` only if state/transition counts change.

**Decision: Separate pipeline test file**  
Mixing pipeline assertions into `test_examples.py` would blur its purpose (lightweight existence checks for all examples). A dedicated `tests/test_bell_pair_pipeline.py` keeps the compiler contract assertions focused and easy to find.

**Decision: Use `prob('00') ≈ 0.5` guard syntax**  
The verifier's `QGuardProbability` is populated from `prob('<bits>') <op> <value>` patterns. The `fidelity(...)` form is a display alias that the parser accepts but the dynamic verifier may not evaluate. Using `prob()` ensures consistency across static and dynamic verification paths.

**Decision: Analytic mode for Qiskit smoke test**  
`QSimulationOptions(analytic=True)` exercises the `Statevector` path without needing a real Qiskit Aer install. This is the same pattern used in `test_vqe_rotation.py`.

## Risks / Trade-offs

- **AST snapshot mismatch** → `test_examples.py` snapshot will need updating if the example's guard syntax change alters the parsed `QGuardDef` representation. Keep both tests updated together.
- **Strict verify flakiness** → If the verifier's superposition-leak check is sensitive to the example's transition structure, the same 3-state trick used in `vqe-rotation.q.orca.md` may be needed. Investigate before patching.
