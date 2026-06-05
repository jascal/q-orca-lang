"""Q-Orca Stim backend adapter — stabilizer (Clifford) fast-path verification.

Implements the `BackendAdapter` contract by delegating Stage 4b to
`dynamic_verify_stabilizer`, which computes the entanglement check from a
stabilizer tableau in polynomial time (Fattal et al.) instead of evolving an
`O(2^n)` state vector. For a Clifford machine the result is identical in shape
to the QuTiP backend; non-Clifford machines are filtered out upstream by the
`is_clifford` classifier before this backend is selected.
"""

from __future__ import annotations

from typing import Any, Optional

from q_orca.ast import QMachineDef
from q_orca.backends.base import BackendAdapter, BackendResult, BackendUnavailableError
from q_orca.verifier.types import QVerificationResult

# Detect availability at module load time, mirroring the other adapters.
AVAILABLE = False
_VERSION = "unknown"
try:
    import stim as _stim
    AVAILABLE = True
    _VERSION = getattr(_stim, "__version__", "unknown")
except ImportError:
    pass


class StimBackend(BackendAdapter):
    """Stabilizer-tableau backend for Clifford circuits, wrapping Stim."""

    AVAILABLE: bool = AVAILABLE

    @property
    def name(self) -> str:
        return "stim"

    @property
    def version(self) -> str:
        return _VERSION

    def verify(
        self, machine: QMachineDef, options: Optional[Any] = None
    ) -> tuple[QVerificationResult, BackendResult]:
        if not AVAILABLE:
            raise BackendUnavailableError(
                "stim is not installed. Install with: pip install 'q-orca[stabilizer]'"
            )
        from q_orca.verifier.dynamic import dynamic_verify_stabilizer
        result = dynamic_verify_stabilizer(machine)
        backend_result = BackendResult(
            name=self.name,
            version=self.version,
            errors=[e.message for e in result.errors],
            metadata={"engine": "stabilizer-tableau"},
        )
        return result, backend_result


# Singleton instance
stim_backend = StimBackend()
