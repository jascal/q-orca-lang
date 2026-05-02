"""Tests for example machines."""

import json
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

EXAMPLE_FILES = {
    "bell-entangler": "bell-entangler.q.orca.md",
    "deutsch-jozsa": "deutsch-jozsa.q.orca.md",
    "ghz-state": "ghz-state.q.orca.md",
    "quantum-teleportation": "quantum-teleportation.q.orca.md",
    "vqe-heisenberg": "vqe-heisenberg.q.orca.md",
    "vqe-rotation": "vqe-rotation.q.orca.md",
    "larql-polysemantic-2": "larql-polysemantic-2.q.orca.md",
    "larql-polysemantic-12": "larql-polysemantic-12.q.orca.md",
    "larql-polysemantic-clusters": "larql-polysemantic-clusters.q.orca.md",
    "larql-polysemantic-hierarchical": "larql-polysemantic-hierarchical.q.orca.md",
}


@pytest.fixture(params=list(EXAMPLE_FILES.keys()))
def example_file(request):
    """Yield (name, path) for each example."""
    name = request.param
    return name, EXAMPLES_DIR / EXAMPLE_FILES[name]


class TestExamples:
    def test_verify_all_examples(self, example_file):
        """Each example must verify successfully."""
        from q_orca.skills import verify_skill

        name, path = example_file
        result = verify_skill({"file": str(path)})
        assert result["status"] == "valid", f"{name} verification failed: {result['errors']}"

    def test_bell_entangler_ast_snapshot(self):
        """Snapshot test: BellEntangler AST must not change unexpectedly."""
        from q_orca.parser.markdown_parser import parse_q_orca_markdown

        source = (EXAMPLES_DIR / "bell-entangler.q.orca.md").read_text()
        result = parse_q_orca_markdown(source)
        machine = result.file.machines[0]

        # Build a serializable representation
        snapshot = {
            "name": machine.name,
            "num_states": len(machine.states),
            "num_events": len(machine.events),
            "num_transitions": len(machine.transitions),
            "num_actions": len(machine.actions),
            "states": sorted(s.name for s in machine.states),
            "events": sorted(e.name for e in machine.events),
            "context_fields": sorted(f.name for f in machine.context),
        }

        # Serialize to JSON for comparison
        snapshot_json = json.dumps(snapshot, sort_keys=True, indent=2)

        # The snapshot should be stable — any change is a breaking change
        expected = {
            "context_fields": ["outcome", "qubits"],
            "events": sorted(["prepare_H", "entangle", "measure_done"]),
            "name": "BellEntangler",
            "num_actions": 4,
            "num_events": 3,
            "num_states": 5,
            "num_transitions": 4,
            "states": sorted(["|00>", "|+0>", "|ψ>", "|00_collapsed>", "|11_collapsed>"]),
        }
        expected_json = json.dumps(expected, sort_keys=True, indent=2)

        assert snapshot_json == expected_json, (
            f"BellEntangler AST snapshot mismatch. "
            f"If this is intentional, update the expected dict in test_examples.py.\n"
            f"Got:\n{snapshot_json}\nExpected:\n{expected_json}"
        )

    def test_larql_polysemantic_12_pipeline(self):
        """End-to-end: parse → verify → compile (QASM + Qiskit + Mermaid).

        Covers task 7.4 of extend-gate-set-and-parametric-actions: the
        12-call-site parametric-action machine must pass every stage of the
        pipeline. Simulation is exercised by demos/larql_polysemantic_12/demo.py.
        """
        from q_orca import (
            QSimulationOptions,
            VerifyOptions,
            compile_to_mermaid,
            compile_to_qasm,
            compile_to_qiskit,
            parse_q_orca_markdown,
            verify,
        )

        source = (EXAMPLES_DIR / "larql-polysemantic-12.q.orca.md").read_text()
        parsed = parse_q_orca_markdown(source)
        assert parsed.errors == []
        machine = parsed.file.machines[0]

        parametric_actions = [a for a in machine.actions if a.parameters]
        assert len(parametric_actions) == 1
        assert parametric_actions[0].name == "query_concept"
        assert [(p.name, p.type) for p in parametric_actions[0].parameters] == [("c", "int")]

        call_sites = [t for t in machine.transitions if t.bound_arguments is not None]
        assert len(call_sites) == 12, f"expected 12 parametric call sites, got {len(call_sites)}"
        bound_values = sorted(int(t.bound_arguments[0].value) for t in call_sites)
        assert bound_values == list(range(12))

        result = verify(machine, VerifyOptions(skip_dynamic=True))
        assert result.valid, [e for e in result.errors if e.severity == "error"]

        qasm = compile_to_qasm(machine)
        assert "qubit[12] q;" in qasm
        assert qasm.count("h q[") == 12  # one Hadamard per expanded call site

        mermaid = compile_to_mermaid(machine)
        assert "LarqlPolysemantic12" in mermaid or "feature_loaded" in mermaid

        qiskit_script = compile_to_qiskit(
            machine,
            QSimulationOptions(analytic=False, shots=0, run=False, skip_qutip=True),
        )
        assert "QuantumCircuit(12)" in qiskit_script
        assert qiskit_script.count("qc.h(") == 12

    def test_larql_polysemantic_clusters_pipeline(self):
        """End-to-end: parse → verify → compile (QASM + Qiskit + Mermaid) →
        concept-gram block structure.

        Covers task 4.2 of add-polysemantic-clusters: the 12-call-site
        multi-angle parametric machine must parse clean, verify, compile to
        a 3-qubit register, and produce a 12×12 Gram matrix whose intra-
        and inter-cluster blocks satisfy the documented tier separation.
        """
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

        source = (
            EXAMPLES_DIR / "larql-polysemantic-clusters.q.orca.md"
        ).read_text()
        parsed = parse_q_orca_markdown(source)
        assert parsed.errors == []
        machine = parsed.file.machines[0]

        parametric_actions = {a.name: a for a in machine.actions if a.parameters}
        assert set(parametric_actions) == {"prepare_concept", "query_concept"}
        for name in ("prepare_concept", "query_concept"):
            params = parametric_actions[name].parameters
            assert [(p.name, p.type) for p in params] == [
                ("a", "angle"),
                ("b", "angle"),
                ("c", "angle"),
            ], f"{name} signature shape mismatch"

        query_call_sites = [
            t for t in machine.transitions if t.action == "query_concept"
        ]
        assert len(query_call_sites) == 12

        result = verify(machine, VerifyOptions(skip_dynamic=True))
        assert result.valid, [e for e in result.errors if e.severity == "error"]

        qasm = compile_to_qasm(machine)
        assert "qubit[3] q;" in qasm

        mermaid = compile_to_mermaid(machine)
        assert "LarqlPolysemanticClusters" in mermaid or "feature_loaded" in mermaid

        qiskit_script = compile_to_qiskit(
            machine,
            QSimulationOptions(analytic=False, shots=0, run=False, skip_qutip=True),
        )
        assert "QuantumCircuit(3)" in qiskit_script
        # 3 Ry for prepare + 3 Ry per query × 12 queries = 39
        assert qiskit_script.count("qc.ry(") == 39

        gram = compute_concept_gram(machine)
        assert gram.shape == (12, 12)
        gsq = np.abs(gram) ** 2

        # Intra-cluster 4×4 diagonal blocks: off-diagonal |<c_i|c_j>|² ≈ 0.72
        for ci in range(3):
            block = gsq[ci * 4:(ci + 1) * 4, ci * 4:(ci + 1) * 4]
            off_diag = block[~np.eye(4, dtype=bool)]
            assert np.all(off_diag >= 0.65), (
                f"cluster {ci} intra-overlap min {off_diag.min()} < 0.65"
            )
            assert np.all(off_diag <= 0.75), (
                f"cluster {ci} intra-overlap max {off_diag.max()} > 0.75"
            )

        # Inter-cluster 4×4 off-diagonal blocks: |<c_i|c_j>|² < 0.10
        for i in range(3):
            for j in range(i + 1, 3):
                block = gsq[i * 4:(i + 1) * 4, j * 4:(j + 1) * 4]
                assert np.all(block < 0.10), (
                    f"clusters {i}<->{j} inter-overlap max {block.max()} ≥ 0.10"
                )

        # Diagonal must be exactly 1 (self-overlap).
        np.testing.assert_allclose(np.diag(gsq), np.ones(12), atol=1e-9)

    def test_larql_polysemantic_hierarchical_pipeline(self):
        """End-to-end: parse → verify → compile (QASM + Qiskit + Mermaid) →
        MPS-bond-2 concept gram four-tier hierarchy.

        Covers task 4.2 of add-mps-concept-encoding: the 12-call-site
        CNOT-staircase parametric machine must parse clean, verify, compile
        to a 3-qubit register with the expected ry/cx counts, and produce a
        12×12 Gram matrix whose four off-diagonal tiers (self / sub-cluster-
        mate / super-group-sibling / cross-group) are strictly ordered.
        """
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

        source = (
            EXAMPLES_DIR / "larql-polysemantic-hierarchical.q.orca.md"
        ).read_text()
        parsed = parse_q_orca_markdown(source)
        assert parsed.errors == []
        machine = parsed.file.machines[0]

        parametric_actions = {a.name: a for a in machine.actions if a.parameters}
        assert set(parametric_actions) == {"prepare_concept", "query_concept"}
        for name in ("prepare_concept", "query_concept"):
            params = parametric_actions[name].parameters
            assert [(p.name, p.type) for p in params] == [
                ("a", "angle"),
                ("b", "angle"),
                ("c", "angle"),
            ], f"{name} signature shape mismatch"

        query_call_sites = [
            t for t in machine.transitions if t.action == "query_concept"
        ]
        assert len(query_call_sites) == 12

        result = verify(machine, VerifyOptions(skip_dynamic=True))
        assert result.valid, [e for e in result.errors if e.severity == "error"]

        qasm = compile_to_qasm(machine)
        assert "qubit[3] q;" in qasm

        mermaid = compile_to_mermaid(machine)
        assert (
            "LarqlPolysemanticHierarchical" in mermaid
            or "feature_loaded" in mermaid
        )

        qiskit_script = compile_to_qiskit(
            machine,
            QSimulationOptions(analytic=False, shots=0, run=False, skip_qutip=True),
        )
        assert "QuantumCircuit(3)" in qiskit_script
        # Each parametric action emits 3 Ry + 2 CNOT (CNOT staircase). With
        # 1 prepare + 12 query call sites = 13 transitions, we expect
        # 13 × 3 = 39 ry and 13 × 2 = 26 cx — i.e., 65 gates total.
        assert qiskit_script.count("qc.ry(") == 39
        assert qiskit_script.count("qc.cx(") == 26

        gram = compute_concept_gram_mps(machine)
        assert gram.shape == (12, 12)
        gsq = np.abs(gram) ** 2

        # Diagonal must be exactly 1 (self-overlap).
        np.testing.assert_allclose(np.diag(gsq), np.ones(12), atol=1e-9)

        # Tier classification by (super-group, sub-cluster) coordinates: i //
        # 4 is the super-group index, (i // 2) % 2 is the sub-cluster index
        # within the super-group.
        sub_mate_pairs = []
        super_sib_pairs = []
        cross_pairs = []
        for i in range(12):
            gi, si = i // 4, (i // 2) % 2
            for j in range(i + 1, 12):
                gj, sj = j // 4, (j // 2) % 2
                v = gsq[i, j]
                if gi == gj and si == sj:
                    sub_mate_pairs.append(v)
                elif gi == gj:
                    super_sib_pairs.append(v)
                else:
                    cross_pairs.append(v)
        assert len(sub_mate_pairs) == 6
        assert len(super_sib_pairs) == 12
        assert len(cross_pairs) == 48

        sub_min, sub_max = min(sub_mate_pairs), max(sub_mate_pairs)
        sup_min, sup_max = min(super_sib_pairs), max(super_sib_pairs)
        cr_min, cr_max = min(cross_pairs), max(cross_pairs)

        # Sub-cluster-mate tier: tight band around 0.882 (analytic
        # cos²(0.35) for the γ-only difference under cross-coupled angles).
        assert 0.87 <= sub_min <= sub_max <= 0.90, (
            f"sub-cluster-mate tier outside [0.87, 0.90]: "
            f"min={sub_min:.4f} max={sub_max:.4f}"
        )

        # Super-group-sibling tier: three discrete values
        # {0.335, 0.593, 0.753} per super-group block under cross-coupling.
        assert 0.32 <= sup_min and sup_max <= 0.77, (
            f"super-group-sibling tier outside [0.32, 0.77]: "
            f"min={sup_min:.4f} max={sup_max:.4f}"
        )

        # Cross-group tier: range [0.000, 0.178] under cross-coupled
        # encoding with cyclic α at 2π/3 spacing.
        assert cr_max <= 0.20, (
            f"cross-group tier max above 0.20: max={cr_max:.4f}"
        )

        # Tier ordering: sub > super > cross (strict separation, ≥ 0.05
        # margin between adjacent bands per the spec).
        assert sub_min - sup_max >= 0.05, (
            f"insufficient sub→super gap: "
            f"sub_min={sub_min:.4f} super_max={sup_max:.4f}"
        )
        assert sup_min - cr_max >= 0.05, (
            f"insufficient super→cross gap: "
            f"super_min={sup_min:.4f} cross_max={cr_max:.4f}"
        )

        # Non-factorization criterion: the cross-coupled MPS Gram differs
        # measurably from the same-angle product-state Gram. The bare
        # staircase (single-bound-param Ry rotations) factorizes as
        # ∏_k cos((θ_{i,k} − θ_{j,k})/2); the cross-coupled variant must
        # break that factorization on at least one off-diagonal entry.
        triples = [
            tuple(b.value for b in t.bound_arguments) for t in query_call_sites
        ]
        gram_prod = np.zeros((12, 12))
        for i in range(12):
            ai, bi, ci = triples[i]
            for j in range(12):
                aj, bj, cj = triples[j]
                gram_prod[i, j] = (
                    np.cos((ai - aj) / 2)
                    * np.cos((bi - bj) / 2)
                    * np.cos((ci - cj) / 2)
                )
        diff = np.abs(gsq - gram_prod ** 2)
        # Zero out the diagonal (both Grams give 1 there).
        np.fill_diagonal(diff, 0.0)
        assert diff.max() >= 0.05, (
            "cross-coupled Gram unexpectedly factorizes: "
            f"max |gram_mps^2 − gram_prod^2| = {diff.max():.6f} < 0.05"
        )
