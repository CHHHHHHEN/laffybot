"""Tests for McpServerManager — lifecycle, startup, routing, shutdown."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from laffybot_agent_runtime.tools.mcp.manager import MCPServerConfig, McpServerManager
from laffybot_agent_runtime.tools.registry import ToolRegistry


def _stdio_config(name: str = "test", **kwargs: Any) -> MCPServerConfig:
    return MCPServerConfig(name=name, transport_type="stdio", command="cat", **kwargs)


_INIT_RESPONSE = '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}}}}'
_TOOLS_RESPONSE = '{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"tool1","description":"A tool","inputSchema":{}}]}}'


class TestConstruction:
    def test_single_server(self) -> None:
        mgr = McpServerManager([_stdio_config()])
        assert len(mgr._clients) == 1
        assert "test" in mgr._clients

    def test_multiple_servers(self) -> None:
        mgr = McpServerManager([_stdio_config("srv1"), _stdio_config("srv2")])
        assert len(mgr._clients) == 2


class TestStart:
    @pytest.mark.asyncio
    async def test_start_single_server(self, tool_registry: ToolRegistry) -> None:
        with patch(
            "laffybot_agent_runtime.tools.mcp.manager.create_transport"
        ) as mock_factory:
            transport = _make_mock_transport(init=True, tools=True)
            mock_factory.return_value = transport

            mgr = McpServerManager([_stdio_config()], tool_registry=tool_registry)
            status = await mgr.start()
            assert "test" in status
            assert "ready" in status["test"]

    @pytest.mark.asyncio
    async def test_start_disabled_server_skipped(
        self, tool_registry: ToolRegistry
    ) -> None:
        with patch(
            "laffybot_agent_runtime.tools.mcp.manager.create_transport"
        ) as mock_factory:
            transport = _make_mock_transport(init=True, tools=True)
            mock_factory.return_value = transport

            cfg = _stdio_config(enabled=False)
            mgr = McpServerManager([cfg], tool_registry=tool_registry)
            status = await mgr.start()
            assert status == {}

    @pytest.mark.asyncio
    async def test_start_failure_isolation(self, tool_registry: ToolRegistry) -> None:
        from laffybot_agent_runtime.tools.mcp.transports import TransportError

        async def _ok_connect() -> None:
            pass

        async def _fail_connect() -> None:
            raise TransportError("connection refused")

        with patch(
            "laffybot_agent_runtime.tools.mcp.manager.create_transport"
        ) as mock_factory:

            def side_effect(config: Any) -> Any:
                t = _make_mock_transport(init=True, tools=True)
                t.connect = _fail_connect if config.name == "bad" else _ok_connect
                return t

            mock_factory.side_effect = side_effect
            mgr = McpServerManager(
                [_stdio_config("good"), _stdio_config("bad")],
                tool_registry=tool_registry,
            )
            status = await mgr.start()
            assert "good" in status
            assert status["bad"] != "ready"


class TestCallTool:
    @pytest.mark.asyncio
    async def test_call_ready_server(self, tool_registry: ToolRegistry) -> None:
        with patch(
            "laffybot_agent_runtime.tools.mcp.manager.create_transport"
        ) as mock_factory:
            transport = _make_mock_transport(init=True, tools=True)
            transport.queue_response(
                '{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"done"}]}}'
            )
            mock_factory.return_value = transport
            mgr = McpServerManager([_stdio_config()], tool_registry=tool_registry)
            await mgr.start()
            result = await mgr.call_tool("test", "tool1", {"arg": "val"})
            assert result["content"][0]["text"] == "done"

    @pytest.mark.asyncio
    async def test_call_unknown_server(self, tool_registry: ToolRegistry) -> None:
        mgr = McpServerManager([_stdio_config()], tool_registry=tool_registry)
        result = await mgr.call_tool("nonexistent", "tool")
        assert result.get("isError") is True


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self, tool_registry: ToolRegistry) -> None:
        with patch(
            "laffybot_agent_runtime.tools.mcp.manager.create_transport"
        ) as mock_factory:
            transport = _make_mock_transport(init=True, tools=True)
            mock_factory.return_value = transport
            mgr = McpServerManager([_stdio_config()], tool_registry=tool_registry)
            await mgr.start()
            await mgr.shutdown()
            assert transport.is_closed


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_get_status(self, tool_registry: ToolRegistry) -> None:
        with patch(
            "laffybot_agent_runtime.tools.mcp.manager.create_transport"
        ) as mock_factory:
            transport = _make_mock_transport(init=True, tools=True)
            mock_factory.return_value = transport
            mgr = McpServerManager([_stdio_config()], tool_registry=tool_registry)
            status = mgr.get_status("test")
            assert status["status"] == "created"
            await mgr.start()
            status = mgr.get_status("test")
            assert status["status"] == "ready"

    def test_get_unknown_server(self) -> None:
        mgr = McpServerManager([_stdio_config()])
        status = mgr.get_status("nonexistent")
        assert status["status"] == "not_found"


def _make_mock_transport(*, init: bool = False, tools: bool = False) -> Any:
    """Create a mock transport pre-configured with JSON-RPC responses."""
    from conftest import _MockTransport

    t = _MockTransport(receive_timeout=5)
    if init:
        t.queue_response(_INIT_RESPONSE)
    if tools:
        t.queue_response(_TOOLS_RESPONSE)
    return t
