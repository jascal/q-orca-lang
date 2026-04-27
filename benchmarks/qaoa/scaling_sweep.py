"""
QAOA MaxCut scaling sweep — 3 to 20 qubits.

Measures wall-clock simulation time and peak memory for QAOA circuits
of increasing size. Supports CPU (Qiskit statevector) and GPU (cuQuantum)
backends.

Usage:
    python benchmarks/qaoa/scaling_sweep.py [--backend cpu|gpu] [--output-dir benchmarks/reports]
"""

from __future__ import annotations

import argparse
import json
import os
import time
import tracemalloc
from datetime import datetime
from pathlib import Path

import numpy as np


# ── Circuit builder ────────────────────────────────────────────────────────

def build_qaoa_maxcut_circuit(n_qubits: int, depth: int = 1, gamma: float = 0.5, beta: float = 0.25):
    """Build a QAOA MaxCut ansatz on a random 3-regular-ish graph."""
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(n_qubits)

    # Layer 0: Hadamard superposition
    for i in range(n_qubits):
        qc.h(i)

    # Build edges: ring + some long-range edges for density
    edges = [(i, (i + 1) % n_qubits) for i in range(n_qubits)]
    if n_qubits >= 6:
        edges += [(i, (i + 2) % n_qubits) for i in range(0, n_qubits, 2)]

    for _ in range(depth):
        # Cost layer — RZZ on all edges
        for u, v in edges:
            qc.rzz(2 * gamma, u, v)
        # Mixer layer — Rx on all qubits
        for i in range(n_qubits):
            qc.rx(2 * beta, i)

    qc.measure_all()
    return qc


# ── Backend runners ────────────────────────────────────────────────────────

def run_cpu(qc, shots: int = 1024) -> dict:
    """Simulate with Qiskit statevector (CPU)."""
    from qiskit import transpile
    from qiskit_aer import AerSimulator

    sim = AerSimulator(method="statevector")
    t_qc = transpile(qc, sim)
    tracemalloc.start()
    t0 = time.perf_counter()
    result = sim.run(t_qc, shots=shots).result()
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    counts = result.get_counts()
    return {"elapsed_s": elapsed, "peak_mem_mb": peak / 1e6, "counts_sample": dict(list(counts.items())[:3])}


def run_gpu(qc, shots: int = 1024) -> dict:
    """Simulate with cuQuantum statevector (GPU). Falls back to CPU if unavailable."""
    try:
        from qiskit import transpile
        from qiskit_aer import AerSimulator

        sim = AerSimulator(method="statevector", device="GPU", cuStateVec_enable=True)
        t_qc = transpile(qc, sim)
        t0 = time.perf_counter()
        result = sim.run(t_qc, shots=shots).result()
        elapsed = time.perf_counter() - t0
        counts = result.get_counts()
        return {"elapsed_s": elapsed, "peak_mem_mb": None, "device": "GPU", "counts_sample": dict(list(counts.items())[:3])}
    except Exception as exc:
        print(f"  [GPU] Not available ({exc}), falling back to CPU")
        result = run_cpu(qc, shots)
        result["device"] = "CPU_fallback"
        return result


# ── Sweep ─────────────────────────────────────────────────────────────────

def sweep(backend: str, qubit_sizes: list[int], depth: int, shots: int, output_dir: Path) -> None:
    rows = []
    for n in qubit_sizes:
        print(f"  n={n:2d} qubits ...", end=" ", flush=True)
        try:
            qc = build_qaoa_maxcut_circuit(n, depth=depth)
            gate_count = qc.count_ops()

            if backend == "gpu":
                res = run_gpu(qc, shots)
            else:
                res = run_cpu(qc, shots)

            row = {
                "algorithm": "QAOA-MaxCut",
                "n_qubits": n,
                "depth": depth,
                "gate_count": sum(gate_count.values()),
                "cx_count": gate_count.get("cx", 0) + gate_count.get("rzz", 0),
                "backend": backend,
                "elapsed_s": round(res["elapsed_s"], 4),
                "peak_mem_mb": round(res.get("peak_mem_mb") or 0, 2),
                "shots": shots,
                "timestamp": datetime.utcnow().isoformat(),
            }
            rows.append(row)
            print(f"✓  {res['elapsed_s']:.3f}s  {res.get('peak_mem_mb', 0):.1f} MB")
        except Exception as exc:
            print(f"✗  {exc}")
            rows.append({"n_qubits": n, "error": str(exc), "backend": backend})

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"qaoa_{backend}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nResults written to {out_file}")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="QAOA scaling sweep")
    parser.add_argument("--backend", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--output-dir", default="benchmarks/reports", type=Path)
    parser.add_argument("--min-qubits", type=int, default=3)
    parser.add_argument("--max-qubits", type=int, default=20)
    parser.add_argument("--step", type=int, default=2)
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--shots", type=int, default=1024)
    args = parser.parse_args()

    qubit_sizes = list(range(args.min_qubits, args.max_qubits + 1, args.step))
    print(f"QAOA MaxCut scaling sweep — backend={args.backend}, sizes={qubit_sizes}")
    sweep(args.backend, qubit_sizes, args.depth, args.shots, args.output_dir)


if __name__ == "__main__":
    main()
