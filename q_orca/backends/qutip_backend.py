"""Q-Orca QuTiP backend adapter — wraps the existing dynamic_verify() logic."""

from __future__ import annotations

from typing import Any, Optional

from q_orca.ast import QMachineDef
from q_orca.backends.base import BackendAdapter, BackendResult, BackendUnavailableError
from q_orca.verifier.types import QVerificationResult

# Detect availability at module load time
AVAILABLE = False
_VERSION = "unknown"
try:
    import qutip as _qutip
    AVAILABLE = True
    _VERSION = getattr(_qutip, "__version__", "unknown")
except ImportError:
    pass


class QuTiPBackend(BackendAdapter):
    """Backend adapter that delegates to q_orca.verifier.dynamic.dynamic_verify()."""

    AVAILABLE: bool = AVAILABLE

    @property
    def name(self) -> str:
        return "qutip"

    @property
    def version(self) -> str:
        return _VERSION

    def verify(
        self, machine: QMachineDef, options: Optional[Any] = None
    ) -> tuple[QVerificationResult, BackendResult]:
        if not AVAILABLE:
            raise BackendUnavailableError("QuTiP is not installed")
        from q_orca.verifier.dynamic import dynamic_verify
        result = dynamic_verify(machine)
        backend_result = BackendResult(
            name=self.name,
            version=self.version,
            errors=[e.message for e in result.errors],
        )
        return result, backend_result


# Singleton instance
qutip_backend = QuTiPBackend()
