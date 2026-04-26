"""Tests for Q-Orca compilers (Mermaid, QASM, Qiskit)."""

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.compiler.mermaid import compile_to_mermaid
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from tests.fixtures.effect_strings import EFFECT_STRING_CASES


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

    def test_shots_mode_unseeded_omits_seed_kwarg(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=False, shots=1024)
        output = compile_to_qiskit(machine, opts)
        assert "seed_simulator" not in output

    def test_shots_mode_seeded_threads_seed_kwarg(self, bell_source):
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=False, shots=1024, seed_simulator=7)
        output = compile_to_qiskit(machine, opts)
        assert "backend.run(qc_shots, shots=shots, seed_simulator=7)" in output
        assert "noisy_backend.run(qc_shots, shots=shots, seed_simulator=7)" in output

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


def _multi_controlled_source(effect: str, qubits: str = "[q0, q1, q2]") -> str:
    return f"""\
# machine MultiCtrl

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | {qubits} |

## events
- run

## state |s0> [initial]
> Start

## state |s1> [final]
> End

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | run   |       | |s1>   | apply  |

## actions
| Name  | Signature   | Effect   |
|-------|-------------|----------|
| apply | (qs) -> qs  | {effect} |

## verification rules
- unitarity: all gates preserve norm
"""


class TestMultiControlledGateEmission:
    """QASM and Qiskit emission for CCZ/MCX/MCZ mirrors the CNOT/CCNOT cases."""

    # --- CCZ (two controls + one target) ---

    def test_qasm_ccz_expands_to_h_ccx_h_sandwich(self):
        source = _multi_controlled_source("CCZ(qs[0], qs[1], qs[2])")
        out = compile_to_qasm(_machine(source))
        # CCZ is emitted as `h q[t]; ccx q[c0], q[c1], q[t]; h q[t];` on one line.
        assert "h q[2]; ccx q[0], q[1], q[2]; h q[2];" in out

    def test_qiskit_ccz_expands_to_h_ccx_h_sandwich(self):
        source = _multi_controlled_source("CCZ(qs[0], qs[1], qs[2])")
        out = compile_to_qiskit(_machine(source), QSimulationOptions(analytic=True, skip_qutip=True))
        # Qiskit emits a 3-line block: pre-H, CCX, post-H. Line ordering is the
        # load-bearing assertion — swapping pre/post-H breaks the CCZ identity.
        idx_pre = out.index("qc.h(2)")
        idx_ccx = out.index("qc.ccx(0, 1, 2)")
        idx_post = out.index("qc.h(2)", idx_pre + 1)
        assert idx_pre < idx_ccx < idx_post

    # --- MCX (≥2 controls + one target) ---

    def test_qasm_mcx_emits_ctrl_n_x(self):
        source = _multi_controlled_source(
            "MCX(qs[0], qs[1], qs[2], qs[3])",
            qubits="[q0, q1, q2, q3]",
        )
        out = compile_to_qasm(_machine(source))
        assert "ctrl(3) @ x q[0], q[1], q[2], q[3];" in out

    def test_qiskit_mcx_emits_mcx_list_target(self):
        source = _multi_controlled_source(
            "MCX(qs[0], qs[1], qs[2], qs[3])",
            qubits="[q0, q1, q2, q3]",
        )
        out = compile_to_qiskit(_machine(source), QSimulationOptions(analytic=True, skip_qutip=True))
        assert "qc.mcx([0, 1, 2], 3)" in out

    # --- MCZ (H-sandwich around MCX) ---

    def test_qasm_mcz_expands_to_h_ctrl_n_x_h_sandwich(self):
        source = _multi_controlled_source(
            "MCZ(qs[0], qs[1], qs[2], qs[3])",
            qubits="[q0, q1, q2, q3]",
        )
        out = compile_to_qasm(_machine(source))
        assert "h q[3]; ctrl(3) @ x q[0], q[1], q[2], q[3]; h q[3];" in out

    def test_qiskit_mcz_expands_to_h_mcx_h_sandwich(self):
        source = _multi_controlled_source(
            "MCZ(qs[0], qs[1], qs[2], qs[3])",
            qubits="[q0, q1, q2, q3]",
        )
        out = compile_to_qiskit(_machine(source), QSimulationOptions(analytic=True, skip_qutip=True))
        idx_pre = out.index("qc.h(3)")
        idx_mcx = out.index("qc.mcx([0, 1, 2], 3)")
        idx_post = out.index("qc.h(3)", idx_pre + 1)
        assert idx_pre < idx_mcx < idx_post

    # --- Shots branch transpiles against a fixed basis ---

    def test_qiskit_shots_branch_transpiles_for_mcx(self):
        source = _multi_controlled_source(
            "MCX(qs[0], qs[1], qs[2], qs[3])",
            qubits="[q0, q1, q2, q3]",
        )
        out = compile_to_qiskit(_machine(source), QSimulationOptions(analytic=False, shots=1024, skip_qutip=True))
        # BasicSimulator does not run `mcx` natively, so the shots script must
        # transpile to a fixed basis before simulating.
        assert "transpile" in out
        assert "basis_gates=_basis" in out


class TestCSWAPGateEmission:
    """CSWAP (Fredkin) is the odd 3-qubit gate: 1 control + 2 swap targets.
    It was in `KNOWN_UNITARY_GATES` and the README gate table but had no
    compiler test — a documentation-without-test asymmetry flagged by PR #14
    QA. These tests close the loop.
    """

    def test_qasm_cswap_emits_cswap_with_ctrl_and_two_targets(self):
        source = _multi_controlled_source("CSWAP(qs[0], qs[1], qs[2])")
        out = compile_to_qasm(_machine(source))
        assert "cswap q[0], q[1], q[2];" in out

    def test_qiskit_cswap_emits_cswap_with_ctrl_and_two_targets(self):
        source = _multi_controlled_source("CSWAP(qs[0], qs[1], qs[2])")
        out = compile_to_qiskit(_machine(source), QSimulationOptions(analytic=True, skip_qutip=True))
        assert "qc.cswap(0, 1, 2)" in out


def _polysemy_source(action_cells: list[str], n_qubits: int = 3) -> str:
    """Build a linear-chain machine with one parametric action `query_concept`
    and one parametric action `rotate` invoked at each transition.

    ``action_cells`` is a list of Action-cell strings placed on successive
    transitions, allowing each test to vary the argument expressions.
    """
    qubits = ", ".join(f"q{i}" for i in range(n_qubits))
    events = "\n".join(f"- e{i}" for i in range(len(action_cells)))
    states = ["## state |s0> [initial]"] + [
        f"## state |s{i}>" for i in range(1, len(action_cells))
    ] + [f"## state |s{len(action_cells)}> [final]"]
    transitions = "\n".join(
        f"| |s{i}> | e{i} |  | |s{i + 1}> | {cell} |"
        for i, cell in enumerate(action_cells)
    )
    return f"""# machine Polysemy

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [{qubits}]   |

## events
{events}

{chr(10).join(states)}

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
{transitions}

## actions
| Name          | Signature                | Effect           |
|---------------|--------------------------|------------------|
| query_concept | (qs, c: int) -> qs       | Hadamard(qs[c])  |
| rotate        | (qs, theta: angle) -> qs | Rx(qs[0], theta) |
"""


class TestParametricActionExpansion:
    """Per-call-site expansion (Section 5). A parametric action SHALL emit
    one independent gate sequence per invoking transition, with bound
    argument values substituted into the template at compile time."""

    def test_qasm_twelve_call_sites_emit_independent_gate_sequences(self):
        # Expand to 3 qubits × 4 concepts each, 12 total call sites. Both
        # arities (12) and range (0..11 mod 3) match the polysemantic-12
        # demo's shape.
        action_cells = [f"query_concept({i % 3})" for i in range(12)]
        source = _polysemy_source(action_cells, n_qubits=3)
        out = compile_to_qasm(_machine(source))
        # Each of qubits 0, 1, 2 gets 4 Hadamards → 4 `h q[0]`, etc.
        assert out.count("h q[0];") == 4
        assert out.count("h q[1];") == 4
        assert out.count("h q[2];") == 4

    def test_qiskit_angle_parameter_substituted_into_rotation(self):
        source = _polysemy_source(["rotate(pi/4)"], n_qubits=1)
        out = compile_to_qiskit(_machine(source), QSimulationOptions(analytic=True, skip_qutip=True))
        # pi/4 ≈ 0.7853981633974483 — the exact repr expand_action_call emits
        assert "qc.rx(0.7853981633974483, 0)" in out

    def test_mermaid_label_uses_source_form_call_text(self):
        source = _polysemy_source(["query_concept(2)"], n_qubits=3)
        out = compile_to_mermaid(_machine(source))
        # The bare action name MUST NOT leak through when the transition
        # carries a call form — the source text is what the user wrote.
        assert "/ query_concept(2)" in out

    def test_mermaid_label_falls_back_to_bare_action_name(self):
        # Non-parametric actions keep their bare-name display.
        source = """# machine Bare
## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]    |

## events
- go

## state |s0> [initial]
## state |s1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | go    |       | |s1>   | apply_h |

## actions
| Name    | Signature  | Effect          |
|---------|------------|-----------------|
| apply_h | (qs) -> qs | Hadamard(qs[0]) |
"""
        out = compile_to_mermaid(_machine(source))
        assert "/ apply_h" in out

    def test_qasm_mixed_parametric_and_bare_actions_coexist(self):
        source = """# machine Mixed
## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2] |

## events
- e0
- e1

## state |s0> [initial]
## state |s1>
## state |s2> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | e0    |       | |s1>   | apply_h |
| |s1>   | e1    |       | |s2>   | query_concept(2) |

## actions
| Name          | Signature          | Effect          |
|---------------|--------------------|-----------------|
| apply_h       | (qs) -> qs         | Hadamard(qs[0]) |
| query_concept | (qs, c: int) -> qs | Hadamard(qs[c]) |
"""
        out = compile_to_qasm(_machine(source))
        # Bare action emits its fixed gate once; parametric action emits
        # its expanded gate once — no cross-contamination.
        assert "h q[0];" in out
        assert "h q[2];" in out


class TestComputeConceptGram:
    """Covers the `compute_concept_gram` analysis helper (Section 2 of
    add-polysemantic-clusters)."""

    def _make_machine(
        self,
        sig: str,
        effect: str,
        calls: list[str],
        action_name: str = "query_concept",
    ):
        """Build a minimal machine with N call sites to a parametric action.

        ``calls`` is a list of argument-literal strings (e.g. "0.1, 0.2, 0.3").
        """
        transitions = []
        states = ["## state idle [initial]"]
        for i, args in enumerate(calls):
            state_name = f"q{i}"
            states.append(f"## state {state_name}")
            transitions.append(
                f"| idle | ev{i} | | {state_name} | {action_name}({args}) |"
            )
        states.append("## state done [final]")
        events = "\n".join(f"- ev{i}" for i in range(len(calls))) or "- noop"
        trans_body = "\n".join(transitions) or (
            "| idle | noop | | done |  |"
        )
        source = (
            "# machine M\n\n"
            "## context\n"
            "| Field  | Type        | Default      |\n"
            "|--------|-------------|--------------|\n"
            "| qubits | list<qubit> | [q0, q1, q2] |\n\n"
            "## events\n"
            f"{events}\n\n"
            + "\n\n".join(states) + "\n\n"
            "## transitions\n"
            "| Source | Event | Guard | Target | Action |\n"
            "|--------|-------|-------|--------|--------|\n"
            f"{trans_body}\n\n"
            "## actions\n"
            "| Name | Signature | Effect |\n"
            "|------|-----------|--------|\n"
            f"| {action_name} | {sig} | {effect} |\n"
        )
        result = parse_q_orca_markdown(source)
        assert result.errors == [], result.errors
        return result.file.machines[0]

    def test_happy_path_on_clusters_example(self):
        """Gram matrix of the canonical example matches the documented
        block structure."""
        import numpy as np
        from pathlib import Path

        from q_orca import compute_concept_gram

        examples_dir = Path(__file__).parent.parent / "examples"
        source = (examples_dir / "larql-polysemantic-clusters.q.orca.md").read_text()
        parsed = parse_q_orca_markdown(source)
        machine = parsed.file.machines[0]

        gram = compute_concept_gram(machine)
        assert gram.shape == (12, 12)
        assert gram.dtype == np.complex128

        np.testing.assert_allclose(np.diag(np.abs(gram)), np.ones(12), atol=1e-9)

        gsq = np.abs(gram) ** 2
        # Intra-cluster uniformity at 0.72 (cos(0)² · cos(0.4)² · cos(0.4)² ≈ 0.7197)
        for ci in range(3):
            block = gsq[ci * 4:(ci + 1) * 4, ci * 4:(ci + 1) * 4]
            off_diag = block[~np.eye(4, dtype=bool)]
            np.testing.assert_allclose(off_diag, 0.7197, atol=1e-3)
        # All inter-cluster < 0.10
        for i in range(3):
            for j in range(i + 1, 3):
                block = gsq[i * 4:(i + 1) * 4, j * 4:(j + 1) * 4]
                assert block.max() < 0.10

    def test_wrong_signature_int_parameter_raises(self):
        """An action with an int parameter (not three angles) raises."""
        from q_orca import ConceptGramConfigurationError, compute_concept_gram

        machine = self._make_machine(
            "(qs, c: int) -> qs",
            "Hadamard(qs[c])",
            ["0"],
            action_name="query_concept",
        )
        try:
            compute_concept_gram(machine)
        except ConceptGramConfigurationError as e:
            assert "query_concept" in str(e)
            assert "three angle" in str(e)
        else:
            raise AssertionError("expected ConceptGramConfigurationError")

    def test_missing_action_raises(self):
        """Passing a label that doesn't name a parametric action raises."""
        from q_orca import ConceptGramConfigurationError, compute_concept_gram

        machine = self._make_machine(
            "(qs, a: angle, b: angle, c: angle) -> qs",
            "Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)",
            ["0.1, 0.2, 0.3"],
            action_name="query_concept",
        )
        try:
            compute_concept_gram(machine, concept_action_label="does_not_exist")
        except ConceptGramConfigurationError as e:
            assert "does_not_exist" in str(e)
            assert "query_concept" in str(e)  # listed as hint
        else:
            raise AssertionError("expected ConceptGramConfigurationError")

    def test_no_call_sites_raises(self):
        """Action exists with correct shape but has zero call sites."""
        from q_orca import ConceptGramConfigurationError, compute_concept_gram

        machine = self._make_machine(
            "(qs, a: angle, b: angle, c: angle) -> qs",
            "Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)",
            [],
            action_name="query_concept",
        )
        try:
            compute_concept_gram(machine)
        except ConceptGramConfigurationError as e:
            assert "query_concept" in str(e)
            assert "no call sites" in str(e)
        else:
            raise AssertionError("expected ConceptGramConfigurationError")

    def test_analytic_identity_matrix_on_zero_angles(self):
        """Multiple call sites all at angles (0, 0, 0) must produce all-ones gram."""
        import numpy as np

        from q_orca import compute_concept_gram

        machine = self._make_machine(
            "(qs, a: angle, b: angle, c: angle) -> qs",
            "Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)",
            ["0, 0, 0", "0, 0, 0", "0, 0, 0"],
            action_name="query_concept",
        )
        gram = compute_concept_gram(machine)
        assert gram.shape == (3, 3)
        np.testing.assert_allclose(np.abs(gram), np.ones((3, 3)), atol=1e-9)


class TestSharedFixtureCompilerAdapter:
    """The Qiskit compiler's effect-string adapter must agree with the
    shared parser fixture on AST gate shape for every supported gate kind.
    """

    @pytest.mark.parametrize(
        "effect_str,angle_context,expected,notes",
        EFFECT_STRING_CASES,
        ids=[c[3] for c in EFFECT_STRING_CASES],
    )
    def test_quantum_gate_shape(self, effect_str, angle_context, expected, notes):
        from q_orca.compiler.qiskit import _parse_single_gate

        gate = _parse_single_gate(effect_str, angle_context=angle_context)
        assert gate is not None, f"{effect_str!r} returned None ({notes})"
        assert gate.kind == expected.name
        assert gate.targets == list(expected.targets)
        if expected.controls:
            assert gate.controls == list(expected.controls)
        else:
            assert not gate.controls
        if expected.parameter is None:
            assert gate.parameter is None
        else:
            assert gate.parameter == pytest.approx(expected.parameter)
        if expected.custom_name is not None:
            assert gate.custom_name == expected.custom_name
