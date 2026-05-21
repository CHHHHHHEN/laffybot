"""Shared test fixtures for laffybot-agent-runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from laffybot_agent_runtime.config import ContextConfig
from laffybot_agent_runtime.providers.base import BaseProvider
from laffybot_agent_runtime.providers.config import ProviderConfig
from laffybot_agent_runtime.providers.types import (
    ErrorLLMResponse,
    StreamChunk,
    SuccessLLMResponse,
)
from laffybot_agent_runtime.tools.base import Tool
from laffybot_agent_runtime.tools.file_state import FileStates
from laffybot_agent_runtime.tools.mcp.manager import MCPServerConfig
from laffybot_agent_runtime.tools.mcp.transports import Transport, TransportError
from laffybot_agent_runtime.tools.registry import ToolRegistry

# ── Mock implementations ─────────────────────────────────────────────────


class _MockTool(Tool):
    """Controllable Tool subclass for testing.

    Pass custom name, description, execute function via constructor.
    Default execute returns ``f"executed with {kwargs}"``.
    """

    def __init__(
        self,
        name: str = "mock_tool",
        description: str = "A mock tool for testing",
        kind: str = "builtin",
        execute_fn: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        self._name = name
        self._desc = description
        self.kind = kind  # type: ignore[assignment]
        self._execute_fn = execute_fn

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._desc

    async def execute(self, **kwargs: Any) -> Any:
        if self._execute_fn is not None:
            return await self._execute_fn(**kwargs)
        return f"executed with {kwargs}"


class _MockProvider(BaseProvider):
    """Controllable BaseProvider mock for testing.

    Usage:

        provider = _MockProvider()
        provider.set_chat_completion_response(SuccessLLMResponse(content="hi"))
        provider.set_chat_completion_error("rate_limit", "too many")
        provider.set_stream_chunks([StreamChunk(content="hello")])

    Attributes:
        call_history: Each entry has keys: method, messages, model, tools,
                      temperature, max_tokens.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(
            config
            or ProviderConfig(
                provider_id="mock",
                name="mock",
                api_key="",
                base_url="http://mock",
            )
        )
        self._chat_response: SuccessLLMResponse | ErrorLLMResponse | None = None
        self._chat_responses: list[SuccessLLMResponse | ErrorLLMResponse] = []
        self._response_index = 0
        self._stream_chunks: list[StreamChunk] = []
        self._stream_response: SuccessLLMResponse | ErrorLLMResponse | None = None
        self.call_history: list[dict[str, Any]] = []

    def set_chat_completion_response(
        self, response: SuccessLLMResponse | ErrorLLMResponse
    ) -> None:
        self._chat_response = response

    def set_chat_completion_responses(
        self, responses: list[SuccessLLMResponse | ErrorLLMResponse]
    ) -> None:
        """Set a sequence of responses, one per iteration."""
        self._chat_responses = list(responses)
        self._response_index = 0

    def set_chat_completion_error(
        self, error_kind: str = "internal", message: str = "mock error"
    ) -> None:
        self._chat_response = ErrorLLMResponse(
            finish_reason="error",
            error_kind=error_kind,
            error_message=message,
        )

    def set_stream_chunks(
        self,
        chunks: list[StreamChunk],
        final_response: SuccessLLMResponse | ErrorLLMResponse | None = None,
    ) -> None:
        self._stream_chunks = list(chunks)
        self._stream_response = final_response

    def _next_response(self) -> SuccessLLMResponse | ErrorLLMResponse:
        if self._response_index < len(self._chat_responses):
            resp = self._chat_responses[self._response_index]
            self._response_index += 1
            return resp
        if self._chat_response is not None:
            return self._chat_response
        return SuccessLLMResponse(content="hello")

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> SuccessLLMResponse | ErrorLLMResponse:
        self.call_history.append(
            {
                "method": "chat_completion",
                "messages": list(messages),
                "model": model,
                "tools": tools,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self._next_response()

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        on_chunk: Callable[[StreamChunk], Awaitable[None]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> SuccessLLMResponse | ErrorLLMResponse:
        self.call_history.append(
            {
                "method": "chat_completion_stream",
                "messages": list(messages),
                "model": model,
                "tools": tools,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        for chunk in self._stream_chunks:
            await on_chunk(chunk)
        return self._next_response()


class _MockTransport(Transport):
    """Controllable Transport mock for testing.

    Queue responses via ``queue_response()`` before calling ``receive()``.
    Record sent messages in ``.sent``.

    If ``receive()`` is called with an empty queue, it raises ``TransportError``
    after ``receive_timeout`` seconds (default 5) to prevent hanging tests.
    Set ``receive_timeout=0`` to fail instantly on empty queue.
    """

    def __init__(self, receive_timeout: float = 5.0) -> None:
        self._responses: list[str | type[TransportError]] = []
        self.sent: list[str] = []
        self._closed = False
        self._receive_timeout = receive_timeout

    async def connect(self) -> None:
        self._closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def receive(self) -> str:
        if not self._responses:
            import asyncio

            if self._receive_timeout <= 0:
                raise TransportError(
                    "Mock transport receive queue empty. "
                    "Call queue_response() before receive()."
                )
            try:
                await asyncio.wait_for(
                    asyncio.Event().wait(), timeout=self._receive_timeout
                )
            except asyncio.TimeoutError:
                raise TransportError(
                    f"Mock transport receive timed out after {self._receive_timeout}s. "
                    "Did you forget to call queue_response()?"
                )
            raise AssertionError("unreachable")
        item = self._responses.pop(0)
        if item is TransportError:
            raise TransportError("mock disconnection")
        return item

    async def close(self) -> None:
        self._closed = True
        await self._call_on_disconnect()

    def queue_response(self, data: str) -> None:
        self._responses.append(data)

    def queue_disconnect(self) -> None:
        self._responses.append(TransportError)

    @property
    def is_closed(self) -> bool:
        return self._closed


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_tool() -> _MockTool:
    return _MockTool()


@pytest.fixture
def tool_registry(mock_tool: _MockTool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(mock_tool)
    return registry


@pytest.fixture
def context_config() -> ContextConfig:
    return ContextConfig()


@pytest.fixture
def file_states() -> FileStates:
    fs = FileStates()
    fs.clear()
    return fs


@pytest.fixture
def mock_provider() -> _MockProvider:
    return _MockProvider()


@pytest.fixture
def mock_transport() -> _MockTransport:
    return _MockTransport()


@pytest.fixture
def mcp_server_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="test",
        transport_type="stdio",
        command="echo",
        args=["{}"],
    )


@pytest.fixture(autouse=True)
def _silence_loguru() -> Any:
    """Disable loguru during tests to prevent log pollution."""
    from loguru import logger

    logger.disable("laffybot_agent_runtime")
    yield
    logger.enable("laffybot_agent_runtime")
