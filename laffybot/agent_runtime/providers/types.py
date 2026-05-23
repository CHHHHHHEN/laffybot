from dataclasses import dataclass, field
from typing import Any

ERROR_TIMEOUT = "timeout"
ERROR_CONNECTION = "connection"
ERROR_RATE_LIMIT = "rate_limit"
ERROR_SERVER = "server"

ERROR_INTERNAL = "internal"


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    extra_content: dict[str, Any] | None = None
    provider_specific_fields: dict[str, Any] | None = None


@dataclass
class LLMResponse:
    """Base LLM response."""

    finish_reason: str = "stop"
    reasoning_content: str | None = None


@dataclass
class SuccessLLMResponse(LLMResponse):
    """Successful LLM response with content and/or tool calls."""

    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class ErrorLLMResponse(LLMResponse):
    """Error LLM response from provider."""

    error_kind: str | None = None
    error_status_code: int | None = None
    error_should_retry: bool | None = None
    error_message: str | None = None


# Backwards-compatible type alias
AnyLLMResponse = SuccessLLMResponse | ErrorLLMResponse


@dataclass(slots=True)
class ToolCallDelta:
    """Incremental tool call data from streaming response."""

    index: int
    id: str | None = None
    name: str | None = None
    arguments_delta: str | None = None


@dataclass(slots=True)
class StreamChunk:
    """Streaming chunk data passed to on_chunk callback.

    This replaces the simple str callback to support:
    - Content streaming
    - Reasoning/thinking streaming
    - Tool call delta streaming
    """

    content: str | None = None
    reasoning: str | None = None
    tool_call_delta: ToolCallDelta | None = None
