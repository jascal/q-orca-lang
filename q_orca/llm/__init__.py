"""Q-Orca LLM providers."""

from q_orca.llm.provider import LLMProvider, LLMRequest, LLMResponse, LLMMessage, LLMProviderConfig
from q_orca.llm.anthropic import AnthropicProvider
from q_orca.llm.openai import OpenAIProvider
from q_orca.llm.ollama import OllamaProvider
from q_orca.llm.grok import GrokProvider
from q_orca.config.types import ProviderType


MINIMAX_BASE_URL = "https://api.minimaxi.chat/v1"
MINIMAX_DEFAULT_MODEL = "MiniMax-M2.7"


def create_provider(type: ProviderType, config: LLMProviderConfig) -> LLMProvider:
    """Create an LLM provider by type."""
    match type:
        case "anthropic":
            return AnthropicProvider(config)
        case "minimax":
            minimax_config = LLMProviderConfig(
                model=config.model or MINIMAX_DEFAULT_MODEL,
                api_key=config.api_key,
                base_url=config.base_url or MINIMAX_BASE_URL,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            return OpenAIProvider(minimax_config)
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
