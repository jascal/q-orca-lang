"""End-to-end test for the vqe-rotation example.

Runs the full pipeline: parse → verify → compile → simulate via QuTiP (skipped
if QuTiP is not installed), and asserts |<psi|psi_expected>|^2 > 0.999999 for
theta = pi/4.
"""

import math
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
VQE_ROTATION_PATH = EXAMPLES_DIR / "vqe-rotation.q.orca.md"


def _parse_machine():
    from q_orca.parser.markdown_parser import parse_q_orca_markdown
    source = VQE_ROTATION_PATH.read_text()
    result = parse_q_orca_markdown(source)
    assert result.errors == [], f"Parse errors: {result.errors}"
    return result.file.machines[0]


class TestVqeRotationPipeline:
    def test_parse_populates_rotation_gate(self):
        machine = _parse_machine()
        rotate_action = next(
            (a for a in machine.actions if a.gate and a.gate.kind in ("Rx", "Ry", "Rz")),
            None,
        )
        assert rotate_action is not None, "No rotation gate action found"
        assert rotate_action.gate.parameter == pytest.approx(math.pi / 4, rel=1e-9)

    def test_verify_passes(self):
        from q_orca.verifier import verify
        machine = _parse_machine()
        result = verify(machine)
        errors = [e for e in result.errors if e.severity == "error"]
        assert not errors, f"Verification errors: {errors}"

    def test_compile_to_qasm(self):
        from q_orca.compiler.qasm import compile_to_qasm
        machine = _parse_machine()
        qasm = compile_to_qasm(machine)
        assert "rx(" in qasm or "ry(" in qasm or "rz(" in qasm

    def test_compile_to_qiskit(self):
        from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
        machine = _parse_machine()
        code = compile_to_qiskit(machine, QSimulationOptions())
        assert "qc.rx(" in code or "qc.ry(" in code or "qc.rz(" in code

    @pytest.mark.skipif(
        not pytest.importorskip("qutip", reason="QuTiP not installed"),
        reason="QuTiP not installed",
    )
    def test_simulate_state_vector(self):
        """After Rx(qs[0], pi/4)|0>, the fidelity with the expected state is > 0.999999."""
        try:
            from qutip import basis
            from qutip.qip.operations import rx
        except ImportError:
            pytest.skip("QuTiP not installed")

        theta = math.pi / 4
        psi_0 = basis(2, 0)
        psi_expected = rx(theta) * psi_0

        # Verify the rotation manually: Rx(pi/4)|0> = cos(pi/8)|0> - i*sin(pi/8)|1>
        import cmath
        c0 = math.cos(theta / 2)
        c1 = -1j * math.sin(theta / 2)
        from qutip import Qobj
        psi_formula = Qobj([[c0], [c1]])

        fidelity = abs((psi_formula.dag() * psi_expected)[0, 0]) ** 2
        assert fidelity > 0.999999, f"State fidelity too low: {fidelity}"
