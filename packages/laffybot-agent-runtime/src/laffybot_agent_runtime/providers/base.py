from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from laffybot_agent_runtime.providers.config import ProviderConfig
from laffybot_agent_runtime.providers.types import (
    ErrorLLMResponse,
    StreamChunk,
    SuccessLLMResponse,
)


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
    ) -> SuccessLLMResponse | ErrorLLMResponse: ...

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        on_chunk: Callable[[StreamChunk], Awaitable[None]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> SuccessLLMResponse | ErrorLLMResponse: ...
