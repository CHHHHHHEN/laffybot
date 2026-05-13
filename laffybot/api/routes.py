"""Versioned API routes."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from fastapi import status as http_status
from fastapi.responses import StreamingResponse

from laffybot import __version__
from laffybot.agent.events import SSEEvent, event_error
from laffybot.api.dependencies import get_session_manager, get_store
from laffybot.api.schemas import (
    HealthResponse,
    HistoryResponse,
    MessageCreateRequest,
    ReadyResponse,
    SessionCancelRequest,
    SessionCancelResponse,
    SessionCreateRequest,
    SessionDeleteResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
)
from laffybot.session.errors import SessionBusyError, SessionError, SessionNotFoundError
from laffybot.session.manager import SessionManager
from laffybot.session.models import SessionInfo, SessionStatus
from laffybot.session.store import SessionStore

router = APIRouter(prefix="/api/v1")


def _serialize_session(session: SessionInfo) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "model": session.model,
        "status": session.status,
        "created_at": session.created_at,
    }


def _serialize_session_detail(session: SessionInfo) -> dict[str, object]:
    payload = _serialize_session(session)
    payload["message_count"] = session.message_count
    payload["current_request_id"] = session.current_request_id
    return payload


def _serialize_message(message: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {
        "role": message["role"],
        "content": message["content"],
        "timestamp": message["timestamp"],
    }
    if "metadata" in message:
        result["metadata"] = message["metadata"]
    if "input_tokens" in message:
        result["input_tokens"] = message["input_tokens"]
    if "output_tokens" in message:
        result["output_tokens"] = message["output_tokens"]
    return result


def _sse_frame(event: SSEEvent, event_id: str) -> str:
    return f"id: {event_id}\n{event.to_sse()}"


async def _stream_session_events(
    manager: SessionManager,
    session_id: str,
    content: str,
    last_event_id: str | None = None,
) -> AsyncGenerator[str, None]:
    del last_event_id
    event_index = 0
    try:
        async for event in manager.send_message(session_id, content):
            event_index += 1
            yield _sse_frame(event, f"evt_{event_index}")
    except SessionNotFoundError as exc:
        event_index += 1
        yield _sse_frame(
            event_error(
                code="SESSION_NOT_FOUND",
                message=str(exc),
            ),
            f"evt_{event_index}",
        )
        yield "event: done\ndata: {}\n\n"
        return
    except SessionError as exc:
        event_index += 1
        code = "SESSION_BUSY" if isinstance(exc, SessionBusyError) else "INVALID_REQUEST"
        yield _sse_frame(event_error(code=code, message=str(exc)), f"evt_{event_index}")
        yield "event: done\ndata: {}\n\n"
        return
    yield "event: done\ndata: {}\n\n"


@router.post("/sessions", response_model=SessionResponse, status_code=http_status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    session = await manager.create_session(
        model=payload.model,
        system_prompt=payload.system_prompt,
        max_iterations=payload.max_iterations,
    )
    return _serialize_session(session)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    session = await manager.get_session_info(session_id)
    return _serialize_session_detail(session)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    status: SessionStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    sessions, total = await manager.list_sessions(status=status, limit=limit, offset=offset)
    return {
        "sessions": [
            {
                **_serialize_session(session),
                "message_count": session.message_count,
            }
            for session in sessions
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_history(
    session_id: str,
    limit: int = 50,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    messages = await manager.get_session_history(session_id, limit=limit)
    return {
        "session_id": session_id,
        "messages": [_serialize_message(message) for message in messages],
    }


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    payload: MessageCreateRequest,
    manager: SessionManager = Depends(get_session_manager),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    session = await manager.get_session_info(session_id)
    if session.status == "busy":
        raise SessionBusyError(session_id, session.current_request_id)

    stream = _stream_session_events(manager, session_id, payload.content, last_event_id)
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(stream, media_type="text/event-stream", headers=headers)


@router.post("/sessions/{session_id}/cancel", response_model=SessionCancelResponse)
async def cancel_session(
    session_id: str,
    payload: SessionCancelRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    request_id = await manager.cancel_request(session_id, payload.reason)
    return {"status": "cancelled", "session_id": session_id, "request_id": request_id}


@router.delete("/sessions/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@router.get("/health", response_model=HealthResponse)
async def health() -> dict[str, object]:
    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc),
    }


@router.get("/ready", response_model=ReadyResponse)
async def ready(store: SessionStore = Depends(get_store)) -> dict[str, object]:
    try:
        await store.list_sessions(limit=1, offset=0)
    except Exception as exc:
        return {"status": "not_ready", "checks": {"database": str(exc)}}
    return {"status": "ready", "checks": {"database": "ok"}}
