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
                "cudaq is not installed. "
                "Install with: pip install cudaq"
            )
        # When available, delegate to dynamic_verify (CUDA-Q execution path reserved for future)
        from q_orca.verifier.dynamic import dynamic_verify
        result = dynamic_verify(machine)
        backend_result = BackendResult(
            name=self.name,
            version=self.version,
            errors=[e.message for e in result.errors],
            metadata={"target": self.target},
        )
        return result, backend_result


# Singleton instance
cudaq_backend = CudaQBackend()
