"""Tests for SSEEvent serialization and factory functions."""

from __future__ import annotations

import json

import pytest

from laffybot_agent_runtime.events import (
    ERROR_CANCELLED,
    ERROR_INTERNAL,
    ERROR_LLM,
    ERROR_STREAM,
    ERROR_TOOL,
    SSEEvent,
    event_cancelled,
    event_content,
    event_done,
    event_error,
    event_iteration_boundary,
    event_ping,
    event_reasoning,
    event_session_start,
    event_title_update,
    event_tool_call,
    event_tool_result,
)


class TestSSEEventToDict:
    """SSEEvent.to_dict() per type."""

    def test_session_start_with_ids(self) -> None:
        e = SSEEvent(type="session_start", session_id="sid1", request_id="req1")
        d = e.to_dict()
        assert d == {
            "type": "session_start",
            "session_id": "sid1",
            "request_id": "req1",
        }

    def test_session_start_without_request_id(self) -> None:
        e = SSEEvent(type="session_start", session_id="sid1")
        d = e.to_dict()
        assert d == {"type": "session_start", "session_id": "sid1"}

    def test_content(self) -> None:
        e = SSEEvent(type="content", text="hello")
        d = e.to_dict()
        assert d == {"type": "content", "text": "hello"}

    def test_content_empty_text(self) -> None:
        e = SSEEvent(type="content", text="")
        d = e.to_dict()
        assert d == {"type": "content", "text": ""}

    def test_content_none_text(self) -> None:
        e = SSEEvent(type="content", text=None)
        d = e.to_dict()
        assert d == {"type": "content", "text": ""}

    def test_reasoning(self) -> None:
        e = SSEEvent(type="reasoning", text="thinking...")
        d = e.to_dict()
        assert d == {"type": "reasoning", "text": "thinking..."}

    def test_tool_call_with_timeout(self) -> None:
        e = SSEEvent(
            type="tool_call",
            tool_call_id="tc1",
            name="read_file",
            arguments={"path": "/tmp"},
            timeout_ms=5000,
        )
        d = e.to_dict()
        assert d["type"] == "tool_call"
        assert d["tool_call_id"] == "tc1"
        assert d["name"] == "read_file"
        assert d["arguments"] == {"path": "/tmp"}
        assert d["timeout_ms"] == 5000

    def test_tool_call_without_timeout(self) -> None:
        e = SSEEvent(
            type="tool_call",
            tool_call_id="tc1",
            name="read_file",
            arguments={},
        )
        d = e.to_dict()
        assert "timeout_ms" not in d

    def test_tool_result_success(self) -> None:
        e = SSEEvent(
            type="tool_result",
            tool_call_id="tc1",
            name="read_file",
            result="file content",
            success=True,
            duration_ms=10,
        )
        d = e.to_dict()
        assert d["type"] == "tool_result"
        assert d["result"] == "file content"
        assert d["success"] is True
        assert d["duration_ms"] == 10

    def test_tool_result_error(self) -> None:
        e = SSEEvent(
            type="tool_result",
            tool_call_id="tc1",
            name="read_file",
            result="Error: not found",
            success=False,
            error_message="not found",
        )
        d = e.to_dict()
        assert d["success"] is False
        assert d["error_message"] == "not found"

    def test_tool_result_without_duration(self) -> None:
        e = SSEEvent(
            type="tool_result",
            tool_call_id="tc1",
            name="read_file",
            result="ok",
            success=True,
        )
        d = e.to_dict()
        assert "duration_ms" not in d
        assert "error_message" not in d

    def test_done_completed(self) -> None:
        e = SSEEvent(type="done", stop_reason="completed")
        d = e.to_dict()
        assert d["stop_reason"] == "completed"

    @pytest.mark.parametrize(
        "reason", ["completed", "max_iterations", "error", "cancelled"]
    )
    def test_done_all_stop_reasons(self, reason: str) -> None:
        e = SSEEvent(type="done", stop_reason=reason)  # type: ignore[arg-type]
        d = e.to_dict()
        assert d["stop_reason"] == reason

    def test_done_with_usage_and_tools(self) -> None:
        e = SSEEvent(
            type="done",
            stop_reason="completed",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            tools_used=["read_file"],
        )
        d = e.to_dict()
        assert d["usage"] == {"prompt_tokens": 10, "completion_tokens": 20}
        assert d["tools_used"] == ["read_file"]

    def test_done_without_optional_fields(self) -> None:
        e = SSEEvent(type="done", stop_reason="completed")
        d = e.to_dict()
        assert "usage" not in d
        assert "tools_used" not in d

    def test_error_with_details(self) -> None:
        e = SSEEvent(
            type="error",
            error={
                "type": "provider_error",
                "error_code": "LLM_ERROR",
                "message": "fail",
                "recoverable": True,
                "details": {"status": 429},
            },
        )
        d = e.to_dict()
        assert d["type"] == "error"
        assert d["error_type"] == "provider_error"
        assert d["error_code"] == "LLM_ERROR"
        assert d["message"] == "fail"
        assert d["recoverable"] is True
        assert d["details"] == {"status": 429}

    def test_error_without_details(self) -> None:
        e = SSEEvent(
            type="error",
            error={
                "type": "internal_error",
                "error_code": "TOOL_ERROR",
                "message": "fail",
                "recoverable": False,
            },
        )
        d = e.to_dict()
        assert d["type"] == "error"
        assert d["error_type"] == "internal_error"
        assert d["error_code"] == "TOOL_ERROR"
        assert d["message"] == "fail"
        assert d["recoverable"] is False
        assert d["details"] is None

    def test_cancelled_with_reason(self) -> None:
        e = SSEEvent(type="cancelled", reason="user cancelled")
        d = e.to_dict()
        assert d == {"type": "cancelled", "reason": "user cancelled"}

    def test_cancelled_without_reason(self) -> None:
        e = SSEEvent(type="cancelled")
        d = e.to_dict()
        assert d == {"type": "cancelled", "reason": None}

    def test_iteration_boundary(self) -> None:
        e = SSEEvent(type="iteration_boundary", iteration=3)
        d = e.to_dict()
        assert d == {"type": "iteration_boundary", "iteration": 3}

    def test_ping_with_timestamp(self) -> None:
        e = SSEEvent(type="ping", timestamp="2025-01-01T00:00:00Z")
        d = e.to_dict()
        assert d == {"type": "ping", "timestamp": "2025-01-01T00:00:00Z"}

    def test_ping_null_timestamp(self) -> None:
        e = SSEEvent(type="ping")
        d = e.to_dict()
        # timestamp is None when not set — factory function handles generation
        assert d["type"] == "ping"
        assert d["timestamp"] is None

    def test_title_update(self) -> None:
        e = SSEEvent(type="title_update", session_id="sid1", text="New Title")
        d = e.to_dict()
        assert d == {"type": "title_update", "session_id": "sid1", "title": "New Title"}


class TestToSSE:
    """SSEEvent.to_sse() serialization format."""

    def test_format(self) -> None:
        e = SSEEvent(type="content", text="hello")
        sse = e.to_sse()
        assert sse.startswith("event: message\ndata: ")
        assert sse.endswith("\n\n")
        # Parse embedded JSON
        data_str = sse[len("event: message\ndata: ") :].rstrip("\n\n")
        parsed = json.loads(data_str)
        assert parsed == {"type": "content", "text": "hello"}

    def test_unicode_not_escaped(self) -> None:
        e = SSEEvent(type="content", text="你好")
        sse = e.to_sse()
        assert "\\u" not in sse
        assert "你好" in sse

    def test_error_to_sse_event_type(self) -> None:
        e = SSEEvent(
            type="error",
            error={
                "type": "internal_error",
                "error_code": "ERR",
                "message": "fail",
                "recoverable": False,
                "details": {"nested": {"key": "val"}},
            },
        )
        sse = e.to_sse()
        assert sse.startswith("event: error\ndata: ")
        assert sse.endswith("\n\n")
        parsed = json.loads(sse[len("event: error\ndata: ") :].rstrip("\n\n"))
        assert parsed["error_type"] == "internal_error"
        assert parsed["details"]["nested"]["key"] == "val"


class TestFactoryFunctions:
    """Factory functions return correctly typed SSEEvent."""

    def test_event_session_start(self) -> None:
        e = event_session_start("sid1", "req1")
        assert e.type == "session_start"
        assert e.session_id == "sid1"
        assert e.request_id == "req1"

    def test_event_session_start_no_request_id(self) -> None:
        e = event_session_start("sid1")
        assert e.request_id is None

    def test_event_content(self) -> None:
        e = event_content("hello")
        assert e.type == "content"
        assert e.text == "hello"

    def test_event_reasoning(self) -> None:
        e = event_reasoning("thinking")
        assert e.type == "reasoning"
        assert e.text == "thinking"

    def test_event_tool_call(self) -> None:
        e = event_tool_call("tc1", "read_file", {"path": "/tmp"}, timeout_ms=5000)
        assert e.type == "tool_call"
        assert e.tool_call_id == "tc1"
        assert e.arguments == {"path": "/tmp"}
        assert e.timeout_ms == 5000

    def test_event_tool_call_no_timeout(self) -> None:
        e = event_tool_call("tc1", "read_file", {})
        assert e.timeout_ms is None

    def test_event_tool_result_success(self) -> None:
        e = event_tool_result(
            "tc1", "read_file", "content", success=True, duration_ms=10
        )
        assert e.success is True
        assert e.duration_ms == 10
        assert e.error_message is None

    def test_event_tool_result_error(self) -> None:
        e = event_tool_result(
            "tc1", "read_file", "Error: fail", success=False, error_message="fail"
        )
        assert e.success is False
        assert e.error_message == "fail"

    def test_event_done(self) -> None:
        e = event_done("completed", usage={"p": 1}, tools_used=["t"])
        assert e.stop_reason == "completed"
        assert e.usage == {"p": 1}
        assert e.tools_used == ["t"]

    def test_event_done_minimal(self) -> None:
        e = event_done("completed")
        assert e.usage is None
        assert e.tools_used is None

    def test_event_error(self) -> None:
        e = event_error("LLM_ERROR", "fail")
        assert e.error == {
            "type": "internal_error",
            "message": "fail",
            "error_code": "LLM_ERROR",
            "recoverable": False,
            "details": None,
        }

    def test_event_error_with_details(self) -> None:
        e = event_error("LLM_ERROR", "fail", {"status": 429})
        assert e.error == {
            "type": "internal_error",
            "message": "fail",
            "error_code": "LLM_ERROR",
            "recoverable": False,
            "details": {"status": 429},
        }

    def test_event_iteration_boundary(self) -> None:
        e = event_iteration_boundary(3)
        assert e.type == "iteration_boundary"
        assert e.iteration == 3

    def test_event_cancelled(self) -> None:
        e = event_cancelled("timeout")
        assert e.type == "cancelled"
        assert e.reason == "timeout"

    def test_event_cancelled_no_reason(self) -> None:
        e = event_cancelled()
        assert e.reason is None

    def test_event_ping_no_timestamp_generates_one(self) -> None:
        e = event_ping()
        assert e.type == "ping"
        assert e.timestamp is not None
        assert "T" in e.timestamp  # ISO 8601 format check

    def test_event_ping_with_timestamp(self) -> None:
        e = event_ping("2025-01-01T00:00:00Z")
        assert e.timestamp == "2025-01-01T00:00:00Z"

    def test_event_title_update(self) -> None:
        e = event_title_update("sid1", "New Title")
        assert e.type == "title_update"
        assert e.session_id == "sid1"
        assert e.text == "New Title"


class TestTypeSafety:
    """Field values not matching event type are silently ignored."""

    def test_wrong_field_for_type_silently_ignored(self) -> None:
        e = SSEEvent(type="content", session_id="should_be_ignored")
        d = e.to_dict()
        assert "session_id" not in d
        assert d["text"] == ""

    def test_none_fields_skipped_by_type(self) -> None:
        e = SSEEvent(type="done", stop_reason="completed", usage=None, tools_used=None)
        d = e.to_dict()
        assert "usage" not in d
        assert "tools_used" not in d


class TestErrorConstants:
    """Error code constants are strings with expected values."""

    def test_error_constants(self) -> None:
        assert ERROR_LLM == "LLM_ERROR"
        assert ERROR_TOOL == "TOOL_ERROR"
        assert ERROR_STREAM == "STREAM_ERROR"
        assert ERROR_INTERNAL == "INTERNAL_ERROR"
        assert ERROR_CANCELLED == "CANCELLED"
