"""LARQL polysemantic-12 demo.

End-to-end validation of the LarqlPolysemantic12 state machine:

    1. parse + verify the .q.orca.md (5-stage pipeline)
    2. compile to Mermaid + OpenQASM 3.0 + Qiskit
    3. for each of the 12 concepts, run a fresh single-query circuit and
       recover the polysemy score P(|0^12>)
    4. compare against the analytic table; confirm the 1/3 cross-talk floor

The state machine declares 12 parametric call sites ``query_concept(0..11)``
that share one action template (``Hadamard(qs[c])``). A single Qiskit circuit
cannot simulate all 12 queries together because each query destroys |f> via
measurement (no-cloning). The demo therefore runs 12 independent circuits,
one per concept, with the same prep unitary.

The polysemantic feature loads concepts 0 ("Paris") and 1 ("Tokyo") with
equal amplitude. Analytic predictions:

    in-feature concepts  (c = 0, 1)   : P(|0^12>) = 3/4   ~ 75.0%
    out-of-feature (c = 2..11)         : P(|0^12>) = 1/3   ~ 33.3%

The 1/3 cross-talk floor is the direct consequence of pairwise overlap 1/2
between concept vectors — the same floor classical sparse autoencoders hit
when feature count exceeds hidden dim.

Usage:
    pip install q-orca[quantum]
    python demos/larql_polysemantic_12/demo.py
"""

from __future__ import annotations

from pathlib import Path

from q_orca import (
    QSimulationOptions,
    VerifyOptions,
    compile_to_mermaid,
    compile_to_qasm,
    compile_to_qiskit,
    parse_q_orca_markdown,
    verify,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MACHINE_PATH = REPO_ROOT / "examples" / "larql-polysemantic-12.q.orca.md"

# Fake LARQL feature table: 12 non-orthogonal concept vectors the machine's
# 12-qubit concept register indexes. Concepts 0 and 1 are loaded into |f>;
# the rest are distractors the cross-talk floor exposes.
LARQL_CONCEPTS = {
    0:  "Paris",
    1:  "Tokyo",
    2:  "Berlin",
    3:  "Rome",
    4:  "Madrid",
    5:  "Cairo",
    6:  "Ottawa",
    7:  "Brasilia",
    8:  "Canberra",
    9:  "New Delhi",
    10: "Mexico City",
    11: "Stockholm",
}
IN_FEATURE = {0, 1}
SHOTS = 1024
ANALYTIC_IN = 0.75
ANALYTIC_OUT = 1 / 3


def banner(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}")


def build_query_circuit(concept_index: int):
    """Build a fresh prep+query circuit for one concept.

    Mirrors the .q.orca.md effect strings: the prep action runs first (always
    the same on q0, q1), then ``Hadamard(qs[concept_index])`` is applied as
    the inverse of concept_index's preparation unitary. Measurement is on
    all 12 qubits; P(|0^12>) is the polysemy score.
    """
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(12, 12)
    # prepare_polysemantic
    qc.ry(0.8411, 1)
    qc.x(1)
    qc.cry(0.9273, 1, 0)
    qc.x(1)
    # query_concept(concept_index)
    qc.h(concept_index)
    qc.measure(range(12), range(12))
    return qc


def run_one_query(concept_index: int, shots: int = SHOTS) -> tuple[int, int]:
    """Return (hit_count, total_count) for a single-concept query."""
    from qiskit import transpile
    from qiskit.providers.basic_provider import BasicSimulator

    qc = build_query_circuit(concept_index)
    backend = BasicSimulator()
    tqc = transpile(qc, backend, basis_gates=["u3", "cx", "id"])
    result = backend.run(tqc, shots=shots).result()
    counts = result.get_counts()
    all_zero_key = "0" * 12
    hit = counts.get(all_zero_key, 0)
    total = sum(counts.values())
    return hit, total


def main() -> None:
    banner("LARQL polysemantic-12 demo")
    print(f"  Machine source : {MACHINE_PATH.relative_to(REPO_ROOT)}")
    print(f"  Concept count  : {len(LARQL_CONCEPTS)} (12-qubit register)")
    print(f"  In-feature     : {sorted(IN_FEATURE)} → {[LARQL_CONCEPTS[c] for c in sorted(IN_FEATURE)]}")
    print("  Cross-talk     : concepts 2..11 load 0, score driven by <c_X|c_in> = 1/2")

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

    parametric_actions = [a for a in machine.actions if a.parameters]
    print(f"  Parametric actions : {[(a.name, [(p.name, p.type) for p in a.parameters]) for a in parametric_actions]}")

    call_sites = [t for t in machine.transitions if t.bound_arguments is not None]
    print(f"  Parametric call sites : {len(call_sites)} (one per concept)")

    result = verify(machine, VerifyOptions(skip_dynamic=True))
    status = "VALID" if result.valid else "INVALID"
    print(f"  Verification : {status}")
    error_count = sum(1 for e in result.errors if e.severity == "error")
    warning_count = sum(1 for e in result.errors if e.severity == "warning")
    print(f"  Errors / warnings : {error_count} / {warning_count}")

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

    prep_lines = [line for line in qasm.splitlines() if "q[0]" in line or "q[1]" in line][:4]
    print(f"  QASM prep     : {' ; '.join(prep_lines)}")

    query_lines = [line for line in qasm.splitlines() if line.startswith("h q[")]
    print(f"  QASM queries  : {len(query_lines)} Hadamard call sites emitted in BFS order")

    # 3. 12 independent simulations
    banner("3. Per-concept polysemy scores (12 independent circuits)")
    print(f"  Each run: prep |f> → Hadamard(q_c) → measure all 12 qubits ({SHOTS} shots)")
    print()
    print(f"  {'c':>2}  {'concept':<14}  {'kind':<4}  {'P(|0^12>) empirical':<22}  {'analytic':<10}  {'error':<10}")
    print(f"  {'':>2}  {'':-<14}  {'':-<4}  {'':-<22}  {'':-<10}  {'':-<10}")

    max_abs_error = 0.0
    for c in range(12):
        hit, total = run_one_query(c, shots=SHOTS)
        p = hit / total if total else 0.0
        in_feature = c in IN_FEATURE
        analytic = ANALYTIC_IN if in_feature else ANALYTIC_OUT
        kind = "in" if in_feature else "out"
        err = abs(p - analytic)
        max_abs_error = max(max_abs_error, err)
        bar = "#" * int(p * 30)
        print(f"  {c:>2}  {LARQL_CONCEPTS[c]:<14}  {kind:<4}  {p:>6.3f}  {bar:<22}  {analytic:>6.3f}    {err:>+6.3f}")

    # 4. Cross-talk assessment
    banner("4. Cross-talk analysis")
    print(f"  Max |empirical − analytic| across 12 concepts : {max_abs_error:.3f}")
    print(f"  Monte-Carlo std (Bernoulli, N={SHOTS})         : {(ANALYTIC_OUT * (1 - ANALYTIC_OUT) / SHOTS) ** 0.5:.3f}")
    print()
    print("  The 1/3 floor on concepts 2..11 is not noise — it is the pairwise")
    print("  overlap |<c_i|c_j>|^2 = 1/4 summed over the two in-feature concepts,")
    print("  normalized by |f|^2 = 3. That floor is intrinsic to the non-orthogonal")
    print("  dictionary; it does not decay with more shots.")
    print()
    print("  --- Scaling implication ---")
    print("    Classical SAE at d=12, k=12 concepts  :  O(d·k) inner products, explicit cross-talk term in loss.")
    print("    Quantum polysemy at d=12, k=12        :  one parametric query_concept(c); cross-talk is the Gram matrix.")
    print()
    print("  Caveat: this toy uses a product-family concept basis (H on a single")
    print("  qubit). A true LARQL feature encoding would pack the concepts into a")
    print("  lower-dim subspace; the parametric-action mechanics stay the same.")


if __name__ == "__main__":
    main()
