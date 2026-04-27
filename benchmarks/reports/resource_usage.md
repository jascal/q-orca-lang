# Q-Orca Resource Usage Report

**Generated:** placeholder — run `python benchmarks/gpu_vs_cpu.py` to populate  
**Repo:** https://github.com/jascal/q-orca-lang

---

## Summary

This report characterises the computational resources required by the Q-Orca
toolchain across its primary benchmark workloads. It is intended to support
grant applications to NVIDIA, IBM, and Microsoft for access to GPU and QPU
compute resources.

---

## Benchmark results — GPU vs CPU

> **Status:** Placeholder — actual results will be generated once GPU hardware
> is available (the central goal of these grant applications).
> CPU baseline results will be added after running:
> `python benchmarks/gpu_vs_cpu.py --backend cpu`

| Algorithm       | Qubits | CPU time (s) | GPU time (s) | Speedup | CPU peak mem (MB) |
|-----------------|--------|--------------|--------------|---------|-------------------|
| QAOA MaxCut     | 6      | —            | —            | —       | —                 |
| QAOA MaxCut     | 10     | —            | —            | —       | —                 |
| QAOA MaxCut     | 14     | —            | —            | —       | —                 |
| QAOA MaxCut     | 18     | —            | —            | —       | —                 |
| QAOA MaxCut     | 20     | —            | —            | —       | —                 |
| VQE Heisenberg  | 6      | —            | —            | —       | —                 |
| VQE Heisenberg  | 10     | —            | —            | —       | —                 |
| VQE Heisenberg  | 14     | —            | —            | —       | —                 |
| VQE Heisenberg  | 18     | —            | —            | —       | —                 |
| VQE Heisenberg  | 20     | —            | —            | —       | —                 |

---

## LLM evolution demo — resource profile

| Parameter              | Value (placeholder) |
|------------------------|---------------------|
| LLM model              | claude-haiku-4-5 / GPT-4o-mini |
| Rounds per run         | 5–20 |
| Avg LLM latency/call   | — |
| Avg GPU eval/call      | — |
| Total GPU-hours / run  | — |
| Projected GPU-hours for 1,000 runs | — |

---

## Projected compute needs (NVIDIA grant request)

| Workload                         | Estimated GPU-hours |
|----------------------------------|---------------------|
| QAOA/VQE scaling sweeps (3–20q)  | ~200                |
| LLM evolution campaigns          | ~5,000              |
| Dirac rewriter verification runs | ~2,000              |
| Safety headroom (20%)            | ~1,440              |
| **Total requested**              | **~8,640 H100-hours**|

> Note: Full 30,000-hour request allows for larger qubit counts (25–30q),
> deeper circuits (depth ≥ 3), and extended LLM evolution campaigns.

---

## System configuration

| Component      | CPU baseline           | Target GPU (requested)      |
|----------------|------------------------|-----------------------------|
| Simulator      | Qiskit Aer (statevec)  | cuQuantum / CUDA-Q          |
| Backend        | x86_64 CPU             | NVIDIA H100 (SXM5, 80 GB)  |
| Python         | 3.10+                  | 3.10+                       |
| Quantum lib    | Qiskit 1.x + QuTiP     | + custatevec-cu12           |
| LLM            | Claude Haiku / GPT-4o  | Same                        |

---

*Report template — updated automatically by `benchmarks/gpu_vs_cpu.py`.*
