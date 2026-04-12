## Context

Single-qubit parameterized gates (`Rx`, `Ry`, `Rz`) were added in v0.3.3. They share a single regex pattern in `_parse_gate_from_effect`, a shared `evaluate_angle` helper, and dispatch branches in the Qiskit/QASM compilers. Two-qubit parameterized gates follow the identical pattern with one extra qubit index argument.

## Goals / Non-Goals

**Goals:**
- Add `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ` to parser, both compilers, and verifier
- Reuse `evaluate_angle` unchanged — no grammar changes needed
- Add a QAOA MaxCut example and a focused test suite

**Non-Goals:**
- Context parameter resolution (e.g. `gamma` as a symbolic angle from context fields) — deferred; gates must use literal angles or the existing `evaluate_angle` grammar
- Three-qubit parameterized gates (`CCRZ` etc.)
- Noise model support for the new gate kinds (follow-on)

## Decisions

**Decision: `Gate(qs[i], qs[j], angle)` argument order — two qubits then angle**  
Consistent with the single-qubit form `Gate(qs[i], angle)`. Controlled gates use first qubit as control, second as target. Symmetric gates (`RXX/RYY/RZZ`) treat both as targets.

**Decision: QASM decomposition for `RXX/RYY/RZZ`**  
These three gates are not in `qelib1.inc` (OpenQASM 2 stdlib). Emit them as inline decompositions rather than custom gate definitions to keep the QASM output self-contained:
- `RZZ(θ) q0, q1` → `cx q0,q1; rz(θ) q1; cx q0,q1;`
- `RXX(θ) q0, q1` → `h q0; h q1; cx q0,q1; rz(θ) q1; cx q0,q1; h q0; h q1;`
- `RYY(θ) q0, q1` → `rx(pi/2) q0; rx(pi/2) q1; cx q0,q1; rz(θ) q1; cx q0,q1; rx(-pi/2) q0; rx(-pi/2) q1;`

`CRx/CRy/CRz` are in `qelib1.inc` and emit directly.

**Decision: Reuse `QuantumGate` AST node**  
`QuantumGate` already has `kind`, `targets: list[int]`, `controls: list[int]`, and `parameter: float`. Two-qubit parameterized gates use `targets=[j]`, `controls=[i]` for controlled forms, and `targets=[i, j]` for symmetric forms. No new AST node needed.

## Risks / Trade-offs

- **QASM decomposition verbosity** → decomposed `RXX/RYY/RZZ` emit 3–7 lines per gate; acceptable for correctness, can be optimized later
- **`GateKind` literal expansion** → adding 6 new string literals to the type is mechanical but widens the union; worth it for type safety
