from __future__ import annotations

import json
import os
from typing import Optional
import asyncio

from openai import AsyncOpenAI

from .base import BaseLLMClient, LLMResponse


class OpenAIClient(BaseLLMClient):
    """OpenAI API 客户端"""

    def __init__(self, config: dict):
        super().__init__(config)
        api_key = os.environ.get(config.get("api_key_env", "OPENAI_API_KEY"), "")
        base_url = config.get("base_url", None)
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=self.timeout)
        self.model = config.get("model", "gpt-4o")

    async def call(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
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
        retries: int = 2,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = await self.call(
                    prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                    response_format={"type": "json_object"},
                )
                parsed = self._extract_json(resp.content)
                if parsed is not None:
                    return parsed
            except Exception as exc:
                last_error = exc
            if attempt < retries:
                await asyncio.sleep(min(2 ** attempt, 8))
        if last_error is not None:
            raise last_error
        return {}

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        import re as _re
        text = (text or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass
        depth = 0
        start = None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        start = None
        return None

    async def close(self) -> None:
        await self.client.close()
