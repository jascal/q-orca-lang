"""Q-Orca runtime types."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PythonCheckResult:
    python3: bool = False
    qiskit: bool = False
    qutip: bool = False
    version: Optional[str] = None


@dataclass
class QuTiPVerificationResult:
    unitarity_verified: bool = False
    entanglement_verified: bool = False
    schmidt_rank: Optional[int] = None
    schmidt_numbers: Optional[list] = None
    unitarity_matrix: Optional[list] = None
    purity: Optional[float] = None
    errors: list = None


@dataclass
class QSimulationResult:
    machine: str
    success: bool
    superposition_leaked: bool = False
    leak_details: list = None
    counts: Optional[dict] = None
    probabilities: Optional[dict] = None
    qutip_verification: Optional[QuTiPVerificationResult] = None
    error: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
