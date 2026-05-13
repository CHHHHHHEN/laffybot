"""HTTP error mapping for the API."""

from __future__ import annotations

from typing import Any

from fastapi import status as http_status
from fastapi.responses import JSONResponse

from laffybot.providers.errors import (
    ModelNameConflictError,
    ModelNotFoundError,
    NoActiveProviderError,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderNotFoundError,
)
from laffybot.session.errors import (
    SessionBusyError,
    SessionError,
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
        details = {"request_id": exc.request_id} if exc.request_id else {}
        return error_response(
            http_status.HTTP_409_CONFLICT,
            "SESSION_BUSY",
            str(exc),
            details,
        )
    if isinstance(exc, SessionNotBusyError):
        return error_response(
            http_status.HTTP_409_CONFLICT,
            "SESSION_NOT_BUSY",
            str(exc),
        )
    if isinstance(exc, SessionStateError):
        return error_response(
            http_status.HTTP_409_CONFLICT,
            "INVALID_REQUEST",
            str(exc),
            {"current_status": exc.current_status},
        )
    return error_response(
        http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        str(exc),
    )


def map_provider_error(exc: ProviderNotFoundError | ProviderConnectionError | ProviderConfigError | NoActiveProviderError | ModelNotFoundError | ModelNameConflictError) -> JSONResponse:
    if isinstance(exc, ProviderNotFoundError):
        return error_response(http_status.HTTP_404_NOT_FOUND, "PROVIDER_NOT_FOUND", str(exc))
    if isinstance(exc, ProviderConfigError):
        return error_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, "PROVIDER_CONFIG_ERROR", str(exc))
    if isinstance(exc, ProviderConnectionError):
        return error_response(http_status.HTTP_502_BAD_GATEWAY, "PROVIDER_CONNECTION_ERROR", str(exc))
    if isinstance(exc, NoActiveProviderError):
        return error_response(http_status.HTTP_400_BAD_REQUEST, "NO_ACTIVE_PROVIDER", str(exc))
    if isinstance(exc, ModelNotFoundError):
        return error_response(http_status.HTTP_404_NOT_FOUND, "MODEL_NOT_FOUND", str(exc))
    if isinstance(exc, ModelNameConflictError):
        return error_response(http_status.HTTP_409_CONFLICT, "MODEL_NAME_CONFLICT", str(exc))
    return error_response(http_status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", str(exc))
