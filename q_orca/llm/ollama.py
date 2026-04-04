"""Ollama LLM provider for Q-Orca (local models)."""

import json
import urllib.request
import urllib.error

from q_orca.llm.provider import LLMProvider, LLMRequest, LLMResponse, LLMProviderConfig


class OllamaProvider(LLMProvider):
    def __init__(self, config: LLMProviderConfig):
        self.base_url = config.base_url or "http://localhost:11434"
        self.model = config.model or "llama3.2"
        self.max_tokens = config.max_tokens or 4096
        self.temperature = config.temperature if config.temperature is not None else 0.7
        # Ollama doesn't require an API key by default

    def name(self) -> str:
        return "ollama"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Build prompt from messages
        system_message = next((m for m in request.messages if m.role == "system"), None)
        other_messages = [m for m in request.messages if m.role != "system"]

        prompt_parts = []
        if system_message:
            prompt_parts.append(f"System: {system_message.content}")
        for m in other_messages:
            role = "Assistant" if m.role == "assistant" else "User"
            prompt_parts.append(f"{role}: {m.content}")
        prompt = "\n\n".join(prompt_parts)

        body = {
            "model": request.model or self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature if request.temperature is not None else self.temperature,
                "num_predict": request.max_tokens or self.max_tokens,
            },
        }

        headers = {"Content-Type": "application/json"}

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"Ollama API error: {e.code} {error_body}")

        return LLMResponse(
            content=data.get("response", ""),
            model=self.model,
            usage=None,
        )
