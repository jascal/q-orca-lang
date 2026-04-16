"""End-to-end pipeline tests for the Bell-pair (BellEntangler) example.

Covers all three compiler backends against examples/bell-entangler.q.orca.md,
validating the exact output strings required by the compiler spec scenarios:
  - "Bell-pair QASM output structure"
  - "CNOT translation across backends"
  - "Qiskit script with simulation options"
  - "Bell-pair Mermaid output structure"
"""

from pathlib import Path

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from q_orca.compiler.mermaid import compile_to_mermaid

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="module")
def bell_machine():
    src = (EXAMPLES_DIR / "bell-entangler.q.orca.md").read_text()
    result = parse_q_orca_markdown(src)
    assert result.file.machines, "No machines parsed from bell-entangler.q.orca.md"
    return result.file.machines[0]


@pytest.fixture(scope="module")
def bell_qasm(bell_machine):
    return compile_to_qasm(bell_machine)


@pytest.fixture(scope="module")
def bell_qiskit(bell_machine):
    return compile_to_qiskit(bell_machine, QSimulationOptions(analytic=True))


@pytest.fixture(scope="module")
def bell_mermaid(bell_machine):
    return compile_to_mermaid(bell_machine)


# ── QASM ─────────────────────────────────────────────────────────────────────

class TestBellPairQASM:
    def test_qasm_header(self, bell_qasm):
        assert "OPENQASM 3.0;" in bell_qasm

    def test_qasm_qubit_register(self, bell_qasm):
        assert "qubit[2] q;" in bell_qasm

    def test_qasm_hadamard(self, bell_qasm):
        assert "h q[0];" in bell_qasm

    def test_qasm_cnot(self, bell_qasm):
        # Compiler spec: "CNOT translation across backends — QASM emits cx q[0], q[1];"
        assert "cx q[0], q[1];" in bell_qasm

    def test_qasm_gate_order(self, bell_qasm):
        # h must appear before cx
        lines = bell_qasm.splitlines()
        h_idx = next(i for i, ln in enumerate(lines) if "h q[0];" in ln)
        cx_idx = next(i for i, ln in enumerate(lines) if "cx q[0], q[1];" in ln)
        assert h_idx < cx_idx


# ── Qiskit ───────────────────────────────────────────────────────────────────

class TestBellPairQiskit:
    def test_qiskit_circuit_size(self, bell_qiskit):
        # Compiler spec: "returned script contains qc = QuantumCircuit(2)"
        assert "QuantumCircuit(2)" in bell_qiskit

    def test_qiskit_hadamard(self, bell_qiskit):
        assert "qc.h(0)" in bell_qiskit

    def test_qiskit_cnot(self, bell_qiskit):
        # Compiler spec: "CNOT translation across backends — Qiskit emits qc.cx(0, 1)"
        assert "qc.cx(0, 1)" in bell_qiskit

    def test_qiskit_analytic_output(self, bell_qiskit):
        # Compiler spec: "produces a probability dictionary on the final print(json.dumps(...))"
        assert "json.dumps" in bell_qiskit


# ── Mermaid ──────────────────────────────────────────────────────────────────

class TestBellPairMermaid:
    def test_mermaid_header(self, bell_mermaid):
        assert bell_mermaid.startswith("stateDiagram-v2")

    def test_mermaid_direction(self, bell_mermaid):
        assert "direction LR" in bell_mermaid

    def test_mermaid_initial_transition(self, bell_mermaid):
        assert "[*] -->" in bell_mermaid

    def test_mermaid_cnot_label(self, bell_mermaid):
        # Compiler spec: "Mermaid renders the action as a transition label ... / apply_CNOT"
        assert "apply_CNOT" in bell_mermaid
