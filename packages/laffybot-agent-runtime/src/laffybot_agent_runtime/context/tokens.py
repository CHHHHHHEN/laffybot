"""Token counting strategies for context management."""

import re
from typing import Any

from .base import TokenCounter


class ApproximateTokenCounter(TokenCounter):
    """Approximate token counter using character-based estimation.

    Does not require external dependencies like tiktoken.
    Uses different ratios for different languages:
    - English/Latin: ~4 chars per token
    - Chinese/CJK: ~2 chars per token (more conservative)

    This is intentionally imprecise but sufficient for capacity control.
    """

    # Unicode ranges for CJK characters
    CJK_PATTERN = re.compile(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff]"
    )

    # Role overhead in tokens (approximate)
    ROLE_OVERHEAD = 4  # {"role": "user", "content": "..."} overhead

    def count_tokens(self, text: str) -> int:
        """Count tokens using character-based estimation.

        Detects language and applies appropriate ratio.
        Mixed content uses weighted average.
        """
        if not text:
            return 0

        # Count CJK characters
        cjk_chars = len(self.CJK_PATTERN.findall(text))
        total_chars = len(text)
        non_cjk_chars = total_chars - cjk_chars

        # Calculate tokens for each segment
        cjk_tokens = cjk_chars / 2  # Conservative for CJK
        non_cjk_tokens = non_cjk_chars / 4  # Standard for Latin

        # Sum and round up
        return int(cjk_tokens + non_cjk_tokens) + 1

    def count_message_tokens(self, message: dict[str, Any]) -> int:
        """Count tokens in a message including role overhead."""
        content = message.get("content", "")
        if isinstance(content, str):
            content_tokens = self.count_tokens(content)
        else:
            # Handle non-string content (e.g., tool calls)
            content_tokens = self.count_tokens(str(content))

        return content_tokens + self.ROLE_OVERHEAD


class UsageBasedTokenCounter(TokenCounter):
    """Token counter that uses exact counts from LLM usage metadata.

    Falls back to approximate counting when usage data is unavailable.
    This is the preferred counter when LLM responses include usage info.
    """

    def __init__(self, fallback_counter: TokenCounter | None = None):
        """Initialize with optional fallback counter.

        Args:
            fallback_counter: Counter to use when usage data unavailable.
                             Defaults to ApproximateTokenCounter.
        """
        self._fallback = fallback_counter or ApproximateTokenCounter()

    def count_tokens(self, text: str) -> int:
        """Count tokens using fallback (usage requires message context)."""
        return self._fallback.count_tokens(text)

    def count_message_tokens(self, message: dict[str, Any]) -> int:
        """Count tokens using usage metadata if available, else fallback.

        Expects message to have 'input_tokens' or 'output_tokens' metadata
        from LLM response usage.
        """
        # Check for exact token counts in metadata
        if "input_tokens" in message:
            return int(message["input_tokens"])
        if "output_tokens" in message:
            return int(message["output_tokens"])

        # Fallback to approximate counting
        return self._fallback.count_message_tokens(message)

    def count_tokens_from_usage(
        self, usage: dict[str, int], role: str = "assistant"
    ) -> int:
        """Extract token count from LLM usage dict.

        Args:
            usage: Usage dict from LLM response with keys like
                   'prompt_tokens', 'completion_tokens', 'total_tokens'.
            role: Message role ('user' or 'assistant').

        Returns:
            Token count for the message.
        """
        if role == "assistant":
            # Assistant messages use completion_tokens
            return int(usage.get("completion_tokens", 0))
        else:
            # User messages use prompt_tokens (less common)
            return int(usage.get("prompt_tokens", 0))
