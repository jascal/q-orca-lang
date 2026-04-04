"""Q-Orca LLM providers."""

from q_orca.llm.provider import LLMProvider, LLMRequest, LLMResponse, LLMMessage, LLMProviderConfig
from q_orca.llm.anthropic import AnthropicProvider
from q_orca.llm.openai import OpenAIProvider
from q_orca.llm.ollama import OllamaProvider
from q_orca.llm.grok import GrokProvider
from q_orca.config.types import ProviderType


def create_provider(type: ProviderType, config: LLMProviderConfig) -> LLMProvider:
    """Create an LLM provider by type."""
    match type:
        case "anthropic":
            return AnthropicProvider(config)
        case "openai":
            return OpenAIProvider(config)
        case "ollama":
            return OllamaProvider(config)
        case "grok":
            return GrokProvider(config)
        case _:
            raise ValueError(f"Unknown LLM provider type: {type}")


__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMMessage",
    "LLMProviderConfig",
    "create_provider",
    "AnthropicProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "GrokProvider",
]
