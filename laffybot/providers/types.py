from dataclasses import dataclass
from typing import Any

ERROR_TIMEOUT = "timeout"
ERROR_CONNECTION = "connection"
ERROR_RATE_LIMIT = "rate_limit"
ERROR_SERVER = "server"


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest]
    finish_reason: str = "stop"
    usage: dict[str, int] = {}
    reasoning_content: str | None = None

    error_status_code: int | None = None
    error_kind: str | None = None          # "timeout", "connection"
    error_should_retry: bool | None = None
