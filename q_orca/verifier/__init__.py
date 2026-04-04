"""Q-Orca verifier — 5-stage verification pipeline."""

from dataclasses import dataclass
from typing import Optional

from q_orca.ast import QMachineDef
from q_orca.verifier.structural import check_structural
from q_orca.verifier.completeness import check_completeness
from q_orca.verifier.determinism import check_determinism
from q_orca.verifier.quantum import verify_quantum
from q_orca.verifier.superposition import check_superposition_leaks
from q_orca.verifier.types import QVerificationResult, QVerificationError


@dataclass
class VerifyOptions:
    skip_completeness: bool = False
    skip_quantum: bool = False
    skip_qutip: bool = False


def verify(machine: QMachineDef, options: Optional[VerifyOptions] = None) -> QVerificationResult:
    """Run the full verification pipeline on a quantum machine definition."""
    opts = options or VerifyOptions()
    all_errors: list[QVerificationError] = []

    # Stage 1: Structural
    structural = check_structural(machine)
    all_errors.extend(structural.errors)

    if not structural.valid:
        return QVerificationResult(valid=False, errors=all_errors)

    # Stage 2: Completeness
    if not opts.skip_completeness:
        completeness = check_completeness(machine)
        all_errors.extend(completeness.errors)

    # Stage 3: Determinism
    determinism = check_determinism(machine)
    all_errors.extend(determinism.errors)

    # Stage 4: Quantum-specific checks
    if not opts.skip_quantum:
        quantum = verify_quantum(machine)
        all_errors.extend(quantum.errors)

    # Stage 5: Superposition leak check
    superposition = check_superposition_leaks(machine)
    all_errors.extend(superposition.errors)

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in all_errors),
        errors=all_errors,
    )


__all__ = ["verify", "VerifyOptions", "QVerificationResult", "QVerificationError"]
