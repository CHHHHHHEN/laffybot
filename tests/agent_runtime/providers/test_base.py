"""Tests for BaseProvider abstract interface."""

from __future__ import annotations

import collections.abc

from laffybot.agent_runtime.providers.base import BaseProvider
from laffybot.agent_runtime.providers.config import ProviderConfig
from laffybot.agent_runtime.providers.types import (
    ErrorLLMResponse,
    StreamChunk,
    SuccessLLMResponse,
)


def test_can_instantiate_with_config() -> None:
    cfg = ProviderConfig(
        provider_id="p1", name="test", api_key="k", base_url="http://t"
    )

    class _Concrete(BaseProvider):
        async def chat_completion(
            self,
            messages: list[dict[str, object]],
            model: str,
            tools: list[dict[str, object]] | None = None,
            temperature: float | None = None,
            max_tokens: int | None = None,
        ) -> SuccessLLMResponse | ErrorLLMResponse:
            return SuccessLLMResponse(content="ok")

        async def chat_completion_stream(
            self,
            messages: list[dict[str, object]],
            model: str,
            on_chunk: collections.abc.Callable[
                [StreamChunk], collections.abc.Awaitable[None]
            ],
            tools: list[dict[str, object]] | None = None,
            temperature: float | None = None,
            max_tokens: int | None = None,
        ) -> SuccessLLMResponse | ErrorLLMResponse:
            return SuccessLLMResponse(content="")

    p = _Concrete(cfg)
    assert p.config is cfg
