"""Tests for McpClient — JSON-RPC protocol over mock transport."""

from __future__ import annotations

import json
from typing import Any

import pytest

from laffybot_agent_runtime.tools.mcp.client import (
    McpClient,
    McpError,
    McpProtocolError,
    _make_notification,
    _make_request,
    _parse_response,
)


class TestMakeRequest:
    def test_basic_request(self) -> None:
        result = _make_request("ping", None, 1)
        parsed = json.loads(result)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["method"] == "ping"
        assert "params" not in parsed

    def test_request_with_params(self) -> None:
        result = _make_request("tools/list", {}, 2)
        parsed = json.loads(result)
        assert parsed["params"] == {}


class TestMakeNotification:
    def test_notification_has_no_id(self) -> None:
        result = _make_notification("notifications/initialized")
        assert '"id"' not in result

    def test_notification_with_params(self) -> None:
        result = _make_notification("logging/setLevel", {"level": "debug"})
        assert '"params"' in result


class TestParseResponse:
    def test_valid_response(self) -> None:
        result = _parse_response('{"jsonrpc":"2.0","id":1,"result":"ok"}')
        assert result["result"] == "ok"

    def test_empty_string_raises(self) -> None:
        with pytest.raises(McpProtocolError, match="Empty"):
            _parse_response("")

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(McpProtocolError, match="JSON parse error"):
            _parse_response("not json")

    def test_non_dict_raises(self) -> None:
        with pytest.raises(McpProtocolError, match="not a JSON object"):
            _parse_response('"string"')


class TestMcpClient:
    @pytest.mark.asyncio
    async def test_send_request_returns_result(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        t.queue_response('{"jsonrpc":"2.0","id":1,"result":"hello"}')
        result = await client.send_request("ping")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_send_request_raises_mcp_error(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        t.queue_response(
            '{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Method not found"}}'
        )
        with pytest.raises(McpError, match="Method not found"):
            await client.send_request("unknown_method")

    @pytest.mark.asyncio
    async def test_discards_wrong_id(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        t.queue_response('{"jsonrpc":"2.0","id":999,"result":"wrong"}')
        t.queue_response('{"jsonrpc":"2.0","id":1,"result":"right"}')
        result = await client.send_request("ping")
        assert result == "right"

    @pytest.mark.asyncio
    async def test_skips_notification_ids(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        # Notification-style response (no id) should be skipped
        t.queue_response('{"jsonrpc":"2.0","method":"some_event"}')
        t.queue_response('{"jsonrpc":"2.0","id":1,"result":"ok"}')
        result = await client.send_request("ping")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_send_notification(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        await client.send_notification("notifications/initialized")
        assert len(t.sent) == 1
        parsed = json.loads(t.sent[0])
        assert parsed["method"] == "notifications/initialized"
        assert "id" not in parsed

    @pytest.mark.asyncio
    async def test_initialize_handshake(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        t.queue_response(
            '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}}}}'
        )
        result = await client.initialize()
        assert result["capabilities"]["tools"] == {}
        assert client.server_protocol_version == "2025-03-26"
        assert client.server_capabilities == {"tools": {}}
        # Should have sent a notification after init
        assert any("notifications/initialized" in s for s in t.sent)

    @pytest.mark.asyncio
    async def test_ping(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        t.queue_response('{"jsonrpc":"2.0","id":1,"result":"pong"}')
        result = await client.ping()
        assert result == "pong"

    @pytest.mark.asyncio
    async def test_list_tools(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        t.queue_response(
            '{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"tool1"}]}}'
        )
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "tool1"

    @pytest.mark.asyncio
    async def test_call_tool(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        t.queue_response(
            '{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"done"}]}}'
        )
        result = await client.call_tool("my_tool", {"arg": "val"})
        assert result["content"][0]["text"] == "done"

    @pytest.mark.asyncio
    async def test_close(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        await client.close()
        assert t.is_closed

    @pytest.mark.asyncio
    async def test_set_logging_level(self, mock_transport: Any) -> None:
        t = mock_transport
        client = McpClient(t)
        await client.set_logging_level("debug")
        assert any("logging/setLevel" in s for s in t.sent)
