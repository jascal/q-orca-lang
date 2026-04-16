"""Q-Orca backend registry — maps backend names to adapters with fallback logic."""

from __future__ import annotations

from typing import Dict

from q_orca.backends.base import BackendAdapter, BackendUnavailableError


class BackendRegistry:
    """Maps backend names to adapter instances and resolves fallback on BackendUnavailableError."""

    _adapters: Dict[str, BackendAdapter] = {}
    _fallback_order: list[str] = []

    @classmethod
    def register(cls, adapter: BackendAdapter, fallback: bool = False) -> None:
        """Register a backend adapter. Pass fallback=True for the default fallback backend."""
        cls._adapters[adapter.name] = adapter
        if fallback and adapter.name not in cls._fallback_order:
            cls._fallback_order.insert(0, adapter.name)

    @classmethod
    def get(cls, name: str) -> BackendAdapter:
        """Return the named adapter, raising BackendUnavailableError if not available."""
        adapter = cls._adapters.get(name)
        if adapter is None:
            raise BackendUnavailableError(f"Unknown backend: '{name}'")
        if not adapter.AVAILABLE:
            raise BackendUnavailableError(
                f"Backend '{name}' is not available (optional dependency not installed)"
            )
        return adapter

    @classmethod
    def get_with_fallback(cls, name: str) -> tuple[BackendAdapter, bool]:
        """Return (adapter, fell_back).

        If the requested backend is unavailable, falls back to the first available
        adapter in _fallback_order. Raises BackendUnavailableError if nothing is available.
        """
        try:
            return cls.get(name), False
        except BackendUnavailableError:
            for fallback_name in cls._fallback_order:
                if fallback_name == name:
                    continue
                try:
                    return cls.get(fallback_name), True
                except BackendUnavailableError:
                    continue
        raise BackendUnavailableError(
            f"Backend '{name}' is unavailable and no fallback backends are installed"
        )

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._adapters.keys())
