"""
QAOA MaxCut scaling sweep — 3 to 20 qubits.

Measures wall-clock simulation time and peak memory for QAOA circuits
of increasing size. Supports CPU (Qiskit statevector) and GPU (cuQuantum)
backends.

Usage:
    python benchmarks/qaoa/scaling_sweep.py [--backend cpu|gpu] [--output-dir benchmarks/reports]
    python benchmarks/qaoa/scaling_sweep.py --export-qasm --output-dir benchmarks/qasm_examples
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

def run_cpu(qc, shots: int = 1024) -> dict[str, Any]:
    """Simulate with Qiskit statevector (CPU).

    The `python_alloc_mb` field is `tracemalloc`'s peak Python-side allocation
    only — Qiskit Aer's statevector lives in C++ and is invisible here.
    """
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
    return {"elapsed_s": elapsed, "python_alloc_mb": peak / 1e6, "counts_sample": dict(list(counts.items())[:3])}


def run_gpu(qc, shots: int = 1024) -> dict[str, Any]:
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
        return {"elapsed_s": elapsed, "python_alloc_mb": None, "device": "GPU", "counts_sample": dict(list(counts.items())[:3])}
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

            python_alloc = res.get("python_alloc_mb")
            actual_device = res.get("device", "GPU" if backend == "gpu" else "CPU")
            row = {
                "algorithm": "QAOA-MaxCut",
                "n_qubits": n,
                "depth": depth,
                "gate_count": sum(gate_count.values()),
                "cx_count": gate_count.get("cx", 0) + gate_count.get("rzz", 0),
                "backend": "gpu" if actual_device == "GPU" else "cpu",
                "backend_requested": backend,
                "device": actual_device,
                "elapsed_s": round(res["elapsed_s"], 4),
                "python_alloc_mb": round(python_alloc, 2) if python_alloc is not None else None,
                "shots": shots,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(row)
            alloc_disp = f"{python_alloc:.1f} MB" if python_alloc is not None else "(GPU: n/a)"
            print(f"✓  {res['elapsed_s']:.3f}s  {alloc_disp}")
        except Exception as exc:
            print(f"✗  {exc}")
            rows.append({
                "n_qubits": n,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "backend": backend,
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"qaoa_{backend}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nResults written to {out_file}")


# ── QASM export ───────────────────────────────────────────────────────────

def export_qasm(qubit_sizes: list[int], depth: int, output_dir: Path) -> None:
    """Build each circuit and dump it as OpenQASM 2.0 — no simulator needed."""
    from qiskit import qasm2

    output_dir.mkdir(parents=True, exist_ok=True)
    for n in qubit_sizes:
        qc = build_qaoa_maxcut_circuit(n, depth=depth)
        out_file = output_dir / f"qaoa_maxcut_{n}q.qasm"
        header = (
            f"// Q-Orca benchmark: qaoa_maxcut_{n}q\n"
            f"// Qubits: {n}, depth: {depth}\n"
            f"// Generated by: python benchmarks/qaoa/scaling_sweep.py --export-qasm\n"
        )
        out_file.write_text(header + qasm2.dumps(qc) + "\n")
        print(f"  ✓ {out_file}")


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
    parser.add_argument(
        "--export-qasm",
        action="store_true",
        help="Write OpenQASM 2.0 for each qubit count to --output-dir and exit (no simulation).",
    )
    args = parser.parse_args()

    qubit_sizes = list(range(args.min_qubits, args.max_qubits + 1, args.step))

    if args.export_qasm:
        print(f"QAOA MaxCut QASM export — sizes={qubit_sizes} → {args.output_dir}")
        export_qasm(qubit_sizes, args.depth, args.output_dir)
        return

    print(f"QAOA MaxCut scaling sweep — backend={args.backend}, sizes={qubit_sizes}")
    sweep(args.backend, qubit_sizes, args.depth, args.shots, args.output_dir)


if __name__ == "__main__":
    main()
