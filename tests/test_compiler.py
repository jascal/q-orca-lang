"""Tests for Q-Orca compilers (Mermaid, QASM, Qiskit)."""

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.compiler.mermaid import compile_to_mermaid
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions


def _machine(source: str):
    return parse_q_orca_markdown(source).file.machines[0]


class TestMermaidCompiler:
    def test_produces_state_diagram(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_mermaid(machine)
        assert "stateDiagram-v2" in output

    def test_contains_states(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_mermaid(machine)
        assert "|00>" in output
        assert "|ψ>" in output

    def test_contains_initial_transition(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_mermaid(machine)
        assert "[*] -->" in output

    def test_contains_final_transitions(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_mermaid(machine)
        assert "--> [*]" in output

    def test_contains_event_labels(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_mermaid(machine)
        assert "prepare_H" in output
        assert "entangle" in output
        assert "measure_done" in output

    def test_contains_guard_labels(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_mermaid(machine)
        assert "prob_collapse" in output

    def test_contains_verification_note(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_mermaid(machine)
        assert "Verification Rules" in output

    def test_minimal_machine(self, minimal_source):
        machine = _machine(minimal_source)
        output = compile_to_mermaid(machine)
        assert "stateDiagram-v2" in output
        assert "[*] -->" in output
        assert "--> [*]" in output


class TestQASMCompiler:
    def test_produces_openqasm(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_qasm(machine)
        assert "OPENQASM 3.0" in output

    def test_declares_qubits(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_qasm(machine)
        assert "qubit[" in output

    def test_contains_hadamard_gate(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_qasm(machine)
        assert "h q[0]" in output

    def test_contains_cnot_gate(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_qasm(machine)
        assert "cx q[0], q[1]" in output

    def test_contains_measurement(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_qasm(machine)
        assert "measure" in output

    def test_machine_name_in_comment(self, bell_source):
        machine = _machine(bell_source)
        output = compile_to_qasm(machine)
        assert "BellEntangler" in output


class TestQiskitCompiler:
    def test_produces_python_script(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True)
        output = compile_to_qiskit(machine, opts)
        assert "QuantumCircuit" in output
        assert "Statevector" in output

    def test_contains_gates(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True)
        output = compile_to_qiskit(machine, opts)
        assert "qc.h(0)" in output
        assert "qc.cx(0, 1)" in output

    def test_analytic_mode(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True)
        output = compile_to_qiskit(machine, opts)
        assert "Statevector" in output
        assert "prob_dict" in output

    def test_shots_mode(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=False, shots=2048)
        output = compile_to_qiskit(machine, opts)
        assert "shots = 2048" in output
        assert "BasicSimulator" in output

    def test_skip_qutip(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        output = compile_to_qiskit(machine, opts)
        assert "qutip" not in output.lower() or "skip" in output.lower()

    def test_qutip_uses_operator(self, bell_source):
        """Unitarity check must use Operator(qc), not qc.unitary_matrix()."""
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True, skip_qutip=False)
        output = compile_to_qiskit(machine, opts)
        assert "Operator(qc)" in output
        assert "unitary_matrix()" not in output

    def test_numpy_bools_wrapped(self, bell_source):
        """Numpy bool comparisons must be wrapped in bool() for JSON serialization."""
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True, skip_qutip=False)
        output = compile_to_qiskit(machine, opts)
        assert "bool(unitarity_error" in output
        assert "bool(schmidt_rank" in output

    def test_machine_name_in_comment(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True)
        output = compile_to_qiskit(machine, opts)
        assert "BellEntangler" in output

    def test_json_output(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True)
        output = compile_to_qiskit(machine, opts)
        assert "json.dumps" in output
