"""
GPU vs CPU comparison benchmark for Q-Orca.

Runs QAOA MaxCut and VQE Heisenberg circuits across a range of qubit counts
on both backends (where available), then produces a side-by-side timing and
memory table for grant application evidence.

Usage:
    python benchmarks/gpu_vs_cpu.py [--max-qubits 20] [--report-dir benchmarks/reports]

Output:
    benchmarks/reports/gpu_vs_cpu_<timestamp>.json
    benchmarks/reports/gpu_vs_cpu_<timestamp>.md   (human-readable table)
"""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Circuit builders (inline — no import from subdirs needed) ─────────────

def qaoa_circuit(n: int, depth: int = 1):
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(n)
    for i in range(n):
        qc.h(i)
    edges = [(i, (i + 1) % n) for i in range(n)]
    for _ in range(depth):
        for u, v in edges:
            qc.rzz(1.0, u, v)
        for i in range(n):
            qc.rx(0.5, i)
    qc.measure_all()
    return qc


def vqe_circuit(n: int, depth: int = 1):
    """Hardware-efficient VQE ansatz with bound parameters (Heisenberg target)."""
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(n)
    for i in range(n):
        qc.ry(0.1, i)
    for _ in range(depth):
        for i in range(n - 1):
            qc.cx(i, i + 1)
        for i in range(n):
            qc.ry(0.1, i)
    qc.measure_all()
    return qc


# ── Timed simulation ───────────────────────────────────────────────────────

def simulate(qc, backend: str, shots: int = 512) -> dict[str, Any]:
    try:
        if backend == "gpu":
            return _sim_gpu(qc, shots)
        return _sim_cpu(qc, shots)
    except Exception as exc:
        return {"elapsed_s": None, "peak_mem_mb": None, "error": str(exc), "device": backend}


def _sim_cpu(qc, shots: int) -> dict:
    from qiskit import transpile
    from qiskit_aer import AerSimulator

    sim = AerSimulator(method="statevector")
    t_qc = transpile(qc, sim)
    tracemalloc.start()
    t0 = time.perf_counter()
    sim.run(t_qc, shots=shots).result()
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"elapsed_s": round(elapsed, 5), "peak_mem_mb": round(peak / 1e6, 2), "device": "CPU"}


def _sim_gpu(qc, shots: int) -> dict:
    from qiskit import transpile
    from qiskit_aer import AerSimulator

    sim = AerSimulator(method="statevector", device="GPU", cuStateVec_enable=True)
    t_qc = transpile(qc, sim)
    t0 = time.perf_counter()
    sim.run(t_qc, shots=shots).result()
    elapsed = time.perf_counter() - t0
    return {"elapsed_s": round(elapsed, 5), "peak_mem_mb": None, "device": "GPU"}


# ── Report builders ───────────────────────────────────────────────────────

def build_markdown_table(rows: list[dict], out_path: Path) -> None:
    header = "| Algorithm | Qubits | CPU (s) | GPU (s) | Speedup | CPU Mem (MB) |"
    sep    = "|-----------|--------|---------|---------|---------|--------------|"
    lines  = [header, sep]

    grouped: dict[tuple, dict] = {}
    for r in rows:
        key = (r["algorithm"], r["n_qubits"])
        grouped.setdefault(key, {})[r["backend"]] = r

    for (algo, n), backends in sorted(grouped.items()):
        cpu = backends.get("cpu", {})
        gpu = backends.get("gpu", {})
        cpu_t = cpu.get("elapsed_s")
        gpu_t = gpu.get("elapsed_s")
        speedup = f"{cpu_t/gpu_t:.1f}×" if cpu_t and gpu_t else "—"
        cpu_mem = f"{cpu.get('peak_mem_mb', '—')}" if cpu.get("peak_mem_mb") else "—"
        lines.append(
            f"| {algo} | {n} "
            f"| {cpu_t if cpu_t else '—'} "
            f"| {gpu_t if gpu_t else '—'} "
            f"| {speedup} "
            f"| {cpu_mem} |"
        )

    out_path.write_text("# GPU vs CPU Benchmark Results\n\n" + "\n".join(lines) + "\n")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["cpu", "gpu", "both"], default="both")
    parser.add_argument("--max-qubits", type=int, default=20)
    parser.add_argument("--min-qubits", type=int, default=6)
    parser.add_argument("--step", type=int, default=2)
    parser.add_argument("--shots", type=int, default=512)
    parser.add_argument("--report-dir", default="benchmarks/reports", type=Path)
    args = parser.parse_args()

    sizes = list(range(args.min_qubits, args.max_qubits + 1, args.step))
    backends = ["cpu", "gpu"] if args.backend == "both" else [args.backend]

    print(f"Q-Orca GPU vs CPU benchmark  |  qubits={sizes}  backends={backends}")
    print("=" * 60)

    rows = []
    for algo_name, build_fn in [("QAOA-MaxCut", qaoa_circuit), ("VQE-Heisenberg", vqe_circuit)]:
        for n in sizes:
            for backend in backends:
                print(f"  {algo_name} n={n:2d} [{backend.upper()}] ...", end=" ", flush=True)
                qc = build_fn(n)
                res = simulate(qc, backend, args.shots)
                row = {
                    "algorithm": algo_name,
                    "n_qubits": n,
                    "backend": backend,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **res,
                }
                rows.append(row)
                if res.get("error"):
                    print(f"✗ {res['error']}")
                else:
                    print(f"✓ {res['elapsed_s']:.4f}s")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    args.report_dir.mkdir(parents=True, exist_ok=True)
    json_out = args.report_dir / f"gpu_vs_cpu_{ts}.json"
    md_out   = args.report_dir / f"gpu_vs_cpu_{ts}.md"

    json_out.write_text(json.dumps(rows, indent=2))
    build_markdown_table(rows, md_out)

    print(f"\nJSON report : {json_out}")
    print(f"Markdown    : {md_out}")


if __name__ == "__main__":
    main()
