"""Tests for MCP wrappers — name normalisation, schema, ToolFilter, tool classes."""

from __future__ import annotations

from typing import Any

import pytest

from laffybot.agent_runtime.tools.mcp.wrappers import (
    McpPromptTool,
    McpResourceTool,
    McpToolCall,
    ToolFilter,
    _content_to_text,
    _normalise_input_schema,
    _normalise_tool_name,
    normalise_server_name,
)


class TestNameNormalisation:
    def test_normalise_server_name(self) -> None:
        assert normalise_server_name("My Server!") == "My_Server"

    def test_collapses_underscores(self) -> None:
        assert normalise_server_name("a___b") == "a_b"

    def test_strips_leading_trailing_underscores(self) -> None:
        assert normalise_server_name("__hello__") == "hello"

    def test_normalise_tool_name(self) -> None:
        result = _normalise_tool_name("My Server", "my.tool")
        assert result == "My_Server_my_tool"

    def test_normalise_tool_name_preserves_hyphen(self) -> None:
        result = _normalise_tool_name("server", "my-tool")
        assert result == "server_my-tool"

    def test_normalise_tool_name_truncated(self) -> None:
        long_server = "a" * 40
        long_tool = "b" * 40
        result = _normalise_tool_name(long_server, long_tool)
        assert len(result) == 64


class TestNormaliseInputSchema:
    def test_none_returns_empty(self) -> None:
        assert _normalise_input_schema(None) == {"type": "object", "properties": {}}

    def test_removes_dollar_schema(self) -> None:
        result = _normalise_input_schema({"$schema": "http://...", "type": "object"})
        assert "$schema" not in result

    def test_adds_properties_when_missing(self) -> None:
        result = _normalise_input_schema({"type": "object"})
        assert result["properties"] == {}

    def test_nullable_union_unpacked(self) -> None:
        result = _normalise_input_schema(
            {"type": ["string", "null"], "properties": {"name": {}}}
        )
        assert result["type"] == "string"
        assert result.get("nullable") is True

    def test_anyof_with_null(self) -> None:
        result = _normalise_input_schema(
            {
                "properties": {
                    "value": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                    }
                }
            }
        )
        prop = result["properties"]["value"]
        assert prop["type"] == "string"
        assert prop.get("nullable") is True


class TestToolFilter:
    def test_default_allows_all(self) -> None:
        f = ToolFilter()
        assert f.allows("anything") is True

    def test_deny_overrides_allow(self) -> None:
        f = ToolFilter(disabled_tools=["bad"])
        assert f.allows("bad") is False
        assert f.allows("good") is True

    def test_enabled_restricts_to_list(self) -> None:
        f = ToolFilter(enabled_tools=["a", "b"])
        assert f.allows("a") is True
        assert f.allows("c") is False

    def test_apply_filters_tool_list(self) -> None:
        f = ToolFilter(disabled_tools=["bad"])
        tools = [{"name": "good"}, {"name": "bad"}, {"name": "ok"}]
        result = f.apply(tools)
        assert len(result) == 2
        assert result[0]["name"] == "good"

    def test_enabled_and_disabled(self) -> None:
        f = ToolFilter(enabled_tools=["a", "b", "c"], disabled_tools=["b"])
        assert f.allows("a") is True
        assert f.allows("b") is False
        assert f.allows("d") is False


class TestContentToText:
    def test_text_block(self) -> None:
        result = _content_to_text([{"type": "text", "text": "hello"}])
        assert result == "hello"

    def test_image_block(self) -> None:
        result = _content_to_text(
            [{"type": "image", "mimeType": "image/png", "data": "abcdef"}]
        )
        assert "[Image:" in result

    def test_resource_block(self) -> None:
        result = _content_to_text(
            [{"type": "resource", "resource": {"uri": "file:///tmp"}}]
        )
        assert "[Resource:" in result

    def test_mixed_blocks(self) -> None:
        result = _content_to_text(
            [
                {"type": "text", "text": "hello"},
                {"type": "image", "mimeType": "image/png", "data": "abc"},
            ]
        )
        assert "hello" in result
        assert "[Image:" in result


class TestMcpToolCall:
    @pytest.mark.asyncio
    async def test_execute_calls_manager(self) -> None:
        manager = _MockManager()
        tool_def = {
            "name": "read_file",
            "description": "Read a file",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        }
        tool = McpToolCall("filesys", tool_def, manager)
        assert tool.name == "filesys_read_file"
        assert "Read a file" in tool.description

        result = await tool.execute(path="/tmp/test.txt")
        assert "ok" in result

    @pytest.mark.asyncio
    async def test_execute_with_error(self) -> None:
        class _ErrorManager:
            async def call_tool(
                self,
                server_name: str,
                tool_name: str,
                arguments: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                return {
                    "content": [{"type": "text", "text": "failed"}],
                    "isError": True,
                }

        tool = McpToolCall(
            "srv", {"name": "bad_tool", "description": ""}, _ErrorManager()
        )
        result = await tool.execute()
        assert result.startswith("Error:")


class _MockManager:
    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": "ok"}]}

    async def read_resource(self, server_name: str, uri: str) -> list[dict[str, Any]]:
        return [{"type": "text", "text": f"resource {uri}"}]

    async def get_prompt(
        self,
        server_name: str,
        prompt_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "messages": [
                {
                    "role": "assistant",
                    "content": {"type": "text", "text": "prompt response"},
                }
            ]
        }


class TestMcpResourceTool:
    @pytest.mark.asyncio
    async def test_execute_reads_resource(self) -> None:
        tool = McpResourceTool(
            "filesys",
            {
                "uri": "file:///tmp/test.txt",
                "name": "test_file",
                "description": "A test resource",
            },
            _MockManager(),
        )
        assert "resource" in tool.name
        result = await tool.execute()
        assert "resource file:///tmp/test.txt" in result


class TestMcpPromptTool:
    @pytest.mark.asyncio
    async def test_execute_gets_prompt(self) -> None:
        tool = McpPromptTool(
            "my_server",
            {"name": "greet", "description": "Greeting prompt"},
            _MockManager(),
        )
        assert "prompt" in tool.name
        result = await tool.execute()
        assert "prompt response" in result
