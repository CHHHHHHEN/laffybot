"""Approximate token counter — shared utility, no service-layer deps.

Moved here from laffybot.service.context.tokens so memory/
can use it without depending on the service layer.
"""

from __future__ import annotations

from typing import Any


class ApproximateTokenCounter:
    """Character-based approximate token counter (~4 chars per token)."""

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def count_message_tokens(self, message: dict[str, Any]) -> int:
        tokens = 0
        role = message.get("role", "")
        content = message.get("content", "")

        tokens += self.count_tokens(role)
        tokens += self.count_tokens(str(content))

        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tokens += self.count_tokens(tc.get("name", ""))
                    tokens += self.count_tokens(tc.get("arguments", ""))

        return tokens
