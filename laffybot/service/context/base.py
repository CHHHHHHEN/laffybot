"""Abstract base classes for context building (service layer)."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from laffybot_agent_runtime.providers.base import BaseProvider

from .types import ContextConfig, RegionInfo


class TokenCounter(ABC):
    @abstractmethod
    def count_tokens(self, text: str) -> int: ...

    @abstractmethod
    def count_message_tokens(self, message: dict[str, Any]) -> int: ...


class ContextBuilder(ABC):
    @abstractmethod
    async def build_messages(
        self,
        session_id: str,
        system_prompt: str | None,
        history: list[dict[str, Any]],
        current_message: str,
        model: str | None = None,
        created_at: datetime | None = None,
        **extra_vars: Any,
    ) -> tuple[list[dict[str, Any]], RegionInfo | None]: ...

    @abstractmethod
    async def compress_messages(
        self,
        messages: list[dict[str, Any]],
        model: str,
        provider: BaseProvider,
    ) -> tuple[list[dict[str, Any]], RegionInfo | None]: ...

    @property
    @abstractmethod
    def config(self) -> ContextConfig: ...
