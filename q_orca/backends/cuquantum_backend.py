"""Q-Orca cuQuantum backend adapter — GPU-accelerated verification via qutip-cuquantum."""

from __future__ import annotations

from typing import Any, Optional

from q_orca.ast import QMachineDef
from q_orca.backends.base import BackendAdapter, BackendResult, BackendUnavailableError
from q_orca.verifier.dynamic import dynamic_verify_gpu
from q_orca.verifier.types import QVerificationResult

# Detect availability at module load time
AVAILABLE = False
_VERSION = "unknown"
try:
    import qutip_cuquantum as _cuq  # type: ignore
    AVAILABLE = True
    _VERSION = getattr(_cuq, "__version__", "unknown")
except ImportError:
    pass


class CuQuantumBackend(BackendAdapter):
    """Backend adapter for GPU-accelerated cuQuantum verification.

    When qutip-cuquantum is absent, raises BackendUnavailableError so the
    BackendRegistry can fall back to QuTiP.
    """

    AVAILABLE: bool = AVAILABLE

    def __init__(self, gpu_count: int = 1, tensor_network: bool = False):
        self.gpu_count = gpu_count
        self.tensor_network = tensor_network

    @property
    def name(self) -> str:
        return "cuquantum"

    @property
    def version(self) -> str:
        return _VERSION

    def verify(
        self, machine: QMachineDef, options: Optional[Any] = None
    ) -> tuple[QVerificationResult, BackendResult]:
        if not AVAILABLE:
            raise BackendUnavailableError(
                "qutip-cuquantum is not installed. "
                "Install with: pip install qutip-cuquantum"
            )
        result = dynamic_verify_gpu(machine)
        backend_result = BackendResult(
            name=self.name,
            version=self.version,
            errors=[e.message for e in result.errors],
            metadata={"gpu_count": self.gpu_count, "tensor_network": self.tensor_network},
        )
        return result, backend_result


# Singleton instance with defaults
cuquantum_backend = CuQuantumBackend()
