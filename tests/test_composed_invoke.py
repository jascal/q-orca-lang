"""End-to-end test for a composed (multi-machine) invoke file.

Covers add-parameterized-invoke §6.1: a classical-orchestrator parent invoking a
quantum-forward-pass child must parse, verify, and render to Mermaid cleanly,
while QASM/Qiskit refuse with the structured composed-machine error.
"""

from pathlib import Path

import pytest

from q_orca.compiler.mermaid import compile_to_mermaid
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import QSimulationOptions, compile_to_qiskit
from q_orca.compiler.util import ComposedMachineError
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import VerifyOptions, verify

FIXTURE = Path(__file__).parent / "fixtures" / "composed_predictive_coder.q.orca.md"


@pytest.fixture(scope="module")
def parsed():
    result = parse_q_orca_markdown(FIXTURE.read_text())
    assert not result.errors, result.errors
    return result


def test_parses_two_machines(parsed):
    assert [m.name for m in parsed.file.machines] == ["QPCTrainer", "QForward"]


def test_parent_and_child_verify_clean(parsed):
    parent, child = parsed.file.machines
    parent_result = verify(parent, VerifyOptions(), file=parsed.file)
    assert parent_result.valid, [(e.code, e.message) for e in parent_result.errors]
    child_result = verify(child, VerifyOptions(), file=parsed.file)
    assert child_result.valid, [(e.code, e.message) for e in child_result.errors]


def test_mermaid_renders_composition(parsed):
    parent = parsed.file.machines[0]
    mermaid = compile_to_mermaid(parent, file=parsed.file)
    assert "invoke: QForward" in mermaid
    assert "state QForward {" in mermaid


def test_qasm_refuses(parsed):
    with pytest.raises(ComposedMachineError):
        compile_to_qasm(parsed.file.machines[0])


def test_qiskit_refuses(parsed):
    with pytest.raises(ComposedMachineError):
        compile_to_qiskit(parsed.file.machines[0], QSimulationOptions(analytic=True, skip_qutip=True))
