"""Pydantic schemas for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SessionCreateRequest(BaseModel):
    max_iterations: int = Field(default=50, ge=1)
    provider_id: str | None = None
    model_name: str | None = None

    @model_validator(mode="after")
    def validate_provider_model(self) -> "SessionCreateRequest":
        if (self.provider_id is None) != (self.model_name is None):
            raise ValueError("provider_id and model_name must be provided together")
        return self


class SystemPromptUpdateRequest(BaseModel):
    system_prompt: str


class MessageCreateRequest(BaseModel):
    content: str


class SessionCancelRequest(BaseModel):
    reason: str | None = None


class SessionBase(BaseModel):
    session_id: str
    provider_id: str
    model_name: str
    status: str
    created_at: datetime
    title: str | None = None
    archived_at: datetime | None = None


class SessionResponse(SessionBase):
    pass


class SessionDetailResponse(SessionBase):
    message_count: int
    current_request_id: str | None = None
    title_auto_generated: bool = False


class SessionListItem(SessionBase):
    message_count: int


class SessionTitleUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


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
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


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


class ProviderCreateRequest(BaseModel):
    name: str
    base_url: str
    api_key: str
    extra_headers: dict[str, str] = Field(default_factory=dict)


class ProviderUpdateRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    extra_headers: dict[str, str] | None = None


class ProviderResponse(BaseModel):
    id: str
    name: str
    base_url: str
    has_api_key: bool
    created_at: datetime


class ProviderDetailResponse(ProviderResponse):
    extra_headers: dict[str, str] = Field(default_factory=dict)


class ModelCreateRequest(BaseModel):
    name: str


class ModelResponse(BaseModel):
    id: str
    provider_id: str
    name: str


class SessionModelUpdateRequest(BaseModel):
    provider_id: str
    model_name: str


class TestResultResponse(BaseModel):
    success: bool
    message: str
    latency_ms: int | None = None


class MemoryResponse(BaseModel):
    memory_id: str
    session_id: str
    content: str
    tags: list[str]
    created_at: str
    updated_at: str
    session_title: str | None = None
    usage_count: int = 0
    last_usage: str | None = None


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int
    limit: int
    offset: int


class MemorySourceResponse(BaseModel):
    session_id: str
    session_title: str | None
    messages: list[MessageResponse]


class ConsolidatedMemoryResponse(BaseModel):
    content: str
    source_memory_ids: list[str]
    last_consolidated_at: str | None
    created_at: str
    updated_at: str


class ConsolidationStatusResponse(BaseModel):
    has_consolidated_memory: bool
    total_raw_memories: int
    consolidated_source_count: int
    unconsolidated_count: int


class SkillsPathResponse(BaseModel):
    path: str | None = None


class SkillsPathUpdateRequest(BaseModel):
    path: str


class SkillItem(BaseModel):
    name: str
    description: str
    enabled: bool
    has_resources: bool


class SkillsListResponse(BaseModel):
    skills: list[SkillItem]
    skills_path: str | None = None


class SkillEnabledUpdateRequest(BaseModel):
    enabled: bool


# ── MCP Server Schemas ───────────────────────────────────────────────────


class MCPServerCreateRequest(BaseModel):
    name: str
    transport_type: str | None = None
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    tool_timeout: int | None = None
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] | None = None
    startup_timeout: int | None = None
    enabled: bool = False


class MCPServerUpdateRequest(BaseModel):
    name: str | None = None
    transport_type: str | None = None
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    tool_timeout: int | None = None
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] | None = None
    startup_timeout: int | None = None
    enabled: bool | None = None


class MCPServerResponse(BaseModel):
    id: str
    name: str
    transport_type: str
    command: str | None = None
    url: str | None = None
    has_env: bool = False
    has_headers: bool = False
    tool_timeout: int | None = None
    enabled_tools: list[str] = ["*"]
    disabled_tools: list[str] = []
    startup_timeout: int = 30
    enabled: bool = False
    connection_status: str = "disconnected"
    tool_count: int = 0
    created_at: datetime


class MCPServerTestResponse(BaseModel):
    success: bool
    message: str
