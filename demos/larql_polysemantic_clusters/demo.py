"""LARQL polysemantic-clusters demo.

End-to-end validation of the `LarqlPolysemanticClusters` state machine:

    1. parse + verify the .q.orca.md (5-stage pipeline)
    2. compile to Mermaid + OpenQASM 3.0 + Qiskit
    3. analytic Gram matrix via `compute_concept_gram` — visualized as a
       3-tier ASCII heatmap showing block structure
    4. for each of the 12 concepts, run a fresh prepare+query circuit
       (feature = |Paris>) and recover the polysemy column
    5. compare empirical vs. analytic polysemy columns; pass/fail on
       |max_error| < 3 · mc_std

The three clusters — capitals, fruits, vehicles — are hand-encoded as
tetrahedral scatters around axis-aligned centers `(2.8, 0, 0)`,
`(0, 2.8, 0)`, `(0, 0, 2.8)` with scatter magnitude `s = 0.4`. This
gives analytic intra-cluster pairwise overlap `|<c_i|c_j>|² = 0.720`
(uniform) and inter-cluster overlap `|<c_i|c_j>|² < 0.10` (most
≪ 0.02) — a block-structured Gram matrix, unlike
`larql-polysemantic-12`'s flat 1/2-everywhere dictionary.

Usage:
    pip install q-orca[quantum]
    python demos/larql_polysemantic_clusters/demo.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from q_orca import (
    QSimulationOptions,
    VerifyOptions,
    compile_to_mermaid,
    compile_to_qasm,
    compile_to_qiskit,
    compute_concept_gram,
    parse_q_orca_markdown,
    verify,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MACHINE_PATH = REPO_ROOT / "examples" / "larql-polysemantic-clusters.q.orca.md"

CONCEPTS = [
    ("Paris",  "capitals"),
    ("Tokyo",  "capitals"),
    ("London", "capitals"),
    ("Berlin", "capitals"),
    ("apple",  "fruits"),
    ("banana", "fruits"),
    ("cherry", "fruits"),
    ("durian", "fruits"),
    ("car",    "vehicles"),
    ("boat",   "vehicles"),
    ("plane",  "vehicles"),
    ("rocket", "vehicles"),
]
FEATURE_INDEX = 0  # |f> = |Paris>
SHOTS = 1024


def banner(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n  {title}\n{bar}")


def heatmap_tier(value: float) -> str:
    """3-tier ASCII heatmap character: '#' (high), '.' (mid), ' ' (low)."""
    v = abs(value)
    if v >= 0.5:
        return "#"
    if v >= 0.1:
        return "."
    return " "


def print_gram_heatmap(gram: np.ndarray) -> None:
    """Print |gram|² as a tiered 12×12 ASCII heatmap."""
    gsq = np.abs(gram) ** 2
    print("  |gram[i,j]|²  (# ≥ 0.5, . ∈ [0.1, 0.5), blank < 0.1)")
    print("  ", "".join(f"{i:>3}" for i in range(12)))
    for i in range(12):
        row = "".join(f"  {heatmap_tier(gsq[i, j])}" for j in range(12))
        print(f"  {i:>2} {row}   ({CONCEPTS[i][0]}, {CONCEPTS[i][1]})")


def build_query_circuit(prepare_angles: tuple, query_angles: tuple):
    """Build a prepare(feature) + query(concept) circuit on 3 qubits.

    Mirrors the .q.orca.md effect strings exactly:
        prepare:  Ry(q0, a); Ry(q1, b); Ry(q2, c)
        query:    Ry(q2, -c); Ry(q1, -b); Ry(q0, -a)
    """
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(3, 3)
    a, b, c = prepare_angles
    qc.ry(a, 0)
    qc.ry(b, 1)
    qc.ry(c, 2)
    a2, b2, c2 = query_angles
    qc.ry(-c2, 2)
    qc.ry(-b2, 1)
    qc.ry(-a2, 0)
    qc.measure(range(3), range(3))
    return qc


def run_one_query(prepare_angles: tuple, query_angles: tuple, shots: int) -> float:
    """Return empirical P(|000>) from `shots` shots."""
    from qiskit import transpile
    from qiskit.providers.basic_provider import BasicSimulator

    qc = build_query_circuit(prepare_angles, query_angles)
    backend = BasicSimulator()
    tqc = transpile(qc, backend, basis_gates=["u3", "cx", "id"])
    result = backend.run(tqc, shots=shots).result()
    counts = result.get_counts()
    hit = counts.get("000", 0)
    total = sum(counts.values())
    return hit / total if total else 0.0


def main() -> None:
    banner("LARQL polysemantic-clusters demo")
    print(f"  Machine source : {MACHINE_PATH.relative_to(REPO_ROOT)}")
    print(f"  Concepts       : {len(CONCEPTS)} over 3 clusters (capitals, fruits, vehicles)")
    print(f"  Feature loaded : |f> = |{CONCEPTS[FEATURE_INDEX][0]}>")
    print(f"  Shots / query  : {SHOTS}")

    # 1. Parse + verify
    banner("1. Verify state machine (Q-Orca pipeline)")
    source = MACHINE_PATH.read_text()
    parsed = parse_q_orca_markdown(source)
    if parsed.errors:
        for e in parsed.errors:
            print(f"  parse error: {e}")
        raise SystemExit(1)
    machine = parsed.file.machines[0]
    print(f"  Machine name : {machine.name}")
    print(f"  States       : {len(machine.states)}")
    print(f"  Transitions  : {len(machine.transitions)}")
    print(f"  Actions      : {[(a.name, [(p.name, p.type) for p in a.parameters]) for a in machine.actions if a.parameters]}")

    call_sites = [t for t in machine.transitions if t.action == "query_concept"]
    print(f"  query_concept call sites : {len(call_sites)}")

    result = verify(machine, VerifyOptions(skip_dynamic=True))
    status = "VALID" if result.valid else "INVALID"
    print(f"  Verification : {status}")
    err_count = sum(1 for e in result.errors if e.severity == "error")
    warn_count = sum(1 for e in result.errors if e.severity == "warning")
    print(f"  Errors / warnings : {err_count} / {warn_count}")

    # 2. Compile
    banner("2. Compile to Mermaid + OpenQASM 3.0 + Qiskit")
    mermaid = compile_to_mermaid(machine)
    qasm = compile_to_qasm(machine)
    qiskit_script = compile_to_qiskit(
        machine,
        QSimulationOptions(analytic=False, shots=0, run=False, skip_qutip=True),
    )
    print(f"  Mermaid lines : {len(mermaid.strip().splitlines())}")
    print(f"  QASM lines    : {len(qasm.strip().splitlines())}")
    print(f"  Qiskit lines  : {len(qiskit_script.strip().splitlines())}")
    print(f"  QASM register : {'qubit[3] q;' in qasm}")
    print(f"  qc.ry calls   : {qiskit_script.count('qc.ry(')} (3 prep + 36 query = 39)")

    # 3. Analytic Gram matrix
    banner("3. Analytic Gram matrix (block structure)")
    gram = compute_concept_gram(machine)
    print_gram_heatmap(gram)

    gsq = np.abs(gram) ** 2
    intra = []
    inter = []
    for i in range(12):
        for j in range(i + 1, 12):
            (v := gsq[i, j])
            if CONCEPTS[i][1] == CONCEPTS[j][1]:
                intra.append(v)
            else:
                inter.append(v)
    print()
    print(f"  Intra-cluster |<c_i|c_j>|² : min={min(intra):.4f} max={max(intra):.4f}  "
          f"(uniform at ≈ 0.7197)")
    print(f"  Inter-cluster |<c_i|c_j>|² : min={min(inter):.4f} max={max(inter):.4f}  "
          f"(all < 0.10; cluster structure)")

    # 4. Per-concept polysemy column (|f> = |Paris>)
    banner("4. Per-concept polysemy column (12 independent circuits)")
    feature_angles = tuple(float(b.value) for b in call_sites[FEATURE_INDEX].bound_arguments)
    print(f"  Feature |f> prepare angles : {feature_angles}")
    print()
    print(f"  {'i':>2}  {'concept':<10}  {'cluster':<9}  {'P(|000>) empirical':<20}  {'analytic':<9}  {'|error|':<8}")
    print(f"  {'':>2}  {'':-<10}  {'':-<9}  {'':-<20}  {'':-<9}  {'':-<8}")

    errors = []
    for i, t in enumerate(call_sites):
        query_angles = tuple(float(b.value) for b in t.bound_arguments)
        p_emp = run_one_query(feature_angles, query_angles, shots=SHOTS)
        p_ana = float(gsq[FEATURE_INDEX, i])
        err = abs(p_emp - p_ana)
        errors.append(err)
        bar = "#" * int(p_emp * 30)
        concept_name, cluster = CONCEPTS[i]
        print(f"  {i:>2}  {concept_name:<10}  {cluster:<9}  "
              f"{p_emp:>6.3f}  {bar:<14}  {p_ana:>6.3f}   {err:>6.3f}")

    # 5. Pass/fail
    banner("5. Empirical vs. analytic agreement")
    max_err = max(errors)
    # Monte-Carlo std under worst-case Bernoulli variance (p=0.5 bound).
    mc_std_bound = (0.5 * 0.5 / SHOTS) ** 0.5
    threshold = 3 * mc_std_bound
    passed = max_err < threshold
    print(f"  max |empirical − analytic| across 12 concepts : {max_err:.4f}")
    print(f"  Monte-Carlo std bound (p=0.5, N={SHOTS})        : {mc_std_bound:.4f}")
    print(f"  3·std threshold                                : {threshold:.4f}")
    print(f"  Result : {'PASS' if passed else 'FAIL'}")
    print()
    print("  --- Cluster-phenomenon recap ---")
    print("    Three tiers in the polysemy column:")
    print("      1.000      (self)                — concept 0 (Paris)")
    print("      0.720      (cluster-mates)       — concepts 1..3 (other capitals)")
    print("      ≲ 0.09     (cross-cluster)       — concepts 4..11 (fruits + vehicles)")
    print("    This is the block-Gram signature of structured polysemy,")
    print("    distinct from `larql-polysemantic-12`'s flat 3/4-vs-1/3 floor.")

    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
