"""Provider factory for decoupling provider creation."""

from __future__ import annotations

from typing import Protocol

from laffybot_agent_runtime.providers.base import BaseProvider
from laffybot_agent_runtime.providers.config import ProviderConfig


class ProviderFactory(Protocol):
    """Interface for creating BaseProvider instances.

    SessionManager and route handlers depend on this protocol instead of
    directly importing concrete provider classes like ``OpenAIProvider``.
    """

    async def create_provider(self, config: ProviderConfig) -> BaseProvider: ...
