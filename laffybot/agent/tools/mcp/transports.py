"""Transport layer for MCP — Stdio, SSE, and Streamable HTTP."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import signal
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

import httpx
import httpx_sse
from loguru import logger

_ENV_WHITELIST = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL", "TMPDIR"}


class TransportError(Exception):
    """Transport-level error (connection failed, process died, etc.)."""


class Transport(ABC):
    """Abstract transport — connect, send/receive JSON strings, close."""

    on_disconnect: Callable[[], Awaitable[None]] | None = None

    async def _call_on_disconnect(self) -> None:
        """Safely invoke the on_disconnect callback if set."""
        if self.on_disconnect is not None:
            try:
                await self.on_disconnect()
            except Exception as exc:
                logger.error("Disconnect callback failed: {}", exc)

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def send(self, message: str) -> None: ...

    @abstractmethod
    async def receive(self) -> str: ...

    @abstractmethod
    async def close(self) -> None: ...


# ── Stdio Transport ──────────────────────────────────────────────────────


def _filter_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key not in _ENV_WHITELIST:
            del env[key]
    if extra_env:
        env.update(extra_env)
    return env


def _win_cmd_wrap(command: str, args: list[str]) -> tuple[str, list[str]]:
    """Wrap via cmd.exe on Windows for npx/bunx/.cmd/.bat scripts."""
    if not args:
        return command, args
    if command.endswith((".cmd", ".bat")) or command in ("npx", "bunx"):
        return "cmd.exe", ["/d", "/c", command, *args]
    return command, args


def _parse_sse_events(text: str) -> list[tuple[str, str]]:
    """Parse raw SSE text into (event_type, data) pairs.

    Handles ``event:``, ``data:`` line types and blank-line delimiters,
    including multi-line ``data:`` fields and trailing events without a
    terminating blank line.
    """
    events: list[tuple[str, str]] = []
    event_type = ""
    data_lines: list[str] = []
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: "):
            data_lines.append(line[6:])
        elif line == "" and data_lines:
            events.append((event_type, "\n".join(data_lines)))
            event_type = ""
            data_lines = []
    if data_lines:
        events.append((event_type, "\n".join(data_lines)))
    return events


class StdioTransport(Transport):
    """Subprocess transport — JSON lines over stdin/stdout."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        stderr_log_path: str | None = None,
    ) -> None:
        self._command = command
        self._args = args or []
        self._extra_env = env
        self._stderr_log_path = stderr_log_path or "mcp_stdio_err.log"
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None

    async def connect(self) -> None:
        cmd, args = _win_cmd_wrap(self._command, self._args)
        filtered = _filter_env(self._extra_env)
        stderr_file = open(self._stderr_log_path, "ab")  # noqa: SIM115
        self._process = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr_file,
            env=filtered,
        )
        self._reader = self._process.stdout

    async def send(self, message: str) -> None:
        if self._process is None or self._process.stdin is None:
            raise TransportError("Stdio transport not connected")
        self._process.stdin.write((message + "\n").encode())
        await self._process.stdin.drain()

    async def receive(self) -> str:
        if self._reader is None:
            raise TransportError("Stdio transport not connected")
        for _ in range(100):
            line = await self._reader.readline()
            if not line:
                await self._call_on_disconnect()
                raise TransportError(
                    "Stdio process closed stdout without sending a valid JSON-RPC message. "
                    "Check stderr log for details."
                )
            decoded = line.decode().rstrip("\n\r")
            if not decoded:
                continue
            try:
                json.loads(decoded)
            except json.JSONDecodeError:
                logger.debug("Skipping non-JSON stdout line: {}", decoded[:200])
                continue
            return decoded
        raise TransportError("Stdio process sent too many non-JSON lines; giving up")

    async def close(self) -> None:
        if self._process is None:
            return
        try:
            if self._process.returncode is None:
                if platform.system() == "Windows":
                    self._process.kill()
                else:
                    self._process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except TimeoutError:
                    self._process.kill()
                    await self._process.wait()
        except ProcessLookupError:
            pass
        self._process = None
        self._reader = None
        await self._call_on_disconnect()


# ── SSE Transport ────────────────────────────────────────────────────────


class SseTransport(Transport):
    """Server-Sent Events transport — bidirectional over HTTP.

    Server → client via SSE stream; client → server via HTTP POST.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        http_timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._http_timeout = http_timeout
        self._client: httpx.AsyncClient | None = None
        self._post_url: str | None = None
        self._response: httpx.Response | None = None
        self._lines: asyncio.Queue[str | None] = asyncio.Queue()
        self._connected = False
        self._read_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(timeout=self._http_timeout)
        merged_headers = {**self._headers, "Accept": "text/event-stream"}
        self._response = await self._client.get(self._url, headers=merged_headers)
        if self._response.status_code >= 400:
            raise TransportError(
                f"SSE connection failed: HTTP {self._response.status_code} for GET {self._url}"
            )
        self._read_task = asyncio.create_task(self._read_sse())
        self._connected = True

    async def send(self, message: str) -> None:
        if not self._connected or self._client is None:
            raise TransportError("SSE transport not connected")
        post_url = self._post_url or self._url
        resp = await self._client.post(
            post_url,
            content=message,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **self._headers,
            },
        )
        if resp.status_code >= 400:
            raise TransportError(
                f"SSE POST failed: HTTP {resp.status_code} for POST {post_url}: {resp.text[:200]}"
            )
        # Some MCP servers respond directly in the POST body (especially
        # for the initial ``initialize`` handshake).  Queue the response
        # body if it contains a JSON-RPC payload.
        body = resp.text.strip()
        if body:
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict) and "jsonrpc" in parsed:
                    await self._lines.put(body)
                    return
            except json.JSONDecodeError:
                pass
            # If the body looks like SSE text, try to extract JSON-RPC data
            for evt_type, data in _parse_sse_events(body):
                if evt_type in ("message", "jsonrpc") and data:
                    try:
                        json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    await self._lines.put(data)
                    return

    async def receive(self) -> str:
        line = await self._lines.get()
        if line is None:
            raise TransportError("SSE stream ended")
        return line

    async def close(self) -> None:
        self._connected = False
        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception):
                pass
            self._read_task = None
        if self._response is not None:
            await self._response.aclose()
            self._response = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await self._call_on_disconnect()

    async def _read_sse(self) -> None:
        try:
            async for sse in httpx_sse.EventSource(self._response).aiter_sse():  # type: ignore[arg-type]
                if sse.event == "endpoint":
                    self._post_url = sse.data.strip()
                elif sse.event in ("message", "jsonrpc"):
                    try:
                        json.loads(sse.data)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Ignoring non-JSON SSE event: {}", sse.data[:200]
                        )
                        continue
                    await self._lines.put(sse.data)
        except Exception as exc:
            if self._connected:
                logger.error("SSE read task error: {}", exc)
        finally:
            await self._call_on_disconnect()
            await self._lines.put(None)  # signal end


# ── Streamable HTTP Transport ────────────────────────────────────────────


class StreamableHttpTransport(Transport):
    """Streamable HTTP transport — POST requests with SSE-style responses."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        http_timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._http_timeout = http_timeout
        self._client: httpx.AsyncClient | None = None
        self._connected = False
        self._responses: asyncio.Queue[str | None] = asyncio.Queue()

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(timeout=self._http_timeout)
        self._connected = True

    async def send(self, message: str) -> None:
        if not self._connected or self._client is None:
            raise TransportError("Streamable HTTP transport not connected")
        resp = await self._client.post(
            self._url,
            content=message,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                **self._headers,
            },
        )
        if resp.status_code >= 400:
            raise TransportError(
                f"HTTP {resp.status_code} for POST {self._url}: {resp.text[:200]}"
            )
        body = resp.text
        # Notification responses may have an empty body — nothing to queue
        if not body.strip():
            return
        # Parse SSE events looking for JSON-RPC data events
        found = False
        for evt_type, data in _parse_sse_events(body):
            if evt_type in ("message", "jsonrpc") and data:
                await self._responses.put(data)
                found = True
        # If no SSE format, treat entire body as response
        if not found:
            await self._responses.put(body)

    async def receive(self) -> str:
        resp = await self._responses.get()
        if resp is None:
            raise TransportError("Stream ended")
        return resp

    async def close(self) -> None:
        self._connected = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await self._call_on_disconnect()
        await self._responses.put(None)
