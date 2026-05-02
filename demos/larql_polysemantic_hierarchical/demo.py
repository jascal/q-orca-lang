"""LARQL polysemantic-hierarchical demo (rung-1, MPS bond-2 encoding).

End-to-end validation of the `LarqlPolysemanticHierarchical` state
machine, the rung-1 sibling of `larql_polysemantic_clusters`:

    1. parse + verify the .q.orca.md (5-stage pipeline)
    2. compile to Mermaid + OpenQASM 3.0 + Qiskit
    3. analytic Gram matrix via `compute_concept_gram_mps` — visualized
       as a 4-tier ASCII heatmap showing the two-level hierarchy
    4. for each of the 12 concepts, run a fresh prepare+query circuit
       (feature = |dog>) and recover the polysemy column
    5. compare empirical vs. analytic polysemy columns; pass/fail on
       |max_error| < 3 · mc_std
    6. side-by-side recap of rung-0 (flat 3-tier) vs. rung-1 (hierarchical
       4-tier) Gram signatures.

Topology: 3 super-groups × 2 sub-clusters × 2 concepts = 12 concepts on a
3-qubit register. Each concept is encoded as the *cross-coupled* bond-2
MPS

    |c_i> = Ry(q0, α_i) CNOT(q0, q1) Ry(q1, α_i + β_i) CNOT(q1, q2) Ry(q2, β_i + γ_i) |000>

with α ∈ {0, 2π/3, 4π/3} (super-group), β ∈ {-0.5, +0.5} (sub-cluster),
and γ ∈ {-0.35, +0.35} (concept). The q1 and q2 rotations bind linear-
combination angles (`α + β`, `β + γ`) — the cross-coupling is what makes
the Gram non-factorized. The bare staircase (single-parameter Ry on each
qubit) factorizes as `∏_k cos((θ_{i,k} − θ_{j,k})/2)` despite Schmidt rank
2 — a known counter-example documented in the
`fix-mps-encoding-non-factorizing` design note. The cross-coupled
encoding produces analytic `|<c_i|c_j>|²` tiers — self 1.000, sub-
cluster-mate 0.882 (uniform), super-group-sibling {0.335, 0.593, 0.753},
cross-group [0.000, 0.178] — distinct from the flat-block clusters
demo's three uniform tiers.

Usage:
    pip install q-orca[quantum]
    python demos/larql_polysemantic_hierarchical/demo.py
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
    compute_concept_gram_mps,
    parse_q_orca_markdown,
    verify,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MACHINE_PATH = REPO_ROOT / "examples" / "larql-polysemantic-hierarchical.q.orca.md"

# (concept_name, super_group, sub_cluster) — order matches transition order.
CONCEPTS = [
    ("dog",        "animals",  "mammals"),
    ("cat",        "animals",  "mammals"),
    ("robin",      "animals",  "birds"),
    ("eagle",      "animals",  "birds"),
    ("strawberry", "fruits",   "berries"),
    ("blueberry",  "fruits",   "berries"),
    ("mango",      "fruits",   "tropical"),
    ("papaya",     "fruits",   "tropical"),
    ("car",        "vehicles", "land"),
    ("bike",       "vehicles", "land"),
    ("plane",      "vehicles", "air"),
    ("drone",      "vehicles", "air"),
]
FEATURE_INDEX = 0  # |f> = |dog>
SHOTS = 1024


def banner(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n  {title}\n{bar}")


def heatmap_tier(value: float) -> str:
    """4-tier ASCII heatmap: '#' ≥ 0.7, 'o' ∈ [0.3, 0.7), '.' ∈ [0.05, 0.3), blank < 0.05."""
    v = abs(value)
    if v >= 0.7:
        return "#"
    if v >= 0.3:
        return "o"
    if v >= 0.05:
        return "."
    return " "


def print_gram_heatmap(gram: np.ndarray) -> None:
    """Print |gram|² as a 4-tier 12×12 ASCII heatmap with hierarchy labels."""
    gsq = np.abs(gram) ** 2
    print("  |gram[i,j]|²  (# ≥ 0.7, o ∈ [0.3, 0.7), . ∈ [0.05, 0.3), blank < 0.05)")
    print("  ", "".join(f"{i:>3}" for i in range(12)))
    for i in range(12):
        row = "".join(f"  {heatmap_tier(gsq[i, j])}" for j in range(12))
        name, sup, sub = CONCEPTS[i]
        print(f"  {i:>2} {row}   ({name}, {sup}/{sub})")


def build_query_circuit(prepare_angles: tuple, query_angles: tuple):
    """Build a prepare(feature) + query(concept) circuit on 3 qubits.

    Mirrors the .q.orca.md effect strings exactly (cross-coupled bond-2):
        prepare:  Ry(q0, a); CNOT(q0,q1); Ry(q1, a+b); CNOT(q1,q2); Ry(q2, b+c)
        query:    Ry(q2,-(b+c)); CNOT(q1,q2); Ry(q1,-(a+b)); CNOT(q0,q1); Ry(q0,-a)
    """
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(3, 3)
    a, b, c = prepare_angles
    qc.ry(a, 0)
    qc.cx(0, 1)
    qc.ry(a + b, 1)
    qc.cx(1, 2)
    qc.ry(b + c, 2)
    a2, b2, c2 = query_angles
    qc.ry(-(b2 + c2), 2)
    qc.cx(1, 2)
    qc.ry(-(a2 + b2), 1)
    qc.cx(0, 1)
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
    banner("LARQL polysemantic-hierarchical demo (rung-1, MPS bond-2)")
    print(f"  Machine source : {MACHINE_PATH.relative_to(REPO_ROOT)}")
    print(f"  Concepts       : {len(CONCEPTS)} over 3 super-groups (animals, fruits, vehicles)")
    print("                   × 2 sub-clusters × 2 concepts (12 total)")
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
    parametric = [
        (a.name, [(p.name, p.type) for p in a.parameters])
        for a in machine.actions
        if a.parameters
    ]
    print(f"  Actions      : {parametric}")

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
    print(
        f"  qc.ry calls   : {qiskit_script.count('qc.ry(')}  "
        f"(3 ry × 13 transitions = 39)"
    )
    print(
        f"  qc.cx calls   : {qiskit_script.count('qc.cx(')}  "
        f"(2 cx × 13 transitions = 26)"
    )

    # 3. Analytic Gram matrix (4-tier hierarchy)
    banner("3. Analytic Gram matrix (4-tier hierarchy)")
    gram = compute_concept_gram_mps(machine)
    print_gram_heatmap(gram)

    gsq = np.abs(gram) ** 2
    sub_mate, super_sib, cross = [], [], []
    for i in range(12):
        gi, si = i // 4, (i // 2) % 2
        for j in range(i + 1, 12):
            gj, sj = j // 4, (j // 2) % 2
            v = gsq[i, j]
            if gi == gj and si == sj:
                sub_mate.append(v)
            elif gi == gj:
                super_sib.append(v)
            else:
                cross.append(v)
    print()
    print(
        f"  sub-cluster-mate   |<c_i|c_j>|² : min={min(sub_mate):.4f} "
        f"max={max(sub_mate):.4f}  (n={len(sub_mate)}; analytic ≈ 0.882)"
    )
    print(
        f"  super-group-sib    |<c_i|c_j>|² : min={min(super_sib):.4f} "
        f"max={max(super_sib):.4f}  (n={len(super_sib)}; analytic {{0.335, 0.593, 0.753}})"
    )
    print(
        f"  cross-group        |<c_i|c_j>|² : min={min(cross):.4f} "
        f"max={max(cross):.4f}  (n={len(cross)}; analytic [0.000, 0.178])"
    )

    # 4. Per-concept polysemy column (|f> = |dog>)
    banner("4. Per-concept polysemy column (12 independent circuits)")
    feature_angles = tuple(
        float(b.value) for b in call_sites[FEATURE_INDEX].bound_arguments
    )
    print(f"  Feature |f> prepare angles : {feature_angles}")
    print()
    print(
        f"  {'i':>2}  {'concept':<11}  {'group':<9}  {'sub':<9}  "
        f"{'P(|000>) empirical':<22}  {'analytic':<9}  {'|err|':<7}"
    )
    print(
        f"  {'':>2}  {'':-<11}  {'':-<9}  {'':-<9}  {'':-<22}  "
        f"{'':-<9}  {'':-<7}"
    )

    errors = []
    for i, t in enumerate(call_sites):
        query_angles = tuple(float(b.value) for b in t.bound_arguments)
        p_emp = run_one_query(feature_angles, query_angles, shots=SHOTS)
        p_ana = float(gsq[FEATURE_INDEX, i])
        err = abs(p_emp - p_ana)
        errors.append(err)
        bar = "#" * int(p_emp * 20)
        name, sup, sub = CONCEPTS[i]
        print(
            f"  {i:>2}  {name:<11}  {sup:<9}  {sub:<9}  "
            f"{p_emp:>6.3f}  {bar:<14}  {p_ana:>6.3f}   {err:>6.3f}"
        )

    # 5. Pass/fail
    banner("5. Empirical vs. analytic agreement")
    max_err = max(errors)
    mc_std_bound = (0.5 * 0.5 / SHOTS) ** 0.5
    threshold = 3 * mc_std_bound
    passed = max_err < threshold
    print(f"  max |empirical − analytic| across 12 concepts : {max_err:.4f}")
    print(f"  Monte-Carlo std bound (p=0.5, N={SHOTS})        : {mc_std_bound:.4f}")
    print(f"  3·std threshold                                : {threshold:.4f}")
    print(f"  Result : {'PASS' if passed else 'FAIL'}")

    # 6. Rung-0 vs. rung-1 recap
    banner("6. Rung-0 (flat) vs. rung-1 (hierarchical) Gram signatures")
    print("    rung-0 (larql-polysemantic-clusters, product state):")
    print("      |c_i> = Ry(q0,α) Ry(q1,β) Ry(q2,γ) |000>")
    print("      tiers : 1.000 / 0.720 / ≲ 0.09")
    print("              (self / cluster-mate / cross-cluster — three flat tiers)")
    print()
    print("    rung-1 (this demo, cross-coupled bond-2 MPS):")
    print("      |c_i> = Ry(q0,α) CNOT(q0,q1) Ry(q1,α+β) CNOT(q1,q2) Ry(q2,β+γ) |000>")
    print("      tiers : 1.000 / 0.882 / {0.335, 0.593, 0.753} / [0.000, 0.178]")
    print("              (self / sub-mate / super-sib / cross-group — four ordered tiers)")
    print()
    print("    The bond-2 CNOT staircase is a *prerequisite* for this hierarchy")
    print("    (it gives the register an entangled MPS structure), but it is not")
    print("    sufficient on its own — the bare staircase Ry(q0,α)·CNOT·Ry(q1,β)·")
    print("    CNOT·Ry(q2,γ)·|000> has a Gram identical to rung-0's product-state")
    print("    Gram despite Schmidt rank 2. The cross-coupled angle structure")
    print("    (α+β on q1, β+γ on q2) is what breaks the factorization and")
    print("    produces the graded four-tier hierarchy.")

    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
