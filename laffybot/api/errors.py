"""HTTP error mapping for the API — follows ARCHITECTURE.md specification.

ARCHITECTURE.md 第 57-61 行:
  SessionError → 409 Conflict
  ProviderError → 502 Bad Gateway
  ToolError → 502 Bad Gateway
  未捕获 → 500 Internal
"""

from __future__ import annotations

from typing import Any

from fastapi import status as http_status
from fastapi.responses import JSONResponse
from laffybot_agent_runtime.providers.errors import ProviderError
from laffybot_agent_runtime.tools.errors import ToolError
from loguru import logger

from laffybot.service.errors import (
    SessionAlreadyArchivedError,
    SessionBusyError,
    SessionError,
    SessionNotArchivedError,
    SessionNotBusyError,
    SessionNotFoundError,
    SessionStateError,
)


def error_payload(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def error_response(
    http_status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_code,
        content=error_payload(code, message, details),
    )


def map_session_error(exc: SessionError) -> JSONResponse:
    if isinstance(exc, SessionNotFoundError):
        return error_response(
            http_status.HTTP_404_NOT_FOUND,
            "SESSION_NOT_FOUND",
            str(exc),
        )
    if isinstance(exc, SessionBusyError):
        logger.warning("Session error: {}", exc)
        details = {"request_id": exc.request_id} if exc.request_id else {}
        return error_response(
            http_status.HTTP_409_CONFLICT,
            "SESSION_BUSY",
            str(exc),
            details,
        )
    if isinstance(exc, SessionNotBusyError):
        logger.warning("Session error: {}", exc)
        return error_response(
            http_status.HTTP_409_CONFLICT,
            "SESSION_NOT_BUSY",
            str(exc),
        )
    if isinstance(exc, SessionAlreadyArchivedError):
        logger.warning("Session error: {}", exc)
        return error_response(
            http_status.HTTP_409_CONFLICT,
            "SESSION_ALREADY_ARCHIVED",
            str(exc),
        )
    if isinstance(exc, SessionNotArchivedError):
        logger.warning("Session error: {}", exc)
        return error_response(
            http_status.HTTP_409_CONFLICT,
            "SESSION_NOT_ARCHIVED",
            str(exc),
        )
    if isinstance(exc, SessionStateError):
        logger.warning("Session error: {}", exc)
        return error_response(
            http_status.HTTP_409_CONFLICT,
            "INVALID_REQUEST",
            str(exc),
            {"current_status": exc.current_status},
        )
    logger.error("Unhandled session error: {}", exc)
    return error_response(
        http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        str(exc),
    )


def map_provider_error(exc: ProviderError) -> JSONResponse:
    """Provider/Tool errors → 502 Bad Gateway per ARCHITECTURE.md."""
    logger.error("Upstream error: {}", exc)
    return error_response(
        http_status.HTTP_502_BAD_GATEWAY,
        "UPSTREAM_ERROR",
        str(exc),
    )


def map_tool_error(exc: ToolError) -> JSONResponse:
    """Tool errors → 502 Bad Gateway per ARCHITECTURE.md."""
    logger.error("Tool error: {}", exc)
    return error_response(
        http_status.HTTP_502_BAD_GATEWAY,
        "TOOL_ERROR",
        str(exc),
        {"tool_name": exc.tool_name} if exc.tool_name else None,
    )
