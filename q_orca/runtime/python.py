"""Q-Orca Python runtime — runs Qiskit simulations directly (no subprocess)."""

import json
import subprocess
import sys
import os
import tempfile
from typing import Optional

from q_orca.runtime.types import PythonCheckResult, QSimulationResult, QuTiPVerificationResult
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from q_orca.ast import QMachineDef


def check_python_dependencies() -> PythonCheckResult:
    """Check if Python 3 and required packages are available."""
    result = PythonCheckResult()
    python = sys.executable  # use the current Python interpreter

    try:
        proc = subprocess.run(
            [python, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        result.python3 = proc.returncode == 0
        if result.python3 and proc.stdout:
            result.version = proc.stdout.strip()
    except Exception:
        return result

    try:
        proc = subprocess.run(
            [python, "-c", "import qiskit; print(qiskit.__version__)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        result.qiskit = proc.returncode == 0
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [python, "-c", "import qutip; print(qutip.__version__)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        result.qutip = proc.returncode == 0
    except Exception:
        pass

    return result


def run_simulation(script: str, verbose: bool = False) -> QSimulationResult:
    """Execute a Qiskit Python script and return the parsed result."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
    ) as f:
        f.write(script)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        stdout = proc.stdout
        stderr = proc.stderr

        if proc.returncode == 0 and stdout.strip():
            try:
                data = json.loads(stdout.strip())
                return QSimulationResult(
                    machine=data.get("machine", "unknown"),
                    success=data.get("success", False),
                    superposition_leaked=data.get("superpositionLeaked", False),
                    leak_details=data.get("leakDetails", []),
                    counts=data.get("counts"),
                    probabilities=data.get("probabilities"),
                    qutip_verification=_parse_qutip(data.get("qutipVerification")),
                    stdout=stdout if verbose else None,
                    stderr=stderr if verbose else None,
                )
            except json.JSONDecodeError:
                return QSimulationResult(
                    machine="unknown",
                    success=False,
                    error=f"Failed to parse JSON output: {stdout[:200]}",
                    stdout=stdout if verbose else None,
                    stderr=stderr if verbose else None,
                )
        else:
            return QSimulationResult(
                machine="unknown",
                success=False,
                error=stderr or f"Process exited with code {proc.returncode}",
                stdout=stdout if verbose else None,
                stderr=stderr if verbose else None,
            )
    except subprocess.TimeoutExpired:
        return QSimulationResult(
            machine="unknown",
            success=False,
            error="Timeout after 60s",
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def simulate_machine(
    machine: QMachineDef,
    options: QSimulationOptions,
) -> QSimulationResult:
    """Compile and run a simulation of a quantum machine."""
    deps = check_python_dependencies()

    if not deps.python3:
        return QSimulationResult(
            machine=machine.name,
            success=False,
            error="python3 not found. Install Python 3.8+ to run simulations.",
        )

    if not deps.qiskit:
        return QSimulationResult(
            machine=machine.name,
            success=False,
            error="qiskit not installed. Run: pip install qiskit",
        )

    script = compile_to_qiskit(machine, options)
    result = run_simulation(script, verbose=options.verbose)
    return result


def _parse_qutip(data) -> Optional[QuTiPVerificationResult]:
    if not data:
        return None
    if isinstance(data, dict):
        return QuTiPVerificationResult(
            unitarity_verified=data.get("unitarityVerified", False),
            entanglement_verified=data.get("entanglementVerified", False),
            schmidt_rank=data.get("schmidtRank"),
            schmidt_numbers=data.get("schmidtNumbers"),
            unitarity_matrix=data.get("unitarityMatrix"),
            purity=data.get("purity"),
            errors=data.get("errors", []),
        )
    return None
