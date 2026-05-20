"""Simple context builder implementation."""

import json
from datetime import datetime
from typing import Any

from loguru import logger

from laffybot.agent.tools.registry import ToolRegistry

from .base import ContextBuilder, TokenCounter
from .compressor import CompressionDetector, prune_tool_outputs
from .templates import SystemPromptTemplate
from .tokens import ApproximateTokenCounter, UsageBasedTokenCounter
from .types import ContextConfig, RegionInfo


def _normalize_assistant_tool_calls(message: dict[str, Any]) -> dict[str, Any]:
    """Convert stored tool_calls format to OpenAI API format.

    Stored format (for UI):
        {"tool_call_id": ..., "name": ..., "arguments": ..., "status": ..., ...}

    OpenAI format (for API):
        {"id": ..., "type": "function", "function": {"name": ..., "arguments": ...}}
    """
    tool_calls = message.get("tool_calls", [])
    if not tool_calls:
        return message

    normalized = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue

        tc_id = tc.get("tool_call_id") or tc.get("id")
        if not tc_id:
            continue

        if tc.get("type") == "function" and "function" in tc:
            normalized.append(tc)
            continue

        name = tc.get("name")
        args = tc.get("arguments")
        if not name:
            continue

        if args is None:
            args = "{}"
        elif not isinstance(args, str):
            try:
                args = json.dumps(args, ensure_ascii=False)
            except (TypeError, ValueError):
                args = "{}"

        normalized.append(
            {
                "id": tc_id,
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )

    if not normalized:
        return message

    result = {k: v for k, v in message.items() if k != "tool_calls"}
    result["tool_calls"] = normalized
    return result


class SimpleContextBuilder(ContextBuilder):
    """Basic context builder with token counting and capacity control.

    Assembles messages in order: system prompt, history, current message.
    Applies capacity control via tool output pruning and compression detection.
    """

    def __init__(
        self,
        config: ContextConfig,
        token_counter: TokenCounter | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        """Initialize context builder.

        Args:
            config: Configuration for context building.
            token_counter: Token counting strategy. Defaults to UsageBasedTokenCounter.
            tool_registry: Optional ToolRegistry for kind-based tool output protection.
        """
        self._config = config
        self._token_counter = token_counter or UsageBasedTokenCounter()
        self._template_renderer = SystemPromptTemplate(config)
        self._compression_detector = CompressionDetector(
            config, ApproximateTokenCounter()
        )
        self._tool_registry = tool_registry

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
        **extra_vars: Any,
    ) -> tuple[list[dict[str, Any]], RegionInfo | None]:
        """Build complete message context with capacity control.

        Process:
        1. Render system prompt from template or use static prompt
        2. Add historical messages
        3. Add current user message
        4. Apply capacity control (prune tool outputs, detect compression region)
        5. Return final message list and optional region info
        """
        messages: list[dict[str, Any]] = []

        # 1. Render system prompt
        if self._config.system_prompt_template:
            effective_prompt = self._template_renderer.render(
                session_id=session_id,
                model=model,
                created_at=created_at,
                **extra_vars,
            )
        else:
            effective_prompt = self._config.system_prompt

        has_system = bool(effective_prompt)
        if effective_prompt:
            messages.append({"role": "system", "content": effective_prompt})

        # 2/3. Add history + current message
        for msg in history:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                messages.append(_normalize_assistant_tool_calls(msg))
            else:
                messages.append(msg)
        messages.append({"role": "user", "content": current_message})

        # 4. Apply capacity control (pruning then detection)
        messages, region_info = self._apply_capacity_control(
            messages, has_system, session_id
        )

        return messages, region_info

    def _apply_capacity_control(
        self,
        messages: list[dict[str, Any]],
        has_system_prompt: bool,
        session_id: str,
    ) -> tuple[list[dict[str, Any]], RegionInfo | None]:
        """Apply tool output pruning and compression detection.

        Stage 0: Prune tool outputs (sync, in-memory)
        Stage 1: Detect compressible region (sync, no LLM)

        Returns (messages, region_info).
        """
        # Stage 0: Prune tool outputs
        try:
            messages = prune_tool_outputs(messages, self._config, self._tool_registry)
        except Exception:
            logger.warning("Tool output pruning failed: session_id={}", session_id)

        # Stage 1: Detect compressible region
        region_info: RegionInfo | None = None
        try:
            if self._config.max_tokens is not None and self._config.enable_compression:
                region_info = self._compression_detector.detect(
                    messages, has_system_prompt
                )
        except Exception:
            logger.warning("Compression detection failed: session_id={}", session_id)

        return messages, region_info
