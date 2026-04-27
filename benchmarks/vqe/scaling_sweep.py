"""
VQE Heisenberg scaling sweep — 4 to 20 qubits.

Measures wall-clock time, convergence behaviour, and peak memory for VQE
circuits of increasing size. Supports CPU (Qiskit statevector) and GPU
(cuQuantum) backends.

Usage:
    python benchmarks/vqe/scaling_sweep.py [--backend cpu|gpu] [--output-dir benchmarks/reports]
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


# ── Ansatz builder ────────────────────────────────────────────────────────

def build_vqe_ansatz(n_qubits: int, depth: int = 1) -> tuple:
    """
    Hardware-efficient VQE ansatz for a 1-D Heisenberg chain.
    Returns (ParameterizedCircuit, ParameterVector).
    """
    from qiskit.circuit import ParameterVector, QuantumCircuit

    params = ParameterVector("θ", length=n_qubits * (depth + 1))
    qc = QuantumCircuit(n_qubits)
    p_idx = 0

    # Initial rotation layer
    for i in range(n_qubits):
        qc.ry(params[p_idx], i)
        p_idx += 1

    for _ in range(depth):
        # Entangling layer — CNOT ladder
        for i in range(n_qubits - 1):
            qc.cx(i, i + 1)
        # Rotation layer
        for i in range(n_qubits):
            qc.ry(params[p_idx], i)
            p_idx += 1

    return qc, params


def build_heisenberg_hamiltonian(n_qubits: int):
    """Nearest-neighbour Heisenberg XXX Hamiltonian."""
    from qiskit.quantum_info import SparsePauliOp

    terms = []
    for i in range(n_qubits - 1):
        xx = "I" * i + "XX" + "I" * (n_qubits - i - 2)
        yy = "I" * i + "YY" + "I" * (n_qubits - i - 2)
        zz = "I" * i + "ZZ" + "I" * (n_qubits - i - 2)
        terms += [(xx, 1.0), (yy, 1.0), (zz, 1.0)]
    return SparsePauliOp.from_list(terms)


# ── Runner ────────────────────────────────────────────────────────────────

def run_vqe_cpu(n_qubits: int, depth: int = 1, maxiter: int = 30) -> dict[str, Any]:
    """Run VQE on CPU via Qiskit Primitives.

    `python_alloc_mb` is `tracemalloc`'s peak Python-side allocation only;
    Qiskit's C++ backend memory is invisible to this measurement.
    """
    from scipy.optimize import minimize

    from qiskit.primitives import StatevectorEstimator

    qc, params = build_vqe_ansatz(n_qubits, depth)
    hamiltonian = build_heisenberg_hamiltonian(n_qubits)
    estimator = StatevectorEstimator()

    def cost_fn(x):
        bound = qc.assign_parameters(dict(zip(params, x)))
        pub = (bound, hamiltonian)
        result = estimator.run([pub]).result()
        return float(result[0].data.evs)

    x0 = [0.1] * len(params)
    tracemalloc.start()
    t0 = time.perf_counter()
    opt_result = minimize(cost_fn, x0, method="COBYLA", options={"maxiter": maxiter})
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "elapsed_s": round(elapsed, 4),
        "python_alloc_mb": round(peak / 1e6, 2),
        "n_iter": opt_result.nfev,
        "energy": round(float(opt_result.fun), 6),
        "converged": opt_result.success,
        "device": "CPU",
    }


def run_vqe_gpu(n_qubits: int, depth: int = 1, maxiter: int = 30) -> dict[str, Any]:
    """Run VQE on GPU via cuStateVec. Falls back to CPU if unavailable."""
    from importlib.util import find_spec

    if find_spec("cudaq") is None:
        print("  [GPU] cudaq not installed — falling back to CPU")
    else:
        # cudaq is installed but the VQE path isn't wired up yet — keep the
        # file runnable on a GPU box without claiming GPU numbers.
        print("  [GPU] cudaq VQE path not yet wired — falling back to CPU")
    result = run_vqe_cpu(n_qubits, depth, maxiter)
    result["device"] = "CPU_fallback"
    return result


# ── Sweep ─────────────────────────────────────────────────────────────────

def sweep(backend: str, qubit_sizes: list[int], depth: int, maxiter: int, output_dir: Path) -> None:
    rows = []
    for n in qubit_sizes:
        print(f"  n={n:2d} qubits ...", end=" ", flush=True)
        try:
            fn = run_vqe_gpu if backend == "gpu" else run_vqe_cpu
            res = fn(n, depth=depth, maxiter=maxiter)
            row = {
                "algorithm": "VQE-Heisenberg",
                "n_qubits": n,
                "depth": depth,
                "n_params": n * (depth + 1),
                "backend": backend,
                "device": res.get("device", backend),
                "elapsed_s": res["elapsed_s"],
                "python_alloc_mb": res.get("python_alloc_mb"),
                "n_iter": res.get("n_iter"),
                "energy": res.get("energy"),
                "converged": res.get("converged"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(row)
            print(f"✓  {res['elapsed_s']:.3f}s  E={res.get('energy', '?'):.4f}")
        except Exception as exc:
            print(f"✗  {exc}")
            rows.append({
                "n_qubits": n,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "backend": backend,
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"vqe_{backend}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nResults written to {out_file}")


# ── QASM export ───────────────────────────────────────────────────────────

def export_qasm(qubit_sizes: list[int], depth: int, output_dir: Path) -> None:
    """Bind ansatz parameters to a fixed value and dump as OpenQASM 2.0."""
    from qiskit import qasm2

    output_dir.mkdir(parents=True, exist_ok=True)
    for n in qubit_sizes:
        qc, params = build_vqe_ansatz(n, depth)
        # Bind every parameter to 0.1 — same default the gpu_vs_cpu harness uses.
        bound = qc.assign_parameters({p: 0.1 for p in params})
        out_file = output_dir / f"vqe_heisenberg_{n}q.qasm"
        header = (
            f"// Q-Orca benchmark: vqe_heisenberg_{n}q\n"
            f"// Qubits: {n}, depth: {depth}, parameters bound to θ=0.1\n"
            f"// Generated by: python benchmarks/vqe/scaling_sweep.py --export-qasm\n"
        )
        out_file.write_text(header + qasm2.dumps(bound) + "\n")
        print(f"  ✓ {out_file}")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VQE scaling sweep")
    parser.add_argument("--backend", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--output-dir", default="benchmarks/reports", type=Path)
    parser.add_argument("--min-qubits", type=int, default=4)
    parser.add_argument("--max-qubits", type=int, default=20)
    parser.add_argument("--step", type=int, default=2)
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--maxiter", type=int, default=30)
    parser.add_argument(
        "--export-qasm",
        action="store_true",
        help="Write OpenQASM 2.0 for each qubit count to --output-dir and exit (no simulation).",
    )
    args = parser.parse_args()

    qubit_sizes = list(range(args.min_qubits, args.max_qubits + 1, args.step))

    if args.export_qasm:
        print(f"VQE Heisenberg QASM export — sizes={qubit_sizes} → {args.output_dir}")
        export_qasm(qubit_sizes, args.depth, args.output_dir)
        return

    print(f"VQE Heisenberg scaling sweep — backend={args.backend}, sizes={qubit_sizes}")
    sweep(args.backend, qubit_sizes, args.depth, args.maxiter, args.output_dir)


if __name__ == "__main__":
    main()
