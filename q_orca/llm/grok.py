"""Grok LLM provider for Q-Orca."""

import os
import json
import urllib.request
import urllib.error

from q_orca.llm.provider import LLMProvider, LLMRequest, LLMResponse, LLMProviderConfig


class GrokProvider(LLMProvider):
    def __init__(self, config: LLMProviderConfig):
        self.base_url = config.base_url or "https://api.grok.com"
        self.model = config.model or "grok-2"
        self.max_tokens = config.max_tokens or 4096
        self.temperature = config.temperature if config.temperature is not None else 0.7
        self.api_key = config.api_key or os.environ.get("ORCA_API_KEY") or os.environ.get("GROK_API_KEY", "")

        if not self.api_key:
            raise ValueError("API key is required — set ORCA_API_KEY (or GROK_API_KEY) in your environment")

    def name(self) -> str:
        return "grok"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Separate system message from user/assistant messages
        system_message = next((m for m in request.messages if m.role == "system"), None)
        other_messages = [m for m in request.messages if m.role != "system"]

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message.content})
        for m in other_messages:
            if m.role == "assistant":
                messages.append({"role": "assistant", "content": m.content})
            else:
                messages.append({"role": "user", "content": m.content})

        body = {
            "model": request.model or self.model,
            "messages": messages,
            "max_tokens": request.max_tokens or self.max_tokens,
            "temperature": request.temperature if request.temperature is not None else self.temperature,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"Grok API error: {e.code} {error_body}")

        choice = data["choices"][0]
        content = choice.get("message", {}).get("content", "")

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            usage={
                "input_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
            },
        )
