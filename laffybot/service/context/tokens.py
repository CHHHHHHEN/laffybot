"""Token counting strategies (service layer)."""

from typing import Any

from laffybot.utils.token_counter import (
    ApproximateTokenCounter as ApproximateTokenCounter,  # noqa: F401
)

from .base import TokenCounter


class UsageBasedTokenCounter(TokenCounter):
    """Prefers exact token counts from LLM usage metadata; falls back to approximate."""

    def __init__(self) -> None:
        self._fallback = ApproximateTokenCounter()

    def count_tokens(self, text: str) -> int:
        return self._fallback.count_tokens(text)

    def count_message_tokens(self, message: dict[str, Any]) -> int:
        input_tokens = message.get("input_tokens")
        if input_tokens is not None and isinstance(input_tokens, int):
            return input_tokens

        return self._fallback.count_message_tokens(message)
