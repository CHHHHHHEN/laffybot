"""Tool execution domain exceptions."""

from __future__ import annotations

from typing import Any


class ToolError(Exception):
    """Raised when a tool execution fails for a known reason."""

    def __init__(
        self,
        message: str,
        tool_name: str = "",
        params: dict[str, Any] | None = None,
        code: str = "TOOL_EXECUTION_ERROR",
    ):
        self.tool_name = tool_name
        self.params = params
        self.code = code
        super().__init__(message)
