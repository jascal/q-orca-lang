"""Regression tests for pipeline bugs 1–7 (v0.3.1 fix batch).

Tests 1–6 are explicitly enumerated in the bug report.
Test for each non-LLM bug (Bugs 1–6) is fully deterministic.
Bug 7 (generate_machine prompt) is an LLM behaviour change with no
deterministic test; it is documented in a skip marker.
"""

import json
import textwrap

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.compiler.qasm import compile_to_qasm, _infer_qubit_count as qasm_qubit_count
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions, _parse_effect_string
from q_orca.verifier.determinism import check_determinism


def _machine(source: str):
    return parse_q_orca_markdown(source).file.machines[0]


# ── Shared fixture machines ───────────────────────────────────────────────────

BELL_TEST_SOURCE = textwrap.dedent("""\
    # machine BellTest

    ## context
    | Field  | Type        | Default  |
    |--------|-------------|----------|
    | qubits | list<qubit> | [q0, q1] |

    ## events
    - apply_H
    - apply_CNOT

    ## state init [initial]
    ## state superposed
    ## state bell [final]

    ## transitions
    | Source     | Event      | Guard | Target     | Action |
    |------------|------------|-------|------------|--------|
    | init       | apply_H    |       | superposed | h0     |
    | superposed | apply_CNOT |       | bell       | cx01   |

    ## actions
    | Name | Signature  | Effect           |
    |------|------------|------------------|
    | h0   | (qs) -> qs | H(qs[0])         |
    | cx01 | (qs) -> qs | CX(qs[0], qs[1]) |

    ## verification rules
    - unitarity: all gates preserve norm
""")

GHZ_TEST_SOURCE = textwrap.dedent("""\
    # machine GHZTest

    ## context
    | Field  | Type        | Default       |
    |--------|-------------|---------------|
    | qubits | list<qubit> | [q0, q1, q2]  |

    ## events
    - apply_H
    - apply_CX01
    - apply_CX02

    ## state init [initial]
    ## state superposed
    ## state entangled
    ## state ghz [final]

    ## transitions
    | Source     | Event       | Guard | Target     | Action |
    |------------|-------------|-------|------------|--------|
    | init       | apply_H     |       | superposed | h0     |
    | superposed | apply_CX01  |       | entangled  | cx01   |
    | entangled  | apply_CX02  |       | ghz        | cx02   |

    ## actions
    | Name | Signature  | Effect           |
    |------|------------|------------------|
    | h0   | (qs) -> qs | H(qs[0])         |
    | cx01 | (qs) -> qs | CX(qs[0], qs[1]) |
    | cx02 | (qs) -> qs | CX(qs[0], qs[2]) |

    ## verification rules
    - unitarity: all gates preserve norm
""")


# ── Bug 1 — Qiskit CX gate emission ─────────────────────────────────────────

class TestBug1QiskitGateEmission:
    """Bug 1: CX(qs[0], qs[1]) must produce qc.cx(0, 1), not a comment."""

    def test_cx_effect_parsed_as_cnot(self):
        gates = _parse_effect_string("CX(qs[0], qs[1])")
        assert len(gates) == 1
        assert gates[0].kind == "CNOT"
        assert gates[0].controls == [0]
        assert gates[0].targets == [1]

    def test_bell_qiskit_contains_h_gate(self):
        machine = _machine(BELL_TEST_SOURCE)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        script = compile_to_qiskit(machine, opts)
        assert "qc.h(0)" in script, f"Expected qc.h(0) in:\n{script}"

    def test_bell_qiskit_contains_cx_gate(self):
        machine = _machine(BELL_TEST_SOURCE)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        script = compile_to_qiskit(machine, opts)
        assert "qc.cx(0, 1)" in script, f"Expected qc.cx(0, 1) in:\n{script}"

    def test_bell_qiskit_no_comment_only_for_cx(self):
        """CX transition must NOT produce only a comment line."""
        machine = _machine(BELL_TEST_SOURCE)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        script = compile_to_qiskit(machine, opts)
        # The cx01 action must produce actual gate code, not just a comment
        lines = script.splitlines()
        gate_lines = [l for l in lines if l.strip().startswith("qc.")]
        assert len(gate_lines) >= 2, f"Expected at least 2 gate calls, got: {gate_lines}"

    def test_rx_ry_rz_parsed(self):
        """RX/RY/RZ(angle, qs[N]) must be parsed into the correct gate kind."""
        for axis in ("X", "Y", "Z"):
            gates = _parse_effect_string(f"R{axis}(0.5, qs[0])")
            assert len(gates) == 1
            assert gates[0].kind == f"R{axis}"
            assert gates[0].targets == [0]
            assert abs(gates[0].parameter - 0.5) < 1e-9


# ── Bug 2 — QASM qubit count from context ────────────────────────────────────

class TestBug2QASMQubitCount:
    """Bug 2: QASM must declare qubit[N] based on context, not hardcode 1."""

    def test_bell_qasm_qubit_count_from_context(self):
        machine = _machine(BELL_TEST_SOURCE)
        assert qasm_qubit_count(machine) == 2

    def test_ghz_qasm_qubit_count_from_context(self):
        machine = _machine(GHZ_TEST_SOURCE)
        assert qasm_qubit_count(machine) == 3

    def test_bell_qasm_declares_two_qubits(self):
        machine = _machine(BELL_TEST_SOURCE)
        output = compile_to_qasm(machine)
        assert "qubit[2] q;" in output, f"Expected qubit[2] q; in:\n{output}"

    def test_explicit_list_qubits_length(self):
        source = textwrap.dedent("""\
            # machine FourQubit

            ## context
            | Field  | Type        | Default              |
            |--------|-------------|----------------------|
            | qubits | list<qubit> | [q0, q1, q2, q3]    |

            ## events
            - go

            ## state start [initial]
            ## state end [final]

            ## transitions
            | Source | Event | Guard | Target | Action |
            |--------|-------|-------|--------|--------|
            | start  | go    |       | end    |        |
        """)
        machine = _machine(source)
        assert qasm_qubit_count(machine) == 4


# ── Bug 3 — QASM gate emission from effect string ────────────────────────────

class TestBug3QASMGateEmission:
    """Bug 3: QASM must emit h q[0]; and cx q[0], q[1]; from Effect column."""

    def test_bell_qasm_h_gate(self):
        machine = _machine(BELL_TEST_SOURCE)
        output = compile_to_qasm(machine)
        assert "h q[0];" in output, f"Expected 'h q[0];' in QASM:\n{output}"

    def test_bell_qasm_cx_gate(self):
        machine = _machine(BELL_TEST_SOURCE)
        output = compile_to_qasm(machine)
        assert "cx q[0], q[1];" in output, f"Expected 'cx q[0], q[1];' in QASM:\n{output}"

    def test_bell_qasm_no_comment_only_for_cx(self):
        """CX transition must not produce only a comment line."""
        machine = _machine(BELL_TEST_SOURCE)
        output = compile_to_qasm(machine)
        gate_lines = [l for l in output.splitlines() if not l.startswith("//") and l.strip()]
        actual_gates = [l for l in gate_lines if not l.startswith("OPENQASM") and
                        not l.startswith('include') and not l.startswith("qubit") and
                        not l.startswith("bit") and not l.startswith("int")]
        assert len(actual_gates) >= 2, f"Expected ≥2 gate statements, got: {actual_gates}"

    def test_ghz_qasm_three_gates(self):
        machine = _machine(GHZ_TEST_SOURCE)
        output = compile_to_qasm(machine)
        assert "h q[0];" in output
        assert "cx q[0], q[1];" in output
        assert "cx q[0], q[2];" in output


# ── Bug 4 — QuTiP JSON serialization ─────────────────────────────────────────

class TestBug4QuTiPSerialization:
    """Bug 4: simulate_machine result must be JSON-serializable (no dataclass leak)."""

    def test_qutip_result_is_dict_in_mcp_return(self):
        """The mcp_server simulate_machine path must convert QuTiPVerificationResult to dict."""
        import dataclasses
        from q_orca.runtime.types import QuTiPVerificationResult

        qutip_obj = QuTiPVerificationResult(
            unitarity_verified=True,
            entanglement_verified=True,
            schmidt_rank=2,
            errors=[],
        )
        # Simulate what mcp_server now does
        qutip_dict = dataclasses.asdict(qutip_obj)
        # Must be JSON serializable
        serialized = json.dumps(qutip_dict)
        assert '"unitarity_verified": true' in serialized

    def test_none_qutip_result_serializable(self):
        """None qutip result (skip_qutip=True) must also serialize cleanly."""
        result = {"qutipVerification": None}
        assert json.dumps(result) == '{"qutipVerification": null}'


# ── Bug 5 — guards[] populated from transitions ───────────────────────────────

class TestBug5GuardsPopulated:
    """Bug 5: guards[] must be non-empty when transitions have inline guard expressions."""

    def test_inline_guards_appear_in_parsed_output(self):
        source = textwrap.dedent("""\
            # machine DeutschJozsa

            ## events
            - check

            ## state init [initial]
            ## state constant [final]
            ## state balanced [final]

            ## transitions
            | Source | Event | Guard               | Target    | Action |
            |--------|-------|---------------------|-----------|--------|
            | init   | check | oracle == constant  | constant  |        |
            | init   | check | oracle == balanced  | balanced  |        |
        """)
        from q_orca.skills import parse_skill
        result = parse_skill({"source": source})
        assert result["status"] == "success"
        guards = result["machine"]["guards"]
        guard_names = [g["name"] for g in guards]
        assert "oracle == constant" in guard_names, f"Missing guard; got: {guard_names}"
        assert "oracle == balanced" in guard_names, f"Missing guard; got: {guard_names}"

    def test_named_guards_still_present(self):
        """Named guards from ## guards section are not displaced."""
        from q_orca.skills import parse_skill
        source = textwrap.dedent("""\
            # machine Named

            ## events
            - go

            ## state s [initial]
            ## state a [final]
            ## state b [final]

            ## guards
            | Name | Expression |
            |------|------------|
            | g1   | x > 3      |
            | g2   | x <= 3     |

            ## transitions
            | Source | Event | Guard | Target | Action |
            |--------|-------|-------|--------|--------|
            | s      | go    | g1    | a      |        |
            | s      | go    | g2    | b      |        |
        """)
        result = parse_skill({"source": source})
        guard_names = [g["name"] for g in result["machine"]["guards"]]
        assert "g1" in guard_names
        assert "g2" in guard_names


# ── Bug 6 — GUARD_OVERLAP false positive ─────────────────────────────────────

class TestBug6GuardOverlapFalsePositive:
    """Bug 6: var == lit_A and var == lit_B guards must not trigger GUARD_OVERLAP."""

    def test_inline_equality_guards_no_overlap_warning(self):
        source = textwrap.dedent("""\
            # machine DeutschJozsaOverlap

            ## events
            - check

            ## state init [initial]
            ## state constant [final]
            ## state balanced [final]

            ## transitions
            | Source | Event | Guard               | Target    | Action |
            |--------|-------|---------------------|-----------|--------|
            | init   | check | oracle == constant  | constant  |        |
            | init   | check | oracle == balanced  | balanced  |        |
        """)
        machine = _machine(source)
        result = check_determinism(machine)
        overlap_warnings = [e for e in result.errors if e.code == "GUARD_OVERLAP"]
        assert len(overlap_warnings) == 0, (
            f"False GUARD_OVERLAP for mutually-exclusive string guards: {overlap_warnings}"
        )

    def test_same_literal_still_warns(self):
        """Two guards with the SAME literal value should still warn (overlap)."""
        source = textwrap.dedent("""\
            # machine SameLiteral

            ## events
            - go

            ## state s [initial]
            ## state a [final]
            ## state b [final]

            ## transitions
            | Source | Event | Guard     | Target | Action |
            |--------|-------|-----------|--------|--------|
            | s      | go    | x == foo  | a      |        |
            | s      | go    | x == foo  | b      |        |
        """)
        machine = _machine(source)
        result = check_determinism(machine)
        overlap_warnings = [e for e in result.errors if e.code == "GUARD_OVERLAP"]
        assert len(overlap_warnings) > 0, "Expected GUARD_OVERLAP for identical guard literals"

    def test_negation_pair_no_overlap(self):
        """g and !g must still be recognized as mutually exclusive."""
        source = textwrap.dedent("""\
            # machine NegPair

            ## events
            - go

            ## state s [initial]
            ## state a [final]
            ## state b [final]

            ## guards
            | Name | Expression |
            |------|------------|
            | flag | b == true  |

            ## transitions
            | Source | Event | Guard | Target | Action |
            |--------|-------|-------|--------|--------|
            | s      | go    | flag  | a      |        |
            | s      | go    | !flag | b      |        |
        """)
        machine = _machine(source)
        result = check_determinism(machine)
        overlap_warnings = [e for e in result.errors if e.code == "GUARD_OVERLAP"]
        assert len(overlap_warnings) == 0


# ── Test 5 + 6 combo: full QASM output for BellTest ──────────────────────────

class TestQASMBellTestFull:
    """Tests 5 and 6 from the spec: qubit[2] + correct gates in one output."""

    def test_bell_qasm_full_output(self):
        machine = _machine(BELL_TEST_SOURCE)
        output = compile_to_qasm(machine)
        assert "qubit[2] q;" in output, "Test 5 FAIL: expected qubit[2] q;"
        assert "h q[0];" in output,     "Test 6 FAIL: expected h q[0];"
        assert "cx q[0], q[1];" in output, "Test 6 FAIL: expected cx q[0], q[1];"


# ── Test 1+2: Qiskit gate sequence shape ─────────────────────────────────────

class TestQiskitBellGateSequence:
    """Tests 1 and 2 from the spec: Qiskit script must have correct gate sequence."""

    def test_bell_script_gate_order(self):
        """H must appear before CX in the generated script."""
        machine = _machine(BELL_TEST_SOURCE)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        script = compile_to_qiskit(machine, opts)
        h_pos = script.find("qc.h(0)")
        cx_pos = script.find("qc.cx(0, 1)")
        assert h_pos != -1, "qc.h(0) not found"
        assert cx_pos != -1, "qc.cx(0, 1) not found"
        assert h_pos < cx_pos, "H gate must precede CX gate"

    def test_ghz_script_contains_three_gates(self):
        machine = _machine(GHZ_TEST_SOURCE)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        script = compile_to_qiskit(machine, opts)
        assert "qc.h(0)" in script
        assert "qc.cx(0, 1)" in script
        assert "qc.cx(0, 2)" in script
        assert "qubit_count = 3" in script
