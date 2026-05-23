"""Extraction logic for generating structured memories from session messages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from laffybot.agent_runtime.providers.types import ErrorLLMResponse
from laffybot.memory.prompts import EXTRACT_MEMORY_PROMPT
from laffybot.utils.token_counter import ApproximateTokenCounter

if TYPE_CHECKING:
    from laffybot.agent_runtime.providers.base import BaseProvider

# Token budget reserved for the extraction prompt itself
PROMPT_TOKEN_BUDGET = 500

# Minimum conversation rounds required for extraction
MIN_REQUIRED_ROUNDS = 1  # At least 1 user + 1 assistant exchange


class MemoryExtractor:
    """Extract structured memories from session messages using LLM."""

    def __init__(self, provider: BaseProvider, model: str) -> None:
        self.provider = provider
        self.model = model
        self.token_counter = ApproximateTokenCounter()

    async def extract(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str, list[str]] | None:
        """Extract memory from a list of session messages.

        Returns (content, tags) if extraction produced valuable memory,
        or None if no-op (no reusable knowledge found).
        """
        filtered = self._filter_messages(messages)

        if not self._has_minimum_rounds(filtered):
            logger.debug("Memory extract skip: insufficient conversation rounds")
            return None

        truncated = self._truncate_messages(filtered)

        prompt = EXTRACT_MEMORY_PROMPT.format(
            conversation=self._format_conversation(truncated)
        )

        try:
            response = await self.provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3,
                max_tokens=2000,
            )

            if isinstance(response, ErrorLLMResponse):
                logger.warning(
                    "Memory extraction LLM call failed: error_kind={}",
                    response.error_kind,
                )
                return None

            if not response.content:
                logger.debug("Memory extraction skipped: empty LLM response")
                return None

            result = response.content.strip()

            if self._is_no_op(result):
                logger.debug("Memory extraction no-op: result rejected by gate")
                return None

            content, tags = self._parse_result(result)
            return content, tags

        except Exception as e:
            logger.warning("Memory extraction failed: error={}", str(e))
            return None

    @staticmethod
    def _filter_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep only user/assistant/tool messages, sorted by timestamp."""
        filtered = [
            m for m in messages if m.get("role") in ("user", "assistant", "tool")
        ]
        return sorted(filtered, key=lambda m: m.get("timestamp", ""))

    @staticmethod
    def _has_minimum_rounds(messages: list[dict[str, Any]]) -> bool:
        """Check if there are at least one user and one assistant message."""
        has_user = any(m.get("role") == "user" for m in messages)
        has_assistant = any(m.get("role") == "assistant" for m in messages)
        return has_user and has_assistant

    def _truncate_messages(
        self,
        messages: list[dict[str, Any]],
        max_context_tokens: int = 128000,
    ) -> list[dict[str, Any]]:
        """Truncate messages from oldest to fit within context window.

        Reserves PROMPT_TOKEN_BUDGET tokens for the extraction prompt.
        Ensures at least MIN_REQUIRED_ROUNDS of conversation are preserved.
        """
        available = max_context_tokens - PROMPT_TOKEN_BUDGET

        total_tokens = sum(self.token_counter.count_message_tokens(m) for m in messages)

        if total_tokens <= available:
            return messages

        # Drop oldest messages until within budget, preserving minimum rounds
        for i in range(len(messages)):
            candidate = messages[i:]
            if self._has_minimum_rounds(candidate):
                candidate_tokens = sum(
                    self.token_counter.count_message_tokens(m) for m in candidate
                )
                if candidate_tokens <= available:
                    logger.debug(
                        "Truncated {} messages for memory extraction: kept={}",
                        i,
                        len(candidate),
                    )
                    return candidate

        # Fallback: keep only the last several messages
        fallback = messages[-(MIN_REQUIRED_ROUNDS * 2) :]
        logger.debug(
            "Memory extraction truncation fallback: kept={}",
            len(fallback),
        )
        return fallback

    @staticmethod
    def _format_conversation(messages: list[dict[str, Any]]) -> str:
        """Format messages into a conversation text for the LLM prompt."""
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                parts.append(f"{role}: {content}")
        return "\n".join(parts)

    @staticmethod
    def _is_no_op(result: str) -> bool:
        """Check if the LLM result indicates no valuable memory."""
        return result.strip().upper() == "NO_MEMORY"

    @staticmethod
    def _parse_result(result: str) -> tuple[str, list[str]]:
        """Parse LLM result into (content, tags).

        Expects content with optional tags indicated by #tag syntax.
        """
        tags: list[str] = []
        lines = result.split("\n")
        content_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Tags:") or stripped.startswith("tags:"):
                tag_str = stripped.split(":", 1)[1].strip()
                tags = [t.strip().lstrip("#") for t in tag_str.split(",") if t.strip()]
            elif stripped and not stripped.startswith("#"):
                content_lines.append(stripped)

        content = "\n".join(content_lines).strip()
        return content, tags
