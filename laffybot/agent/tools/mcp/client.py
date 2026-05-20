"""JSON-RPC 2.0 MCP client — protocol-level session over a Transport."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

MCP_PROTOCOL_VERSION = "2025-03-26"


class McpError(Exception):
    """JSON-RPC error returned by the server."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.data = data
        super().__init__(message)


class McpProtocolError(Exception):
    """Protocol-level error (parse error, invalid response, etc.)."""


def _make_request(method: str, params: dict[str, Any] | None, request_id: int) -> str:
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        body["params"] = params
    return json.dumps(body, ensure_ascii=False)


def _make_notification(method: str, params: dict[str, Any] | None = None) -> str:
    """Build a JSON-RPC 2.0 notification (no ``id`` field)."""
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        body["params"] = params
    return json.dumps(body, ensure_ascii=False)


def _parse_response(data: str) -> dict[str, Any]:
    stripped = data.strip()
    if not stripped:
        raise McpProtocolError(f"Empty response from server (raw={data!r})")
    try:
        msg = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise McpProtocolError(
            f"JSON parse error: {exc} (data={data[:500]!r})"
        ) from exc
    if not isinstance(msg, dict):
        raise McpProtocolError("Response is not a JSON object")
    return msg


class McpClient:
    """MCP protocol client — sends JSON-RPC requests over a Transport.

    All requests are serialised via an internal lock so that request/response
    ID pairing is never ambiguous.
    """

    def __init__(self, transport: Any) -> None:
        self._transport = transport
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._server_capabilities: dict[str, Any] = {}
        self._server_protocol_version: str = ""

    @property
    def server_capabilities(self) -> dict[str, Any]:
        return self._server_capabilities

    @property
    def server_protocol_version(self) -> str:
        return self._server_protocol_version

    async def send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """Send a JSON-RPC 2.0 notification — fire-and-forget, no response."""
        payload = _make_notification(method, params)
        await self._transport.send(payload)

    async def send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Send a JSON-RPC request and await the response."""
        async with self._lock:
            self._request_id += 1
            req_id = self._request_id
            payload = _make_request(method, params, req_id)
            await self._transport.send(payload)
            while True:
                raw = await self._transport.receive()
                msg = _parse_response(raw)
                msg_id = msg.get("id")
                if msg_id is None:
                    continue
                if msg_id != req_id:
                    logger.error(
                        "Response ID {} does not match request ID {}; discarding",
                        msg_id,
                        req_id,
                    )
                    continue
                if "error" in msg:
                    err = msg["error"]
                    raise McpError(
                        code=err.get("code", 0),
                        message=err.get("message", "Unknown error"),
                        data=err.get("data"),
                    )
                result = msg.get("result")
                return result

    async def initialize(self) -> Any:
        """Negotiate protocol version and capabilities."""
        result = await self.send_request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": False},
                    "sampling": {},
                },
                "clientInfo": {
                    "name": "laffybot",
                    "version": "0.1.0",
                },
            },
        )
        self._server_capabilities = result.get("capabilities", {})
        self._server_protocol_version = result.get("protocolVersion", "")
        await self.send_notification("notifications/initialized")
        return result

    async def ping(self) -> Any:
        """Heartbeat — keep-alive."""
        return await self.send_request("ping")

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the server."""
        result = await self.send_request("tools/list")
        return result.get("tools", []) if isinstance(result, dict) else []

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call a tool and return the result."""
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        result = await self.send_request("tools/call", params)
        return result if isinstance(result, dict) else {}

    async def list_resources(self) -> list[dict[str, Any]]:
        """List available resources."""
        result = await self.send_request("resources/list")
        return result.get("resources", []) if isinstance(result, dict) else []

    async def read_resource(self, uri: str) -> list[dict[str, Any]]:
        """Read a resource by URI."""
        result = await self.send_request("resources/read", {"uri": uri})
        return result.get("contents", []) if isinstance(result, dict) else []

    async def list_prompts(self) -> list[dict[str, Any]]:
        """List available prompts."""
        result = await self.send_request("prompts/list")
        return result.get("prompts", []) if isinstance(result, dict) else []

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Get a prompt by name."""
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        result = await self.send_request("prompts/get", params)
        return result if isinstance(result, dict) else {}

    async def set_logging_level(self, level: str) -> None:
        """Set the server's logging level (notification — fire-and-forget)."""
        await self.send_notification("logging/setLevel", {"level": level})

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()
