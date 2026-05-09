from __future__ import annotations

import abc
from typing import Any, Optional

from pydantic import BaseModel


class LLMResponse(BaseModel):
    """LLM 调用的标准化返回"""

    content: str
    model: str = ""
    usage: dict[str, int] = {}
    raw: Any = None


class BaseLLMClient(abc.ABC):
    """LLM 客户端抽象基类"""

    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "")
        self.timeout = config.get("timeout", 60)

    @abc.abstractmethod
    async def call(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        """调用 LLM 并返回结构化响应"""
        ...

    @abc.abstractmethod
    async def call_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """调用 LLM 并解析 JSON 返回"""
        ...

    async def close(self) -> None:
        """清理资源"""
        pass
