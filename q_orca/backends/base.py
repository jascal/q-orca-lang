"""Q-Orca backend adapter base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from q_orca.ast import QMachineDef
from q_orca.verifier.types import QVerificationResult


class BackendUnavailableError(Exception):
    """Raised when a backend's optional dependency is not installed."""


@dataclass
class BackendResult:
    """Metadata returned by a backend after verification."""
    name: str
    version: str = "unknown"
    errors: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BackendAdapter(ABC):
    """Abstract base class for all Q-Orca execution backends."""

    #: Set to True at module load if the backend's dependencies are available.
    AVAILABLE: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier (e.g. 'qutip', 'cuquantum', 'cudaq')."""

    @property
    def version(self) -> str:
        """Backend library version string."""
        return "unknown"

    @abstractmethod
    def verify(self, machine: QMachineDef, options: Optional[Any] = None) -> tuple[QVerificationResult, BackendResult]:
        """Run verification and return (QVerificationResult, BackendResult)."""
