# QASM Examples

Compiled OpenQASM 2.0 outputs from Q-Orca benchmark circuits.
Provided for IBM Quantum and Microsoft Azure Quantum grant reviewers.

## Files

| File | Algorithm | Qubits | Notes |
|------|-----------|--------|-------|
| `qaoa_maxcut_6q.qasm` | QAOA MaxCut | 6 | Ring graph, depth=1 |
| `qaoa_maxcut_12q.qasm` | QAOA MaxCut | 12 | Ring + long-range, depth=1 |
| `vqe_heisenberg_8q.qasm` | VQE Heisenberg | 8 | HW-efficient ansatz, depth=1 |

## Regenerating

```bash
# After installing q-orca[quantum]:
python benchmarks/qaoa/scaling_sweep.py --export-qasm --output-dir benchmarks/qasm_examples
```

These files are also the basis for IBM QPU submission (via Qiskit Runtime)
and Azure Quantum submission (via Q# or pass-through QASM).
