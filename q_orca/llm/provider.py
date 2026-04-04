"""Q-Orca LLM provider interface and types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMRequest:
    messages: list[LLMMessage]
    model: str
    max_tokens: int | None = None
    temperature: float | None = None
    stop_sequences: list[str] | None = None


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict[str, int] | None = None


@dataclass
class LLMProviderConfig:
    model: str
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


class LLMProvider(ABC):
    """Abstract LLM provider."""

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the LLM."""
        ...
