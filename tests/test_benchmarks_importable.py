"""Smoke tests for the benchmarks scaffold.

Catches missing __init__.py files, import errors, and broken refactors before
CI hits the real benchmark workflows.
"""

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "benchmarks",
        "benchmarks.gpu_vs_cpu",
        "benchmarks.llm_evolution",
        "benchmarks.qaoa",
        "benchmarks.qaoa.scaling_sweep",
        "benchmarks.vqe",
        "benchmarks.vqe.scaling_sweep",
    ],
)
def test_benchmark_module_importable(module: str) -> None:
    importlib.import_module(module)


def test_qaoa_circuit_builder_runs() -> None:
    """The pure-builder path must work without qiskit_aer or any sim backend."""
    pytest.importorskip("qiskit")
    from qiskit import qasm2

    from benchmarks.qaoa.scaling_sweep import build_qaoa_maxcut_circuit

    qc = build_qaoa_maxcut_circuit(6, depth=1)
    assert qc.num_qubits == 6
    assert qasm2.dumps(qc).startswith("OPENQASM 2.0;")


def test_vqe_ansatz_builder_runs() -> None:
    pytest.importorskip("qiskit")
    from benchmarks.vqe.scaling_sweep import build_vqe_ansatz

    qc, params = build_vqe_ansatz(4, depth=1)
    assert qc.num_qubits == 4
    assert len(params) == 4 * (1 + 1)


def test_extract_json_object_handles_fences_and_preamble() -> None:
    from benchmarks.llm_evolution import _extract_json_object

    # Pure JSON
    assert _extract_json_object('{"gamma": 0.5, "beta": 0.25}') == {
        "gamma": 0.5,
        "beta": 0.25,
    }
    # Markdown-fenced JSON with preamble
    raw = 'Sure!\n```json\n{"gamma": 0.7, "beta": 0.3, "rationale": "ok"}\n```\nthx'
    assert _extract_json_object(raw) == {
        "gamma": 0.7,
        "beta": 0.3,
        "rationale": "ok",
    }
    # No JSON at all
    assert _extract_json_object("no json here") is None
    # Malformed JSON inside fences
    assert _extract_json_object('```json\n{not valid}\n```') is None
