"""Tests for context compression — pruning, detection, summarization."""

from __future__ import annotations

import pytest

from laffybot_agent_runtime.config import ContextConfig
from laffybot_agent_runtime.context.compressor import (
    CompressionDetector,
    LLMSummarizer,
    prune_tool_outputs,
)
from laffybot_agent_runtime.context.types import RegionInfo
from laffybot_agent_runtime.tools.registry import ToolRegistry


class TestPruneToolOutputs:
    def test_prunes_long_output(self) -> None:
        config = ContextConfig(compress_tool_output_max_chars=5)
        messages = [
            {"role": "tool", "name": "read_file", "content": "x" * 100},
        ]
        result = prune_tool_outputs(messages, config)
        assert len(result[0]["content"]) < 50
        assert "truncated" in result[0]["content"]

    def test_skips_non_tool_messages(self) -> None:
        config = ContextConfig(compress_tool_output_max_chars=5)
        messages = [
            {"role": "user", "content": "hello"},
        ]
        result = prune_tool_outputs(messages, config)
        assert result == messages

    def test_respects_max_chars_zero(self) -> None:
        config = ContextConfig(compress_tool_output_max_chars=0)
        messages = [{"role": "tool", "name": "t", "content": "long" * 100}]
        result = prune_tool_outputs(messages, config)
        assert result == messages

    def test_protected_tool_not_pruned(self) -> None:
        config = ContextConfig(
            compress_tool_output_max_chars=5,
            compress_protected_tools=["skill_view"],  # name-based protection
        )
        messages = [
            {"role": "tool", "name": "skill_view", "content": "x" * 100},
        ]
        result = prune_tool_outputs(messages, config)
        assert len(result[0]["content"]) == 100

    def test_protected_via_registry(self, tool_registry: ToolRegistry) -> None:
        config = ContextConfig(
            compress_tool_output_max_chars=5,
            compress_protected_tools=["skill"],
        )
        messages = [
            {"role": "tool", "name": "mock_tool", "content": "x" * 100},
        ]
        result = prune_tool_outputs(messages, config, tool_registry=tool_registry)
        # mock_tool has kind="builtin", not "skill" → should be pruned
        assert "truncated" in result[0]["content"]


class TestCompressionDetector:
    def test_returns_none_when_disabled(self) -> None:
        config = ContextConfig(enable_compression=False, max_tokens=1000)
        detector = CompressionDetector(config)
        result = detector.detect(
            [{"role": "user", "content": "hi"}],
            has_system_prompt=False,
        )
        assert result is None

    def test_returns_none_when_below_threshold(self) -> None:
        config = ContextConfig(max_tokens=10000, compress_threshold_ratio=0.8)
        detector = CompressionDetector(config)
        messages = [{"role": "user", "content": "short"}] * 5
        result = detector.detect(messages, has_system_prompt=False)
        assert result is None

    def test_returns_region_when_above_threshold(self) -> None:
        config = ContextConfig(
            max_tokens=50,
            compress_threshold_ratio=0.01,
            compress_reserved_tokens=0,
            compress_max_summary_tokens=10,
            compress_preserve_recent_tokens=0,
            compress_preserve_pairs=1,
        )
        detector = CompressionDetector(config)
        messages = [{"role": "user", "content": "x" * 200}] * 5
        result = detector.detect(messages, has_system_prompt=False)
        assert isinstance(result, RegionInfo)
        assert len(result.message_ids) > 0

    def test_preserves_system_prompt(self) -> None:
        config = ContextConfig(
            max_tokens=50,
            compress_threshold_ratio=0.01,
            compress_reserved_tokens=0,
            compress_max_summary_tokens=10,
            compress_preserve_recent_tokens=0,
            compress_preserve_pairs=1,
        )
        detector = CompressionDetector(config)
        messages = [{"role": "system", "content": "sys"}] + [
            {"role": "user", "content": "x" * 200}
        ] * 5
        result = detector.detect(messages, has_system_prompt=True)
        assert isinstance(result, RegionInfo)
        assert 0 not in result.message_ids


class TestLLMSummarizer:
    @pytest.mark.asyncio
    async def test_summarize_returns_empty_on_error(self) -> None:
        """When provider returns ErrorLLMResponse, summarizer returns ''."""
        summarizer = LLMSummarizer(provider=None, model="test")  # type: ignore[arg-type]
        result = await summarizer.summarize([{"role": "user", "content": "hi"}])
        assert result == ""
