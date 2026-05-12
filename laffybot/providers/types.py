from dataclasses import dataclass, field
from typing import Any

ERROR_TIMEOUT = "timeout"
ERROR_CONNECTION = "connection"
ERROR_RATE_LIMIT = "rate_limit"
ERROR_SERVER = "server"


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    extra_content: dict[str, Any] | None = None
    provider_specific_fields: dict[str, Any] | None = None


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None

    error_status_code: int | None = None
    error_kind: str | None = None
    error_should_retry: bool | None = None
