"""Q-Orca configuration types."""

from dataclasses import dataclass
from typing import Literal


ProviderType = Literal["anthropic", "openai", "ollama", "grok", "minimax"]
CodeGeneratorType = Literal["python", "typescript", "rust", "go"]


@dataclass
class QOrcaConfig:
    provider: ProviderType
    model: str
    api_key: str | None = None
    base_url: str | None = None
    code_generator: CodeGeneratorType = "python"
    max_tokens: int = 4096
    temperature: float = 0.7


DEFAULT_CONFIG = QOrcaConfig(
    provider="anthropic",
    model="claude-sonnet-4-6",
    code_generator="python",
    max_tokens=4096,
    temperature=0.7,
)
