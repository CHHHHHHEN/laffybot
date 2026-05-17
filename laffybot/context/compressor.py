"""Context compression components: pruning, detection, and summarization."""

from __future__ import annotations

from typing import Any

from loguru import logger

from laffybot.config import ContextConfig
from laffybot.context.tokens import ApproximateTokenCounter
from laffybot.context.types import RegionInfo
from laffybot.providers.base import BaseProvider
from laffybot.providers.types import ErrorLLMResponse

_SUMMARY_SYSTEM_PROMPT = """You are a precise summarizer. Your task is to compress a conversation segment into a structured summary that preserves all critical information for ongoing context.

Output format — use these sections:

Goal: <the original user goal and task description>
Constraints & Preferences: <any constraints, preferences, or requirements mentioned>
Progress: <what has been accomplished, what is in progress, what is blocked>
Key Decisions: <important decisions made by the user or conclusions reached>
Next Steps: <planned next actions or pending items>
Critical Context: <important facts, data points, tool results, or context needed for future turns>
Relevant Files: <any files, code modules, or resources referenced or modified>

Rules:
- Use concise bullet points, not paragraphs
- Preserve all factual data, numeric values, error messages, and decisions
- Include tool execution results when they produced meaningful output
- Do NOT add commentary, opinions, or suggestions
- If a section has nothing to report, write "None"
- Keep the total summary under 400 tokens"""


_SUMMARY_USER_TEMPLATE = """Summarize the following conversation segment, preserving all critical information for future context:

{conversation_text}

Output the summary using the structured format (Goal, Constraints & Preferences, Progress, Key Decisions, Next Steps, Critical Context, Relevant Files)."""


def prune_tool_outputs(
    messages: list[dict[str, Any]],
    config: ContextConfig,
) -> list[dict[str, Any]]:
    """Synchronously prune tool output messages that exceed character limit.

    Operates in memory only — does not modify persisted messages.
    Protected tools (e.g. "skill") are not pruned.
    """
    max_chars = config.compress_tool_output_max_chars
    if max_chars <= 0:
        return messages

    protected = set(config.compress_protected_tools)

    result: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") not in ("tool", "function"):
            result.append(msg)
            continue

        tool_name = msg.get("name", "")
        if tool_name in protected:
            result.append(msg)
            continue

        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > max_chars:
            truncated = content[:max_chars]
            truncated += f"\n... (truncated, original {len(content)} chars)"
            msg = {**msg, "content": truncated}

        result.append(msg)

    return result


class CompressionDetector:
    """Synchronous detector that checks whether compression is needed.

    Pure function — no storage awareness, no LLM calls.
    """

    def __init__(
        self,
        config: ContextConfig,
        token_counter: ApproximateTokenCounter | None = None,
    ):
        self._config = config
        self._token_counter = token_counter or ApproximateTokenCounter()

    def detect(
        self,
        messages: list[dict[str, Any]],
        has_system_prompt: bool,
    ) -> RegionInfo | None:
        """Check if compression is needed and return compressible region info.

        Always preserves:
        - System prompt (if present)
        - Most recent compress_preserve_pairs user-assistant pairs
        - The current (last) message

        Returns RegionInfo with compressible message IDs or None.
        """
        if not self._config.enable_compression:
            return None

        if self._config.max_tokens is None:
            return None

        if len(messages) < self._config.compress_preserve_pairs * 2 + 2:
            return None

        total_tokens = sum(
            self._token_counter.count_message_tokens(m) for m in messages
        )
        usage_ratio = total_tokens / self._config.max_tokens

        if usage_ratio < self._config.compress_threshold_ratio:
            return None

        system_idx = 0 if has_system_prompt else -1
        current_idx = len(messages) - 1

        tail_pair_count = self._config.compress_preserve_pairs
        tail_start = current_idx - tail_pair_count * 2

        compressible_ids: list[int] = []
        compressible_tokens = 0
        tail_tokens = 0

        for i, msg in enumerate(messages):
            if i == system_idx or i == current_idx:
                continue
            if i >= tail_start:
                tail_tokens += self._token_counter.count_message_tokens(msg)
                continue
            compressible_ids.append(i)
            compressible_tokens += self._token_counter.count_message_tokens(msg)

        if not compressible_ids:
            return None

        reserved = self._config.compress_reserved_tokens
        summary_budget = self._config.compress_max_summary_tokens
        tail_budget = self._config.compress_preserve_recent_tokens
        if tail_budget is None:
            tail_budget = min(max(tail_tokens, 2000), 8000) if tail_tokens > 0 else 0

        available = self._config.max_tokens - reserved - summary_budget - tail_budget

        if compressible_tokens <= available:
            return None

        token_ratio = compressible_tokens / self._config.max_tokens

        return RegionInfo(message_ids=compressible_ids, token_ratio=token_ratio)


class LLMSummarizer:
    """Execute LLM summarization for a compressible message region.

    Receives messages, calls LLM via non-streaming chat_completion,
    returns summary text. Never throws — returns empty string on failure.
    """

    def __init__(self, provider: BaseProvider, model: str):
        self._provider = provider
        self._model = model

    async def summarize(self, messages: list[dict[str, Any]]) -> str:
        """Summarize messages using LLM.

        Returns summary text, or empty string on failure.
        """
        try:
            conversation_text = self._format_conversation(messages)
            user_prompt = _SUMMARY_USER_TEMPLATE.format(
                conversation_text=conversation_text
            )

            response = await self._provider.chat_completion(
                messages=[
                    {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=self._model,
                temperature=0.3,
            )

            if isinstance(response, ErrorLLMResponse):
                logger.warning(
                    "LLM summary generation failed: error_kind={}",
                    response.error_kind,
                )
                return ""

            if response.content:
                return response.content.strip()

            logger.warning("LLM summary returned empty content")
            return ""

        except Exception:
            logger.warning("LLM summarization failed", exc_info=True)
            return ""

    @staticmethod
    def _format_conversation(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            name = msg.get("name")
            prefix = f"[{role}"
            if name:
                prefix += f" ({name})"
            prefix += "]"
            lines.append(f"{prefix}: {content}")
        return "\n\n".join(lines)
