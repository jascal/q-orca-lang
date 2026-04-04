"""Anthropic LLM provider for Q-Orca."""

import os
from q_orca.llm.provider import LLMProvider, LLMRequest, LLMResponse, LLMProviderConfig


class AnthropicProvider(LLMProvider):
    def __init__(self, config: LLMProviderConfig):
        self.base_url = config.base_url or "https://api.anthropic.com"
        self.model = config.model or "claude-sonnet-4-6"
        self.max_tokens = config.max_tokens or 4096
        self.temperature = config.temperature if config.temperature is not None else 0.7

        # MiniMax uses Bearer token auth, standard Anthropic uses x-api-key
        if "minimax.io" in (self.base_url or ""):
            self.api_key = config.api_key or os.environ.get("ORCA_API_KEY") or os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
            self.auth_type = "bearer"
        else:
            self.api_key = config.api_key or os.environ.get("ORCA_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
            self.auth_type = "x-api-key"

        if not self.api_key:
            raise ValueError("API key is required — set ORCA_API_KEY (or ANTHROPIC_API_KEY) in your environment")

    def name(self) -> str:
        return "anthropic"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        import json

        # Separate system message from user/assistant messages
        system_message = next((m for m in request.messages if m.role == "system"), None)
        other_messages = [m for m in request.messages if m.role != "system"]

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "anthropic-dangerous-direct-browser-access": "true",
        }

        if self.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers["x-api-key"] = self.api_key

        body = {
            "model": request.model or self.model,
            "system": system_message.content if system_message else None,
            "messages": [
                {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
                for m in other_messages
            ],
            "max_tokens": request.max_tokens or self.max_tokens,
            "temperature": request.temperature if request.temperature is not None else self.temperature,
        }
        if request.stop_sequences:
            body["stop_sequences"] = request.stop_sequences

        import urllib.request

        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"Anthropic API error: {e.code} {error_body}")

        text_content = next(
            (c["text"] for c in data.get("content", []) if c.get("type") == "text"),
            "",
        )

        return LLMResponse(
            content=text_content,
            model=data.get("model", self.model),
            usage={
                "input_tokens": data.get("usage", {}).get("input_tokens", 0),
                "output_tokens": data.get("usage", {}).get("output_tokens", 0),
            },
        )
