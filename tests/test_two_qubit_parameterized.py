"""Tests for two-qubit parameterized gates: CRx, CRy, CRz, RXX, RYY, RZZ.

Covers parser, Qiskit compiler, QASM compiler, and verifier for all six new gate kinds.
"""

import math
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
QAOA_PATH = EXAMPLES_DIR / "qaoa-maxcut.q.orca.md"

TWO_QUBIT_SOURCE = """\
# machine TwoQubitParam

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0, q1] |

## events
- run

## state |00> [initial]
## state |result> [final]

## transitions
| Source | Event | Guard | Target    | Action   |
|--------|-------|-------|-----------|----------|
| |00>   | run   |       | |result>  | apply_all |

## actions
| Name      | Signature    | Effect                                                                                       |
|-----------|--------------|----------------------------------------------------------------------------------------------|
| apply_all | (qs) -> qs   | CRz(qs[0], qs[1], pi/2); CRx(qs[0], qs[1], pi/4); CRy(qs[0], qs[1], pi/4); RZZ(qs[0], qs[1], pi/3); RXX(qs[0], qs[1], pi/6); RYY(qs[0], qs[1], pi/6) |

## verification rules
- unitarity: all gates preserve norm
"""


def _parse(source: str):
    from q_orca.parser.markdown_parser import parse_q_orca_markdown
    result = parse_q_orca_markdown(source)
    assert result.errors == [], f"Parse errors: {result.errors}"
    return result.file.machines[0]


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParserTwoQubitGates:
    def test_crz_parsed(self):
        machine = _parse(TWO_QUBIT_SOURCE)
        action = next(a for a in machine.actions if a.name == "apply_all")
        # Parser stores only the first gate on action.gate; multi-gate effects use effect string
        # Just verify the effect string is stored and no parse errors occurred
        assert action.effect is not None
        assert "CRz" in action.effect

    def test_rzz_in_effect(self):
        machine = _parse(TWO_QUBIT_SOURCE)
        action = next(a for a in machine.actions if a.name == "apply_all")
        assert "RZZ" in action.effect

    def test_no_parse_errors(self):
        from q_orca.parser.markdown_parser import parse_q_orca_markdown
        result = parse_q_orca_markdown(TWO_QUBIT_SOURCE)
        assert result.errors == []


class TestParserCRzSingle:
    """CRz as the only gate so action.gate is populated."""

    SOURCE = """\
# machine CRzOnly

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0, q1] |

## events
- run

## state |00> [initial]
## state |done> [final]

## transitions
| Source | Event | Guard | Target  | Action    |
|--------|-------|-------|---------|-----------|
| |00>   | run   |       | |done>  | apply_crz |

## actions
| Name      | Signature  | Effect                    |
|-----------|------------|---------------------------|
| apply_crz | (qs) -> qs | CRz(qs[0], qs[1], pi/2)   |

## verification rules
- unitarity: all gates preserve norm
"""

    def test_gate_kind(self):
        machine = _parse(self.SOURCE)
        action = next(a for a in machine.actions if a.name == "apply_crz")
        assert action.gate is not None
        assert action.gate.kind == "CRz"

    def test_gate_controls_and_targets(self):
        machine = _parse(self.SOURCE)
        action = next(a for a in machine.actions if a.name == "apply_crz")
        assert action.gate.controls == [0]
        assert action.gate.targets == [1]

    def test_gate_angle(self):
        machine = _parse(self.SOURCE)
        action = next(a for a in machine.actions if a.name == "apply_crz")
        assert action.gate.parameter == pytest.approx(math.pi / 2, rel=1e-9)


class TestParserRZZSingle:
    """RZZ as the only gate."""

    SOURCE = """\
# machine RZZOnly

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0, q1] |

## events
- run

## state |00> [initial]
## state |done> [final]

## transitions
| Source | Event | Guard | Target  | Action    |
|--------|-------|-------|---------|-----------|
| |00>   | run   |       | |done>  | apply_rzz |

## actions
| Name      | Signature  | Effect                    |
|-----------|------------|---------------------------|
| apply_rzz | (qs) -> qs | RZZ(qs[0], qs[1], pi/3)   |

## verification rules
- unitarity: all gates preserve norm
"""

    def test_gate_kind(self):
        machine = _parse(self.SOURCE)
        action = next(a for a in machine.actions if a.name == "apply_rzz")
        assert action.gate is not None
        assert action.gate.kind == "RZZ"

    def test_gate_targets(self):
        machine = _parse(self.SOURCE)
        action = next(a for a in machine.actions if a.name == "apply_rzz")
        assert action.gate.targets == [0, 1]
        assert not action.gate.controls

    def test_gate_angle(self):
        machine = _parse(self.SOURCE)
        action = next(a for a in machine.actions if a.name == "apply_rzz")
        assert action.gate.parameter == pytest.approx(math.pi / 3, rel=1e-9)


# ---------------------------------------------------------------------------
# Verifier tests
# ---------------------------------------------------------------------------

class TestVerifierTwoQubitGates:
    def test_unitarity_passes_for_crz(self):
        from q_orca.verifier import verify
        machine = _parse(TestParserCRzSingle.SOURCE)
        result = verify(machine)
        errors = [e for e in result.errors if e.severity == "error"]
        assert not errors, f"Unexpected errors: {errors}"

    def test_unitarity_passes_for_rzz(self):
        from q_orca.verifier import verify
        machine = _parse(TestParserRZZSingle.SOURCE)
        result = verify(machine)
        errors = [e for e in result.errors if e.severity == "error"]
        assert not errors, f"Unexpected errors: {errors}"

    @pytest.mark.parametrize("kind", ["CRx", "CRy", "CRz", "RXX", "RYY", "RZZ"])
    def test_all_new_kinds_in_known_unitary_gates(self, kind):
        from q_orca.verifier.quantum import KNOWN_UNITARY_GATES
        assert kind in KNOWN_UNITARY_GATES


# ---------------------------------------------------------------------------
# Qiskit compiler tests
# ---------------------------------------------------------------------------

class TestQiskitCompilerTwoQubitGates:
    def test_crz_emitted(self):
        from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
        machine = _parse(TestParserCRzSingle.SOURCE)
        code = compile_to_qiskit(machine, QSimulationOptions())
        assert "qc.crz(" in code

    def test_rzz_emitted(self):
        from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
        machine = _parse(TestParserRZZSingle.SOURCE)
        code = compile_to_qiskit(machine, QSimulationOptions())
        assert "qc.rzz(" in code

    @pytest.mark.parametrize("kind,expected", [
        ("CRx", "qc.crx("),
        ("CRy", "qc.cry("),
        ("CRz", "qc.crz("),
        ("RXX", "qc.rxx("),
        ("RYY", "qc.ryy("),
        ("RZZ", "qc.rzz("),
    ])
    def test_all_kinds_emitted(self, kind, expected):
        from q_orca.compiler.qiskit import _gate_to_qiskit
        from q_orca.ast import QuantumGate
        if kind in ("CRx", "CRy", "CRz"):
            gate = QuantumGate(kind=kind, targets=[1], controls=[0], parameter=math.pi / 4)
        else:
            gate = QuantumGate(kind=kind, targets=[0, 1], parameter=math.pi / 4)
        line = _gate_to_qiskit(gate)
        assert expected in line, f"Expected {expected!r} in {line!r}"


# ---------------------------------------------------------------------------
# QASM compiler tests
# ---------------------------------------------------------------------------

class TestQasmCompilerTwoQubitGates:
    def test_crz_direct_emission(self):
        from q_orca.compiler.qasm import compile_to_qasm
        machine = _parse(TestParserCRzSingle.SOURCE)
        qasm = compile_to_qasm(machine)
        assert "crz(" in qasm

    def test_rzz_decomposition(self):
        from q_orca.compiler.qasm import _gate_to_qasm
        from q_orca.ast import QuantumGate
        gate = QuantumGate(kind="RZZ", targets=[0, 1], parameter=math.pi / 3)
        line = _gate_to_qasm(gate, 2)
        assert "cx" in line
        assert "rz(" in line

    def test_rxx_decomposition(self):
        from q_orca.compiler.qasm import _gate_to_qasm
        from q_orca.ast import QuantumGate
        gate = QuantumGate(kind="RXX", targets=[0, 1], parameter=math.pi / 6)
        line = _gate_to_qasm(gate, 2)
        assert "h " in line
        assert "cx" in line
        assert "rz(" in line

    def test_ryy_decomposition(self):
        from q_orca.compiler.qasm import _gate_to_qasm
        from q_orca.ast import QuantumGate
        gate = QuantumGate(kind="RYY", targets=[0, 1], parameter=math.pi / 6)
        line = _gate_to_qasm(gate, 2)
        assert "rx(" in line
        assert "cx" in line

    @pytest.mark.parametrize("kind,expected_fragment", [
        ("CRx", "crx("),
        ("CRy", "cry("),
        ("CRz", "crz("),
    ])
    def test_controlled_direct_emission(self, kind, expected_fragment):
        from q_orca.compiler.qasm import _gate_to_qasm
        from q_orca.ast import QuantumGate
        gate = QuantumGate(kind=kind, targets=[1], controls=[0], parameter=math.pi / 4)
        line = _gate_to_qasm(gate, 2)
        assert expected_fragment in line


# ---------------------------------------------------------------------------
# QAOA example end-to-end
# ---------------------------------------------------------------------------

class TestQaoaMaxcutExample:
    def test_parse_no_errors(self):
        from q_orca.parser.markdown_parser import parse_q_orca_markdown
        source = QAOA_PATH.read_text()
        result = parse_q_orca_markdown(source)
        assert result.errors == [], f"Parse errors: {result.errors}"

    def test_verify_passes(self):
        from q_orca.parser.markdown_parser import parse_q_orca_markdown
        from q_orca.verifier import verify
        source = QAOA_PATH.read_text()
        machine = parse_q_orca_markdown(source).file.machines[0]
        result = verify(machine)
        errors = [e for e in result.errors if e.severity == "error"]
        assert not errors, f"Verification errors: {errors}"

    def test_compile_to_qiskit_contains_rzz(self):
        from q_orca.parser.markdown_parser import parse_q_orca_markdown
        from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
        source = QAOA_PATH.read_text()
        machine = parse_q_orca_markdown(source).file.machines[0]
        code = compile_to_qiskit(machine, QSimulationOptions())
        assert "qc.rzz(" in code

    def test_compile_to_qasm_contains_rzz_decomp(self):
        from q_orca.parser.markdown_parser import parse_q_orca_markdown
        from q_orca.compiler.qasm import compile_to_qasm
        source = QAOA_PATH.read_text()
        machine = parse_q_orca_markdown(source).file.machines[0]
        qasm = compile_to_qasm(machine)
        assert "cx" in qasm
        assert "rz(" in qasm
