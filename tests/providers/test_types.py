"""Tests for provider response types."""

from laffybot.providers.types import (
    ErrorLLMResponse,
    LLMResponse,
    StreamChunk,
    SuccessLLMResponse,
    ToolCallDelta,
    ToolCallRequest,
)


def test_success_llm_response_creation() -> None:
    resp = SuccessLLMResponse(
        content="Hello",
        tool_calls=[ToolCallRequest(id="call_1", name="exec", arguments={"cmd": "ls"})],
        usage={"prompt_tokens": 10, "completion_tokens": 20},
    )
    assert resp.content == "Hello"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "exec"
    assert resp.usage["prompt_tokens"] == 10


def test_error_llm_response_creation() -> None:
    resp = ErrorLLMResponse(
        error_kind="rate_limit",
        error_status_code=429,
        error_should_retry=True,
        error_message="Rate limited",
    )
    assert resp.error_kind == "rate_limit"
    assert resp.error_status_code == 429
    assert resp.error_should_retry is True


def test_llm_response_is_union() -> None:
    success: LLMResponse = SuccessLLMResponse(content="ok")
    error: LLMResponse = ErrorLLMResponse(error_kind="timeout")
    assert isinstance(success, SuccessLLMResponse)
    assert isinstance(error, ErrorLLMResponse)


def test_success_response_defaults() -> None:
    resp = SuccessLLMResponse()
    assert resp.content is None
    assert resp.tool_calls == []
    assert resp.usage == {}


def test_error_response_defaults() -> None:
    resp = ErrorLLMResponse()
    assert resp.error_kind is None
    assert resp.error_status_code is None


def test_tool_call_request_fields() -> None:
    tc = ToolCallRequest(
        id="call_1",
        name="read_file",
        arguments={"path": "/tmp/test.txt"},
        extra_content={"meta": "data"},
    )
    assert tc.id == "call_1"
    assert tc.arguments["path"] == "/tmp/test.txt"


def test_tool_call_delta() -> None:
    delta = ToolCallDelta(index=0, id="call_1", arguments_delta='{"path":')
    assert delta.index == 0
    assert delta.id == "call_1"
    assert delta.arguments_delta == '{"path":'


def test_stream_chunk_content() -> None:
    chunk = StreamChunk(content="Hello", reasoning="thinking...")
    assert chunk.content == "Hello"
    assert chunk.reasoning == "thinking..."


def test_stream_chunk_tool_call() -> None:
    delta = ToolCallDelta(index=0, id="call_1")
    chunk = StreamChunk(tool_call_delta=delta)
    assert chunk.tool_call_delta is not None
    assert chunk.tool_call_delta.id == "call_1"
