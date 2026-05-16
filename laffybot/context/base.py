"""Abstract base classes for context building."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from .types import ContextConfig, RegionInfo


class TokenCounter(ABC):
    """Abstract base for token counting strategies."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string.

        Args:
            text: The text to count tokens for.

        Returns:
            Estimated or exact token count.
        """
        ...

    @abstractmethod
    def count_message_tokens(self, message: dict[str, Any]) -> int:
        """Count tokens in a message (including role overhead).

        Args:
            message: Message dict with 'role' and 'content' keys.

        Returns:
            Total token count for the message.
        """
        ...


class ContextBuilder(ABC):
    """Abstract base for context building strategies.

    Responsible for assembling the complete message context
    sent to the LLM, including system prompt, history, and
    current message with capacity control.
    """

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
    ) -> tuple[list[dict[str, Any]], RegionInfo | None]:
        """Build complete message context for LLM.

        Args:
            session_id: Session identifier for logging/metrics.
            system_prompt: System prompt (from session or config).
            history: Historical messages from session store.
            current_message: Current user input.
            model: Model name for template variables.
            created_at: Session creation timestamp for template variables.
            **extra_vars: Additional template variables passed to system prompt renderer.

        Returns:
            Tuple of (complete message list, optional region info for compression).
        """
        ...

    @property
    @abstractmethod
    def config(self) -> ContextConfig:
        """Get the configuration for this builder."""
        ...
