"""Simple context builder implementation."""

from datetime import datetime
from typing import Any

from loguru import logger

from .base import ContextBuilder, TokenCounter
from .templates import SystemPromptTemplate
from .tokens import UsageBasedTokenCounter
from .types import ContextConfig


class SimpleContextBuilder(ContextBuilder):
    """Basic context builder with token counting and capacity control.

    Assembles messages in order: system prompt, history, current message.
    Applies capacity control by truncating oldest history when limits exceeded.
    """

    def __init__(
        self,
        config: ContextConfig,
        token_counter: TokenCounter | None = None,
    ):
        """Initialize context builder.

        Args:
            config: Configuration for context building.
            token_counter: Token counting strategy. Defaults to UsageBasedTokenCounter.
        """
        self._config = config
        self._token_counter = token_counter or UsageBasedTokenCounter()
        self._template_renderer = SystemPromptTemplate(config)

    @property
    def config(self) -> ContextConfig:
        return self._config

    async def build_messages(
        self,
        session_id: str,
        system_prompt: str | None,
        history: list[dict[str, Any]],
        current_message: str,
        model: str | None = None,
        created_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Build complete message context with capacity control.

        Process:
        1. Render system prompt from template or use static prompt
        2. Add historical messages
        3. Add current user message
        4. Apply capacity control (truncate history if needed)
        5. Return final message list
        """
        messages: list[dict[str, Any]] = []

        # 1. Render system prompt
        # Priority: session-specific prompt > config template > config static prompt
        effective_prompt = system_prompt
        if effective_prompt is None and self._config.system_prompt_template:
            effective_prompt = self._template_renderer.render(
                session_id=session_id,
                model=model,
                created_at=created_at,
            )
        elif effective_prompt is None:
            effective_prompt = self._config.system_prompt

        if effective_prompt:
            messages.append({"role": "system", "content": effective_prompt})

        # 2. Add history (will be truncated later if needed)
        messages.extend(history)

        # 3. Add current message
        messages.append({"role": "user", "content": current_message})

        # 4. Apply capacity control
        messages = self._apply_capacity_control(
            messages, effective_prompt is not None, session_id
        )

        return messages

    def _apply_capacity_control(
        self,
        messages: list[dict[str, Any]],
        has_system_prompt: bool,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """Apply token and message count limits.

        Always preserves:
        - System prompt (if present)
        - Current user message (last message)
        - At least min_preserve_pairs of user-assistant pairs

        Truncation strategy:
        - Remove oldest user-assistant pairs first
        - Stop when limits satisfied or minimum preserved
        """
        # No limits configured
        if self._config.max_tokens is None and self._config.max_messages is None:
            return messages

        # Separate fixed messages from truncatable history
        fixed_messages: list[dict[str, Any]] = []
        truncatable: list[dict[str, Any]] = []

        # System prompt is fixed (first message if present)
        system_idx = 0 if has_system_prompt else -1
        # Current message is fixed (last message)
        current_idx = len(messages) - 1

        for i, msg in enumerate(messages):
            if i == system_idx or i == current_idx:
                fixed_messages.append(msg)
            else:
                truncatable.append(msg)

        # Check if we need to truncate
        needs_truncation = False

        if self._config.max_messages is not None:
            # Total messages = fixed + truncatable
            # We need space for fixed messages
            max_history = self._config.max_messages - len(fixed_messages)
            if len(truncatable) > max_history:
                needs_truncation = True

        if self._config.max_tokens is not None:
            total_tokens = self._count_tokens(messages)
            if total_tokens > self._config.max_tokens:
                needs_truncation = True

        if not needs_truncation:
            return messages

        original_count = len(messages)
        logger.debug(
            "Context capacity control triggered: session_id={}, original_messages={}, max_tokens={}, max_messages={}",
            session_id,
            original_count,
            self._config.max_tokens,
            self._config.max_messages,
        )

        # Truncate history while respecting min_preserve_pairs
        min_pairs = self._config.min_preserve_pairs
        # Each pair is 2 messages (user + assistant)
        min_preserve = min_pairs * 2

        while truncatable and (
            self._exceeds_message_limit(truncatable, fixed_messages)
            or self._exceeds_token_limit(truncatable, fixed_messages)
        ):
            # Don't truncate below minimum preserve
            if len(truncatable) <= min_preserve:
                break

            # Remove oldest pair (user + assistant)
            # Find the oldest user message to remove
            if len(truncatable) >= 2:
                # Remove first two messages (oldest pair)
                truncatable = truncatable[2:]
            else:
                # Only one message left, remove it
                truncatable = []

        # Reassemble: system + truncated history + current
        result: list[dict[str, Any]] = []
        if has_system_prompt:
            result.append(fixed_messages[0])
        result.extend(truncatable)
        result.append(fixed_messages[-1])  # Current message

        logger.debug(
            "Context truncated: session_id={}, messages {} -> {}",
            session_id,
            original_count,
            len(result),
        )

        return result

    def _count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Count total tokens in message list."""
        return sum(self._token_counter.count_message_tokens(msg) for msg in messages)

    def _exceeds_message_limit(
        self,
        truncatable: list[dict[str, Any]],
        fixed: list[dict[str, Any]],
    ) -> bool:
        """Check if message count exceeds limit."""
        if self._config.max_messages is None:
            return False
        return len(truncatable) + len(fixed) > self._config.max_messages

    def _exceeds_token_limit(
        self,
        truncatable: list[dict[str, Any]],
        fixed: list[dict[str, Any]],
    ) -> bool:
        """Check if token count exceeds limit."""
        if self._config.max_tokens is None:
            return False
        total = self._count_tokens(truncatable) + self._count_tokens(fixed)
        return total > self._config.max_tokens
