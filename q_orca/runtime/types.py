"""Q-Orca runtime types."""

from dataclasses import dataclass, field
from typing import Optional

from q_orca.compiler.qiskit import QSimulationOptions


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


@dataclass
class QIterationTrace:
    """One step of the iterative runtime walker."""
    iteration: int
    source_state: str
    target_state: str
    event: str
    action: Optional[str] = None
    measurement_bits: dict = field(default_factory=dict)
    context_snapshot: dict = field(default_factory=dict)


@dataclass
class QIterativeSimulationOptions(QSimulationOptions):
    """Options for the iterative runtime. Extends QSimulationOptions with
    inner-shot accounting, a hard iteration ceiling, and trace control.
    """
    inner_shots: int = 1
    iteration_ceiling: int = 10_000
    record_trace: bool = True


@dataclass
class QIterativeSimulationResult:
    """Result of running the iterative runtime against a machine."""
    machine: str
    success: bool
    final_state: str = ""
    final_context: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)
    aggregate_counts: dict = field(default_factory=dict)
    error: Optional[str] = None


class QIterativeRuntimeError(RuntimeError):
    """Raised by the iterative runtime on stuck states, type mismatches,
    unsupported guard kinds, or iteration-ceiling exhaustion."""
