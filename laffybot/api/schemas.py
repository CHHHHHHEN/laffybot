"""Pydantic schemas for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SessionCreateRequest(BaseModel):
    model: str
    system_prompt: str | None = None
    max_iterations: int = Field(default=10, ge=1)


class MessageCreateRequest(BaseModel):
    content: str


class SessionCancelRequest(BaseModel):
    reason: str | None = None


class SessionBase(BaseModel):
    session_id: str
    model: str
    status: str
    created_at: datetime


class SessionResponse(SessionBase):
    pass


class SessionDetailResponse(SessionBase):
    message_count: int
    current_request_id: str | None = None


class SessionListItem(SessionBase):
    message_count: int


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: datetime
    metadata: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageResponse]


class SessionCancelResponse(BaseModel):
    status: str = "cancelled"
    session_id: str
    request_id: str


class SessionDeleteResponse(BaseModel):
    status: str = "deleted"
    session_id: str


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, str]
