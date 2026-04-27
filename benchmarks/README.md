# Q-Orca Benchmarks

Performance benchmarks and resource characterization for the Q-Orca toolchain.
These results support GPU compute grant applications (NVIDIA, IBM, Microsoft).

## Structure

```
benchmarks/
├── qaoa/              # QAOA MaxCut benchmarks — 3 to 20 qubits
├── vqe/               # VQE Heisenberg benchmarks — 4 to 20 qubits
├── qasm_examples/     # Compiled QASM outputs for QPU grant reviewers
├── reports/           # Resource usage summaries (auto-generated)
├── gpu_vs_cpu.py      # GPU vs CPU timing comparison (NVIDIA grant)
└── llm_evolution.py   # LLM-driven circuit evolution demo (NVIDIA grant)
```

## Running benchmarks

```bash
# Full benchmark suite (CPU — no GPU required)
python benchmarks/gpu_vs_cpu.py --backend cpu

# GPU benchmark (requires NVIDIA GPU + cuQuantum or CUDA-Q)
python benchmarks/gpu_vs_cpu.py --backend gpu

# LLM evolution demo (requires OPENAI_API_KEY or Claude API key)
python benchmarks/llm_evolution.py

# Individual QAOA scaling sweep
python benchmarks/qaoa/scaling_sweep.py

# Individual VQE scaling sweep
python benchmarks/vqe/scaling_sweep.py
```

## Key results (placeholder — update after runs)

| Benchmark        | Qubits | CPU time (s) | GPU time (s) | Speedup |
|-----------------|--------|--------------|--------------|---------|
| QAOA MaxCut     | 12     | —            | —            | —       |
| QAOA MaxCut     | 16     | —            | —            | —       |
| QAOA MaxCut     | 20     | —            | —            | —       |
| VQE Heisenberg  | 12     | —            | —            | —       |
| VQE Heisenberg  | 16     | —            | —            | —       |
| VQE Heisenberg  | 20     | —            | —            | —       |

See `reports/resource_usage.md` for full profiling data.
