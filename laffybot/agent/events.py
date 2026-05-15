"""SSE event types for streaming agent execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

# Event type literals
EventType = Literal[
    "session_start",
    "content",
    "reasoning",
    "tool_call",
    "tool_result",
    "done",
    "error",
    "cancelled",
    "ping",
    "title_update",
]

StopReason = Literal["completed", "max_iterations", "error", "cancelled"]


@dataclass(slots=True)
class SSEEvent:
    """Base structure for all SSE events."""

    type: EventType

    # session_start fields
    session_id: str | None = None
    request_id: str | None = None

    # content/reasoning fields
    text: str | None = None

    # tool_call fields
    tool_call_id: str | None = None
    name: str | None = None
    arguments: dict[str, Any] | None = None
    timeout_ms: int | None = None

    # tool_result fields
    result: Any = None
    success: bool | None = None
    duration_ms: int | None = None
    error_message: str | None = None

    # done fields
    stop_reason: StopReason | None = None
    usage: dict[str, int] | None = None
    tools_used: list[str] | None = None

    # error fields
    error: dict[str, Any] | None = None

    # cancelled fields
    reason: str | None = None

    # ping fields
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for JSON serialization."""
        result: dict[str, Any] = {"type": self.type}

        if self.type == "session_start":
            if self.session_id is not None:
                result["session_id"] = self.session_id
            if self.request_id is not None:
                result["request_id"] = self.request_id

        elif self.type == "content":
            result["text"] = self.text or ""

        elif self.type == "reasoning":
            result["text"] = self.text or ""

        elif self.type == "tool_call":
            result["tool_call_id"] = self.tool_call_id
            result["name"] = self.name
            result["arguments"] = self.arguments or {}
            if self.timeout_ms is not None:
                result["timeout_ms"] = self.timeout_ms

        elif self.type == "tool_result":
            result["tool_call_id"] = self.tool_call_id
            result["name"] = self.name
            result["result"] = self.result
            result["success"] = self.success
            if self.duration_ms is not None:
                result["duration_ms"] = self.duration_ms
            if self.error_message is not None:
                result["error_message"] = self.error_message

        elif self.type == "done":
            result["stop_reason"] = self.stop_reason
            if self.usage is not None:
                result["usage"] = self.usage
            if self.tools_used is not None:
                result["tools_used"] = self.tools_used

        elif self.type == "error":
            result["error"] = self.error

        elif self.type == "cancelled":
            result["reason"] = self.reason

        elif self.type == "ping":
            result["timestamp"] = self.timestamp

        elif self.type == "title_update":
            result["session_id"] = self.session_id
            result["title"] = self.text

        return result

    def to_sse(self) -> str:
        """Serialize event to SSE format.

        Returns:
            SSE-formatted string: "event: message\\ndata: <json>\\n\\n"
        """
        data = json.dumps(self.to_dict(), ensure_ascii=False)
        return f"event: message\ndata: {data}\n\n"


# Factory functions for creating events


def event_session_start(session_id: str, request_id: str | None = None) -> SSEEvent:
    """Create a session_start event."""
    return SSEEvent(type="session_start", session_id=session_id, request_id=request_id)


def event_content(text: str) -> SSEEvent:
    """Create a content event with text fragment."""
    return SSEEvent(type="content", text=text)


def event_reasoning(text: str) -> SSEEvent:
    """Create a reasoning event with thinking fragment."""
    return SSEEvent(type="reasoning", text=text)


def event_tool_call(
    tool_call_id: str,
    name: str,
    arguments: dict[str, Any],
    timeout_ms: int | None = None,
) -> SSEEvent:
    """Create a tool_call event."""
    return SSEEvent(
        type="tool_call",
        tool_call_id=tool_call_id,
        name=name,
        arguments=arguments,
        timeout_ms=timeout_ms,
    )


def event_tool_result(
    tool_call_id: str,
    name: str,
    result: Any,
    success: bool,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> SSEEvent:
    """Create a tool_result event."""
    return SSEEvent(
        type="tool_result",
        tool_call_id=tool_call_id,
        name=name,
        result=result,
        success=success,
        duration_ms=duration_ms,
        error_message=error_message,
    )


def event_done(
    stop_reason: StopReason,
    usage: dict[str, int] | None = None,
    tools_used: list[str] | None = None,
) -> SSEEvent:
    """Create a done event."""
    return SSEEvent(
        type="done",
        stop_reason=stop_reason,
        usage=usage,
        tools_used=tools_used,
    )


def event_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> SSEEvent:
    """Create an error event."""
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error_obj["details"] = details
    return SSEEvent(type="error", error=error_obj)


def event_cancelled(reason: str | None = None) -> SSEEvent:
    """Create a cancelled event."""
    return SSEEvent(type="cancelled", reason=reason)


def event_ping(timestamp: str | None = None) -> SSEEvent:
    """Create a ping (heartbeat) event."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return SSEEvent(type="ping", timestamp=timestamp)


def event_title_update(session_id: str, title: str) -> SSEEvent:
    """Create a title_update event for global event bus.

    Args:
        session_id: The session whose title was updated
        title: The new title value

    Returns:
        SSEEvent: A title_update event
    """
    return SSEEvent(type="title_update", session_id=session_id, text=title)


# Error code constants

ERROR_LLM = "LLM_ERROR"
ERROR_TOOL = "TOOL_ERROR"
ERROR_STREAM = "STREAM_ERROR"
ERROR_INTERNAL = "INTERNAL_ERROR"
ERROR_CANCELLED = "CANCELLED"
