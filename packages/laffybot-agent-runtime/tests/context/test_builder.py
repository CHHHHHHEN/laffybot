"""Tests for SimpleContextBuilder — message assembly and capacity control."""

from __future__ import annotations

import pytest

from laffybot_agent_runtime.config import ContextConfig
from laffybot_agent_runtime.context.builder import SimpleContextBuilder


class TestBuildMessages:
    @pytest.mark.asyncio
    async def test_system_prompt_included(self) -> None:
        config = ContextConfig(system_prompt_template=None)
        builder = SimpleContextBuilder(config)
        messages, region = await builder.build_messages(
            session_id="s1",
            system_prompt=None,
            history=[],
            current_message="hi",
        )
        assert messages[0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_history_and_current_message(self) -> None:
        config = ContextConfig(system_prompt_template=None)
        builder = SimpleContextBuilder(config)
        messages, region = await builder.build_messages(
            session_id="s1",
            system_prompt=None,
            history=[{"role": "user", "content": "prev"}],
            current_message="current",
        )
        assert len(messages) == 3  # system + history + current
        assert messages[1] == {"role": "user", "content": "prev"}
        assert messages[2] == {"role": "user", "content": "current"}

    @pytest.mark.asyncio
    async def test_assistant_tool_calls_normalized(self) -> None:
        config = ContextConfig(system_prompt_template=None)
        builder = SimpleContextBuilder(config)
        history = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "tool_call_id": "c1",
                        "name": "read_file",
                        "arguments": {"path": "/tmp"},
                    },
                ],
            }
        ]
        messages, region = await builder.build_messages(
            session_id="s1",
            system_prompt=None,
            history=history,
            current_message="done",
        )
        # Find the assistant message
        asst = [m for m in messages if m.get("role") == "assistant"]
        assert len(asst) == 1
        tc = asst[0]["tool_calls"][0]
        assert tc["id"] == "c1"
        assert tc["function"]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_system_prompt_template_renders(
        self, context_config: ContextConfig
    ) -> None:
        config = ContextConfig(
            system_prompt_template="Hello {{ session_id }}",
        )
        builder = SimpleContextBuilder(config)
        messages, region = await builder.build_messages(
            session_id="test123",
            system_prompt=None,
            history=[],
            current_message="hi",
        )
        assert "Hello test123" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_config_property(self) -> None:
        config = ContextConfig(system_prompt_template=None)
        builder = SimpleContextBuilder(config)
        assert builder.config is config
