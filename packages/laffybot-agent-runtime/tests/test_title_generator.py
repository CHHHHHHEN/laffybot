"""Tests for TitleGenerator — truncation and fallback."""

from __future__ import annotations

from laffybot_agent_runtime.title_generator import TitleGenerator


class TestTruncateTitle:
    def test_short_text_preserved(self) -> None:
        result = TitleGenerator.truncate_title_from_message("hello")
        assert result == "hello"

    def test_long_text_truncated(self) -> None:
        text = "a" * 100
        result = TitleGenerator.truncate_title_from_message(text, max_length=10)
        assert len(result) <= 13  # 10 + "..."

    def test_whitespace_collapsed(self) -> None:
        result = TitleGenerator.truncate_title_from_message("hello    world")
        assert result == "hello world"

    def test_empty_text(self) -> None:
        result = TitleGenerator.truncate_title_from_message("")
        assert result == ""
