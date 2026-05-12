from typing import Any, Awaitable, Callable

from laffybot.providers.base import BaseProvider
from laffybot.providers.types import LLMResponse


class OpenAIProvider(BaseProvider):
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        on_chunk: Callable[[str], Awaitable[None]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        raise NotImplementedError
