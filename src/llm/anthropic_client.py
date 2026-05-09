from __future__ import annotations

import json
import os
from typing import Optional

from anthropic import AsyncAnthropic

from .base import BaseLLMClient, LLMResponse


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API 客户端"""

    def __init__(self, config: dict):
        super().__init__(config)
        api_key = os.environ.get(config.get("api_key_env", "ANTHROPIC_API_KEY"), "")
        self.client = AsyncAnthropic(api_key=api_key, timeout=self.timeout)
        self.model = config.get("model", "claude-sonnet-4-20250514")

    async def call(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self.client.messages.create(**kwargs)
        content = response.content[0].text if response.content else ""

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            raw=response,
        )

    async def call_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ) -> dict:
        full_prompt = prompt + "\n\nRespond with valid JSON only. No extra text."
        resp = await self.call(
            full_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    async def close(self) -> None:
        await self.client.close()
