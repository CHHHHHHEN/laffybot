"""Simple context builder implementation (service layer)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from .base import ContextBuilder, TokenCounter
from .compressor import CompressionDetector, prune_tool_outputs
from .templates import SystemPromptTemplate
from .tokens import ApproximateTokenCounter, UsageBasedTokenCounter
from .types import ContextConfig, RegionInfo

if TYPE_CHECKING:
    from laffybot.agent_runtime.providers.base import BaseProvider
    from laffybot.agent_runtime.tools.registry import ToolRegistry


def _normalize_assistant_tool_calls(message: dict[str, Any]) -> dict[str, Any]:
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
    def __init__(
        self,
        config: ContextConfig,
        token_counter: TokenCounter | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
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
        messages: list[dict[str, Any]] = []

        if self._config.system_prompt_template:
            effective_prompt = self._template_renderer.render(
                session_id=session_id,
                model=model,
                created_at=created_at,
                **extra_vars,
            )
        else:
            effective_prompt = system_prompt or self._config.system_prompt

        if effective_prompt:
            messages.append({"role": "system", "content": effective_prompt})

        for msg in history:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                messages.append(_normalize_assistant_tool_calls(msg))
            else:
                messages.append(msg)
        messages.append({"role": "user", "content": current_message})

        messages, region_info = self._apply_capacity_control(
            messages, bool(effective_prompt), session_id
        )

        return messages, region_info

    async def compress_messages(
        self,
        messages: list[dict[str, Any]],
        model: str,
        provider: BaseProvider,
    ) -> tuple[list[dict[str, Any]], RegionInfo | None]:
        has_system = bool(messages and messages[0].get("role") == "system")
        region_info = None
        if self._config.enable_compression and self._config.max_tokens is not None:
            compressor = CompressionDetector(self._config, ApproximateTokenCounter())
            region_info = compressor.detect(messages, has_system)
        return messages, region_info

    def _apply_capacity_control(
        self,
        messages: list[dict[str, Any]],
        has_system_prompt: bool,
        session_id: str,
    ) -> tuple[list[dict[str, Any]], RegionInfo | None]:
        try:
            messages = prune_tool_outputs(messages, self._config, self._tool_registry)
        except Exception:
            logger.warning("Tool output pruning failed: session_id={}", session_id)

        region_info: RegionInfo | None = None
        try:
            if self._config.max_tokens is not None and self._config.enable_compression:
                region_info = self._compression_detector.detect(
                    messages, has_system_prompt
                )
        except Exception:
            logger.warning("Compression detection failed: session_id={}", session_id)

        return messages, region_info
