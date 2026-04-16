"""Q-Orca execution backends — pluggable verification and simulation backends."""

from q_orca.backends.base import BackendAdapter, BackendResult, BackendUnavailableError
from q_orca.backends.registry import BackendRegistry
from q_orca.backends.qutip_backend import qutip_backend
from q_orca.backends.cuquantum_backend import cuquantum_backend
from q_orca.backends.cudaq_backend import cudaq_backend

# Register all adapters; QuTiP is the fallback
BackendRegistry.register(qutip_backend, fallback=True)
BackendRegistry.register(cuquantum_backend)
BackendRegistry.register(cudaq_backend)

__all__ = [
    "BackendAdapter",
    "BackendResult",
    "BackendUnavailableError",
    "BackendRegistry",
]
