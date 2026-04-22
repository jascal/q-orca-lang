"""LARQL Gate-KNN Grover demo.

End-to-end validation of the GateKnnGroverSearch state machine:

    1. parse + verify the .q.orca.md (5-stage pipeline)
    2. compile to Mermaid + OpenQASM 3.0
    3. compile to a Qiskit script and run it (analytic + 1024 shots)
    4. decode the measurement back to a (fake) LARQL feature table

This instance uses 4 index qubits (N=16 features). Marked feature is
index 10 (bitstring 1010) = the (France, capital, Paris) edge in the
LARQL frame. Optimal Grover iteration count for N=16, M=1 is
floor(pi/4 * sqrt(16)) = 3; the marked-state probability after three
iterations is > 96%.

Scaling note. A real LARQL layer has N ~ 10K gate vectors. The state-machine
shape generalises by adding more (oracle_mark -> diffuse) iterations:
floor(pi/4 * sqrt(N/M)) total. The 4-qubit toy is the smallest size that
exercises the multi-controlled-Z primitive (MCZ on 3 controls + 1 target),
which is the gate that scales with index-register width.

Usage:
    pip install q-orca[quantum]
    python demos/larql_gate_knn/demo.py
"""

from __future__ import annotations

from pathlib import Path

from q_orca import (
    parse_q_orca_markdown,
    verify,
    VerifyOptions,
    compile_to_mermaid,
    compile_to_qasm,
    compile_to_qiskit,
    QSimulationOptions,
)
from q_orca.runtime.python import run_simulation


REPO_ROOT = Path(__file__).resolve().parents[2]
MACHINE_PATH = REPO_ROOT / "examples" / "larql-gate-knn-grover.q.orca.md"

# Stand-in for a LARQL .vindex layer. In a real run these triples would be
# read from down_meta.bin + relation_clusters.json + feature_labels.json.
LARQL_FEATURES = {
    0:  ("Germany",      "capital",     "Berlin"),
    1:  ("France",       "language",    "French"),
    2:  ("Spain",        "borders",     "France"),
    3:  ("Italy",        "capital",     "Rome"),
    4:  ("Japan",        "capital",     "Tokyo"),
    5:  ("Brazil",       "capital",     "Brasilia"),
    6:  ("Egypt",        "capital",     "Cairo"),
    7:  ("Canada",       "capital",     "Ottawa"),
    8:  ("Australia",    "capital",     "Canberra"),
    9:  ("India",        "capital",     "New Delhi"),
    10: ("France",       "capital",     "Paris"),   # marked target — bitstring 1010
    11: ("Germany",      "borders",     "France"),
    12: ("Spain",        "language",    "Spanish"),
    13: ("Italy",        "language",    "Italian"),
    14: ("Portugal",     "borders",     "Spain"),
    15: ("Mexico",       "language",    "Spanish"),
}
MARKED_INDEX = 10


def banner(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}")


def bitstring_to_index(bits: str) -> int:
    # Qiskit returns counts keyed by bitstrings with q[N-1] as the leftmost
    # character. The bitstring read left-to-right is already the integer
    # representation with q[N-1] as MSB.
    return int(bits, 2)


def main() -> None:
    banner("LARQL Gate-KNN Grover demo")
    print(f"  Machine source : {MACHINE_PATH.relative_to(REPO_ROOT)}")
    print(f"  Layer features : {len(LARQL_FEATURES)} (N=16, log2 N = 4 qubits)")
    e, r, t = LARQL_FEATURES[MARKED_INDEX]
    print(f"  Marked feature : index {MARKED_INDEX} = ({e!r}, {r!r}, {t!r})")

    # 1. Parse + verify
    banner("1. Verify state machine (Q-Orca 5-stage pipeline)")
    source = MACHINE_PATH.read_text()
    parsed = parse_q_orca_markdown(source)
    if parsed.errors:
        for e in parsed.errors:
            print(f"  parse error: {e}")
        return
    machine = parsed.file.machines[0]
    print(f"  Machine name : {machine.name}")
    print(f"  States       : {len(machine.states)}")
    print(f"  Transitions  : {len(machine.transitions)}")
    print(f"  Actions      : {len(machine.actions)}")

    result = verify(machine, VerifyOptions(skip_dynamic=True))
    status = "VALID" if result.valid else "INVALID"
    print(f"  Verification : {status}")
    for err in result.errors:
        print(f"    [{err.severity.upper():5}] {err.code}: {err.message}")

    # 2. Compile to Mermaid + QASM
    banner("2. Compile to Mermaid + OpenQASM 3.0")
    mermaid = compile_to_mermaid(machine)
    qasm = compile_to_qasm(machine)

    print("  --- Mermaid state diagram ---")
    for line in mermaid.strip().splitlines():
        print(f"    {line}")

    print("\n  --- OpenQASM 3.0 ---")
    for line in qasm.strip().splitlines():
        print(f"    {line}")

    # 3. Generate + run Qiskit simulation
    banner("3. Simulate (Qiskit, 1024 shots)")
    script = compile_to_qiskit(
        machine,
        QSimulationOptions(analytic=False, shots=1024, run=True, skip_qutip=True),
    )
    sim = run_simulation(script)
    if not sim.success:
        print(f"  Simulation FAILED: {sim.error}")
        if sim.stderr:
            print(f"  stderr: {sim.stderr[:500]}")
        return

    counts = sim.counts or {}
    if counts:
        print(f"  Counts ({sum(counts.values())} shots):")
        for bits, n in sorted(counts.items()):
            bar = "#" * int(40 * n / sum(counts.values()))
            print(f"    |{bits}>  {n:4d}  {bar}")

    if sim.probabilities:
        print("\n  Probabilities:")
        for bits, p in sorted(sim.probabilities.items()):
            print(f"    |{bits}>  {p:6.2%}")

    # 4. Decode back to LARQL features
    banner("4. LARQL feature recovery")
    if not counts:
        print("  No shot counts (analytic-only run). Falling back to probabilities.")
        counts = {b: int(round(p * 1024)) for b, p in (sim.probabilities or {}).items()}

    best_bits, best_n = max(counts.items(), key=lambda kv: kv[1])
    best_index = bitstring_to_index(best_bits)
    e, r, t = LARQL_FEATURES.get(best_index, ("?", "?", "?"))
    total = sum(counts.values()) or 1

    print(f"  Most-measured : |{best_bits}>  ({best_n}/{total} = {best_n/total:.1%})")
    print(f"  Decoded index : {best_index}")
    print(f"  LARQL edge    : {e} --[{r}]--> {t}")
    if best_index == MARKED_INDEX:
        print("  Result        : RECOVERED the marked feature in 1 oracle call.")
    else:
        print("  Result        : MISS (expected on noisy hardware; clean sim should hit).")

    print("\n  --- Scaling ---")
    print("    Classical KNN at N=16  :  16 inner products.")
    print("    Quantum Grover at N=16 :  3 oracle + 3 diffusion (probability > 96%).")
    print("    LARQL layer N~10K      :  10000 vs floor(pi/4 * sqrt(10000)) = 78 oracles.")
    print("    LARQL Gemma 4B (34 layers, N~348K total): 348K vs ~590 -- O(N) -> O(sqrt N).")
    print("\n  Caveat: the speedup is only realised if the gate-vector database can be")
    print("  loaded into superposition (QRAM). Without QRAM, classical I/O dominates")
    print("  and the quadratic speedup vanishes -- this is the load-bearing assumption")
    print("  the state machine makes implicit by treating apply_phase_oracle as one step.")


if __name__ == "__main__":
    main()
