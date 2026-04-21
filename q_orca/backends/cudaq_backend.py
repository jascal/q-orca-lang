"""Q-Orca CUDA-Q backend adapter — QPU/GPU execution via cuda-quantum."""

from __future__ import annotations

from typing import Any, Optional

from q_orca.ast import QMachineDef
from q_orca.backends.base import BackendAdapter, BackendResult, BackendUnavailableError
from q_orca.verifier.types import QVerificationResult

# Detect availability at module load time
AVAILABLE = False
_VERSION = "unknown"
try:
    import cudaq as _cudaq  # type: ignore
    AVAILABLE = True
    _VERSION = getattr(_cudaq, "__version__", "unknown")
except ImportError:
    pass


class CudaQBackend(BackendAdapter):
    """Backend adapter for CUDA-Q QPU/GPU execution.

    When cuda-quantum is absent, raises BackendUnavailableError so the
    BackendRegistry can fall back to QuTiP.
    """

    AVAILABLE: bool = AVAILABLE

    def __init__(self, target: Optional[str] = None):
        self.target = target

    @property
    def name(self) -> str:
        return "cudaq"

    @property
    def version(self) -> str:
        return _VERSION

    def verify(
        self, machine: QMachineDef, options: Optional[Any] = None
    ) -> tuple[QVerificationResult, BackendResult]:
        if not AVAILABLE:
            raise BackendUnavailableError(
                "cudaq is not installed or failed to import (matplotlib is required). "
                "Install with: pip install cudaq matplotlib"
            )
        # CUDA-Q execution path reserved for future — fall back to QuTiP-based
        # dynamic verification and surface that substitution as a warning.
        from q_orca.verifier.dynamic import dynamic_verify
        from q_orca.verifier.types import QVerificationError

        inner = dynamic_verify(machine)
        fallback_warning = QVerificationError(
            code="CUDAQ_VERIFY_FALLBACK",
            message=(
                "CudaQBackend.verify() is a stub: verification was executed "
                "on the CPU via QuTiP, not on a CUDA-Q target. Results are "
                "correct but do not exercise the cudaq runtime."
            ),
            severity="warning",
            suggestion="Set --backend qutip explicitly to remove this warning.",
        )
        # Prepend the fallback warning and re-derive `valid` from the merged
        # error list so the severity/valid invariant (valid iff no error-level
        # entries) is preserved even if the inserted code is ever changed to
        # severity="error".
        merged_errors = [fallback_warning] + list(inner.errors)
        result = QVerificationResult(
            valid=not any(e.severity == "error" for e in merged_errors),
            errors=merged_errors,
        )
        backend_result = BackendResult(
            name=self.name,
            version=self.version,
            errors=[e.message for e in result.errors],
            metadata={"target": self.target, "fallback": "qutip"},
        )
        return result, backend_result


# Singleton instance
cudaq_backend = CudaQBackend()
