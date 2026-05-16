"""Session domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

SessionStatus = Literal["idle", "busy", "error"]
MessageRole = Literal["user", "assistant", "system", "tool"]
SessionMessage = dict[str, Any]


@dataclass(slots=True)
class SessionInfo:
    """Metadata for a persisted session."""

    session_id: str
    provider_id: str
    model_name: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    current_request_id: str | None = None
    error_message: str | None = None
    system_prompt: str | None = None
    max_iterations: int = 10
    title: str | None = None
    user_message_count: int = 0
    title_updated_at_user_message_count: int = 0
    title_auto_generated: bool = False
    archived_at: datetime | None = None


def validate_status(status: str) -> SessionStatus:
    if status not in {"idle", "busy", "error"}:
        raise ValueError(f"Invalid session status: {status}")
    return cast(SessionStatus, status)


def validate_role(role: str) -> MessageRole:
    if role not in {"user", "assistant", "system", "tool"}:
        raise ValueError(f"Invalid message role: {role}")
    return cast(MessageRole, role)
