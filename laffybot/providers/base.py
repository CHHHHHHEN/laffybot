from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from laffybot.config import ProviderConfig
from laffybot.providers.types import LLMResponse


class BaseProvider(ABC):
    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        on_chunk: Callable[[str], Awaitable[None]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        ...
