"""Tests for MCP transports — Stdio, SSE, StreamableHttp."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import respx
from httpx import Response

from laffybot_agent_runtime.tools.mcp.transports import (
    SseTransport,
    StdioTransport,
    StreamableHttpTransport,
    TransportError,
    _parse_sse_events,
)


class TestParseSSEEvents:
    def test_single_event(self) -> None:
        events = _parse_sse_events("data: hello\n\n")
        assert events == [("", "hello")]

    def test_event_with_type(self) -> None:
        events = _parse_sse_events("event: message\ndata: hello\n\n")
        assert events == [("message", "hello")]

    def test_multiple_events(self) -> None:
        sse = "data: first\n\ndata: second\n\n"
        events = _parse_sse_events(sse)
        assert len(events) == 2
        assert events[0][1] == "first"

    def test_multiline_data(self) -> None:
        sse = "data: line1\ndata: line2\n\n"
        events = _parse_sse_events(sse)
        assert events[0][1] == "line1\nline2"

    def test_no_trailing_blank_line(self) -> None:
        events = _parse_sse_events("data: hello")
        assert events == [("", "hello")]

    def test_carriage_return_normalized(self) -> None:
        events = _parse_sse_events("data: hello\r\n\r\n")
        assert events == [("", "hello")]

    def test_empty_input(self) -> None:
        assert _parse_sse_events("") == []


class TestStdioTransport:
    @pytest.mark.asyncio
    async def test_send_receive_roundtrip(self) -> None:
        transport = StdioTransport(command="cat")
        await transport.connect()
        msg = json.dumps({"jsonrpc": "2.0", "method": "ping"})
        await transport.send(msg)
        response = await transport.receive()
        assert response == msg  # cat echoes stdin
        await transport.close()

    @pytest.mark.asyncio
    async def test_close_twice(self) -> None:
        transport = StdioTransport(command="echo", args=["{}"])
        await transport.connect()
        await transport.close()
        await transport.close()  # second close should not raise

    @pytest.mark.asyncio
    async def test_send_before_connect_raises(self) -> None:
        transport = StdioTransport(command="echo")
        with pytest.raises(TransportError):
            await transport.send("test")


class TestSseTransport:
    @pytest.mark.asyncio
    async def test_close(self) -> None:
        async def sse_stream() -> Any:
            yield b"event: endpoint\ndata: http://test.local/msg\n\n"
            await asyncio.Event().wait()

        with respx.mock:
            respx.get("http://test.local/sse").mock(
                return_value=Response(
                    status_code=200,
                    headers={"Content-Type": "text/event-stream"},
                    content=sse_stream(),
                )
            )
            transport = SseTransport(url="http://test.local/sse", http_timeout=5)
            await transport.connect()
            await transport.close()
            await transport.close()

    @pytest.mark.asyncio
    async def test_http_error_on_connect(self) -> None:
        with respx.mock:
            respx.get("http://test.local/bad").respond(status_code=404)
            transport = SseTransport(url="http://test.local/bad", http_timeout=5)
            with pytest.raises(TransportError, match="404"):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_endpoint_timeout(self) -> None:
        with respx.mock:
            respx.get("http://test.local/sse").respond(
                status_code=200,
                content=b"data: hello\n\n",
            )
            transport = SseTransport(url="http://test.local/sse", http_timeout=0.5)
            with pytest.raises(TransportError, match="timed out|no endpoint"):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_connect_sets_up_endpoint(self) -> None:
        async def sse_stream() -> Any:
            yield b"event: endpoint\ndata: http://test.local/message\n\n"
            await asyncio.Event().wait()

        with respx.mock:
            respx.get("http://test.local/sse").mock(
                return_value=Response(
                    status_code=200,
                    headers={"Content-Type": "text/event-stream"},
                    content=sse_stream(),
                )
            )
            transport = SseTransport(url="http://test.local/sse", http_timeout=5)
            await transport.connect()

            respx.post("http://test.local/message").respond(
                status_code=200,
                json={"jsonrpc": "2.0", "id": 1, "result": "ok"},
            )
            await transport.send(json.dumps({"jsonrpc": "2.0", "method": "ping"}))
            response = await transport.receive()
            parsed = json.loads(response)
            assert parsed["result"] == "ok"
            await transport.close()
            # Closing twice should not raise
            await transport.close()


class TestStreamableHttpTransport:
    @pytest.mark.asyncio
    async def test_send_and_receive(self) -> None:
        with respx.mock:
            respx.post("http://test.local/rpc").respond(
                status_code=200,
                json={"jsonrpc": "2.0", "id": 1, "result": "pong"},
            )
            transport = StreamableHttpTransport(
                url="http://test.local/rpc", http_timeout=5
            )
            await transport.connect()
            await transport.send(json.dumps({"jsonrpc": "2.0", "method": "ping"}))
            response = await transport.receive()
            parsed = json.loads(response)
            assert parsed["result"] == "pong"
            await transport.close()

    @pytest.mark.asyncio
    async def test_http_error(self) -> None:
        with respx.mock:
            respx.post("http://test.local/rpc").respond(status_code=500)
            transport = StreamableHttpTransport(
                url="http://test.local/rpc", http_timeout=5
            )
            await transport.connect()
            with pytest.raises(TransportError, match="500"):
                await transport.send("test")

    @pytest.mark.asyncio
    async def test_send_before_connect_raises(self) -> None:
        transport = StreamableHttpTransport(url="http://test.local/rpc")
        with pytest.raises(TransportError):
            await transport.send("test")
