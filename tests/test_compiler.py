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

    def test_custom_measurement_gate_declares_bit_register(self):
        """Bug 2 regression: M(q[0]) custom measurement must emit bit[] declaration."""
        source = """\
# machine CustomMeasure

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]    |

## events
- init
- done

## state |0> [initial]
> Ground

## state |+>
> Superposition

## state |result> [final]
> Measured

## transitions
| Source | Event | Guard | Target   | Action  |
|--------|-------|-------|----------|---------|
| |0>    | init  |       | |+>      | do_H    |
| |+>    | done  |       | |result> | do_M    |

## actions
| Name | Signature    | Effect       |
|------|--------------|--------------|
| do_H | (qs) -> qs  | Hadamard(qs[0]) |
| do_M | (qs) -> bit | M(qs[0])     |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        output = compile_to_qasm(machine)
        assert "bit[" in output, (
            "QASM output missing 'bit[' register declaration for M(q[0]) measurement action"
        )
        assert "measure" in output, (
            "QASM output missing measurement instruction for M(q[0]) action"
        )

    def test_standard_measure_still_works(self, bell_source):
        """The standard measure(...) pattern must still produce bit[] declaration."""
        source = """\
# machine StandardMeasure

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]    |

## events
- init
- collapse

## state |0> [initial]
> Ground

## state |result> [final]
> Measured

## transitions
| Source | Event    | Guard | Target   | Action  |
|--------|----------|-------|----------|---------|
| |0>    | init     |       | |result> | do_meas |

## actions
| Name    | Signature    | Effect            |
|---------|--------------|-------------------|
| do_meas | (qs) -> bit | measure(qs[0])    |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        output = compile_to_qasm(machine)
        assert "bit[" in output


class TestInferQubitCount:
    """Tests for _infer_qubit_count function."""

    def test_n_plus_ancilla(self):
        """Machine with n control qubits + ancilla should return n + 1."""
        source = """\
# machine DeutschJozsa

## context
| Field          | Type          | Default |
|----------------|---------------|---------|
| qubits         | list<qubit>   |         |
| n              | int           | 3       |
| control_qubits | list<qubit>   | qs[0:n] |
| ancilla        | qubit         | qs[n]   |

## events
- init

## state |psi0> [initial]
> Initial

## transitions
| Source | Event | Guard | Target |
|--------|-------|-------|--------|
| |psi0> | init |       | |psi0> |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| noop | (qs) -> qs | Identity |

## verification rules
- unitarity: all gates preserve norm
"""
        from q_orca.compiler.qiskit import _infer_qubit_count
        machine = _machine(source)
        assert _infer_qubit_count(machine) == 4  # n=3 + ancilla=1

    def test_explicit_qubits_list(self):
        """Machine with explicit qubits list should return length of list."""
        source = """\
# machine CustomQubits

## context
| Field   | Type        | Default       |
|---------|-------------|---------------|
| qubits  | list<qubit> | [q0, q1, q2] |

## events
- init

## state |psi0> [initial]
> Initial

## transitions
| Source | Event | Guard | Target |
|--------|-------|-------|--------|
| |psi0> | init |       | |psi0> |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| noop | (qs) -> qs | Identity |

## verification rules
- unitarity: all gates preserve norm
"""
        from q_orca.compiler.qiskit import _infer_qubit_count
        machine = _machine(source)
        assert _infer_qubit_count(machine) == 3

    def test_bitstring_in_state_name(self):
        """Machine with bitstrings in state names should return max bitstring length."""
        source = """\
# machine BitstringMachine

## events
- init

## state |0000> [initial]
> Initial

## state |1111>
> Final

## transitions
| Source | Event | Guard | Target |
|--------|-------|-------|--------|
| |0000> | init |       | |1111> |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| noop | (qs) -> qs | Identity |

## verification rules
- unitarity: all gates preserve norm
"""
        from q_orca.compiler.qiskit import _infer_qubit_count
        machine = _machine(source)
        assert _infer_qubit_count(machine) == 4

    def test_fallback_to_one(self):
        """Machine with no context or bitstrings should default to 1."""
        source = """\
# machine MinimalNoQubits

## events
- go

## state |psi0> [initial]
> Start

## transitions
| Source | Event | Guard | Target |
|--------|-------|-------|--------|
| |psi0> | go   |       | |psi0> |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| noop | (qs) -> qs | Identity |

## verification rules
- unitarity: all gates preserve norm
"""
        from q_orca.compiler.qiskit import _infer_qubit_count
        machine = _machine(source)
        assert _infer_qubit_count(machine) == 1

    def test_n_minus_1_ancilla(self):
        """Machine with n=5 + ancilla should return 6."""
        source = """\
# machine SixQubits

## context
| Field    | Type        | Default |
|----------|-------------|---------|
| qubits   | list<qubit> |         |
| n        | int         | 5       |
| ctrl     | list<qubit> | qs[0:n] |
| ancilla  | qubit       | qs[n]   |

## events
- init

## state |psi0> [initial]
> Initial

## transitions
| Source | Event | Guard | Target |
|--------|-------|-------|--------|
| |psi0> | init |       | |psi0> |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| noop | (qs) -> qs | Identity |

## verification rules
- unitarity: all gates preserve norm
"""
        from q_orca.compiler.qiskit import _infer_qubit_count
        machine = _machine(source)
        assert _infer_qubit_count(machine) == 6  # n=5 + ancilla=1


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

    def test_multi_gate_effects_expanded(self):
        """Multi-gate effects (semicolon-separated) should generate all gates."""
        source = """\
# machine MultiGateTest

## context
| Field   | Type        | Default |
|---------|-------------|---------|
| qubits  | list<qubit> | [q0, q1, q2, q3] |

## events
- init
- apply

## state |s0> [initial]
> Initial

## state |s1>
> After gates

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | init  |       | |s1>   | multi_h |

## actions
| Name     | Signature   | Effect                                |
|----------|-------------|---------------------------------------|
| multi_h  | (qs) -> qs | H(qs[0]); H(qs[1]); H(qs[2]); H(qs[3]) |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        output = compile_to_qiskit(machine, opts)
        # All 4 Hadamards should appear
        assert output.count("qc.h(0)") == 1
        assert output.count("qc.h(1)") == 1
        assert output.count("qc.h(2)") == 1
        assert output.count("qc.h(3)") == 1

    def test_multi_gate_cnot_oracle(self):
        """CNOT gates from semicolon-separated effect should all be generated."""
        source = """\
# machine BVOracle

## context
| Field   | Type        | Default |
|---------|-------------|---------|
| qubits  | list<qubit> | [q0, q1, q2, q3] |

## events
- init
- apply

## state |s0> [initial]
> Initial

## state |s1>
> After oracle

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | init  |       | |s1>   | bv_oracle |

## actions
| Name     | Signature   | Effect                            |
|----------|-------------|-----------------------------------|
| bv_oracle | (qs) -> qs | CNOT(qs[0], qs[3]); CNOT(qs[2], qs[3]) |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        output = compile_to_qiskit(machine, opts)
        # Both CNOTs should appear
        assert "qc.cx(0, 3)" in output
        assert "qc.cx(2, 3)" in output

    def test_qubit_count_from_n_plus_ancilla(self):
        """Machine with n=3 and ancilla should produce 4 qubits."""
        source = """\
# machine BVTest

## context
| Field   | Type        | Default |
|---------|-------------|---------|
| qubits  | list<qubit> |         |
| n       | int         | 3       |
| ancilla | qubit       | qs[n]   |

## events
- init

## state |s0> [initial]
> Initial

## transitions
| Source | Event | Guard | Target |
|--------|-------|-------|--------|
| |s0>   | init  |       | |s0>   | noop |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| noop | (qs) -> qs | H(qs[0]) |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        opts = QSimulationOptions(analytic=True, skip_qutip=True)
        output = compile_to_qiskit(machine, opts)
        assert "qubit_count = 4" in output
        assert "qc = QuantumCircuit(4)" in output


class TestContextAngleCompilation:
    """Verify the QASM and Qiskit backends resolve context-field angle refs."""

    SOURCE = """\
# machine CtxAngleCompile

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0, q1] |
| gamma  | float       | 0.5     |
| beta   | float       | 0.25    |

## events
- run

## state |00> [initial]
## state |out> [final]

## transitions
| Source | Event | Guard | Target | Action  |
|--------|-------|-------|--------|---------|
| |00>   | run   |       | |out>  | rotate  |

## actions
| Name   | Signature  | Effect                                       |
|--------|------------|----------------------------------------------|
| rotate | (qs) -> qs | Rx(qs[0], gamma); RZZ(qs[0], qs[1], beta)    |
"""

    def test_qasm_emits_resolved_angle(self):
        machine = _machine(self.SOURCE)
        out = compile_to_qasm(machine)
        # Rx(gamma) → rx(0.5) on q[0]; RZZ(beta) is decomposed into
        # `cx q0,q1; rz(0.25) q[1]; cx q0,q1;`.
        assert "rx(0.5) q[0];" in out
        assert "rz(0.25) q[1];" in out

    def test_qiskit_emits_resolved_angle(self):
        machine = _machine(self.SOURCE)
        out = compile_to_qiskit(machine, QSimulationOptions(analytic=True, skip_qutip=True))
        assert "qc.rx(0.5, 0)" in out
        assert "qc.rzz(0.25, 0, 1)" in out
