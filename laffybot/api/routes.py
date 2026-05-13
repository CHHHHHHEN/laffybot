"""Versioned API routes."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from loguru import logger

from laffybot import __version__
from laffybot.agent.events import SSEEvent, event_error
from laffybot.api.dependencies import get_provider_store, get_session_manager, get_store
from laffybot.api.schemas import (
    ActiveSelectionResponse,
    ActiveSelectionUpdateRequest,
    HealthResponse,
    HistoryResponse,
    MessageCreateRequest,
    ModelCreateRequest,
    ModelResponse,
    ProviderCreateRequest,
    ProviderDetailResponse,
    ProviderResponse,
    ProviderUpdateRequest,
    ReadyResponse,
    SessionCancelRequest,
    SessionCancelResponse,
    SessionCreateRequest,
    SessionDeleteResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
    TestResultResponse,
)
from laffybot.providers.errors import (
    NoActiveProviderError,
    ProviderConnectionError,
)
from laffybot.session.errors import (
    SessionBusyError,
    SessionError,
    SessionNotFoundError,
    SessionStateError,
)
from laffybot.session.manager import SessionManager
from laffybot.session.models import SessionInfo, SessionStatus
from laffybot.session.provider_store import ProviderRow, ProviderStore
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
        logger.error("SSE stream error: session_id={}, error={}", session_id, exc)
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
        logger.error("SSE stream error: session_id={}, error={}", session_id, exc)
        event_index += 1
        if isinstance(exc, SessionBusyError):
            code = "SESSION_BUSY"
        elif isinstance(exc, SessionStateError):
            code = "SESSION_STATE_ERROR"
        else:
            code = "INVALID_REQUEST"
        yield _sse_frame(event_error(code=code, message=str(exc)), f"evt_{event_index}")
        yield "event: done\ndata: {}\n\n"
        return


# ─── Session Routes ────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionResponse, status_code=http_status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    session = await manager.create_session(
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
    logger.info("API request: POST /sessions/{}/messages, content_len={}", session_id, len(payload.content))
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


# ─── Health Routes ─────────────────────────────────────────────────────────────

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


# ─── Provider Routes ───────────────────────────────────────────────────────────

@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    provider_store: ProviderStore = Depends(get_provider_store),
) -> list[dict[str, object]]:
    providers = await provider_store.list_providers()
    return [
        _serialize_provider(p)
        for p in providers
    ]


@router.post("/providers", response_model=ProviderResponse, status_code=http_status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreateRequest,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    provider = await provider_store.create_provider(
        name=payload.name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        extra_headers=payload.extra_headers,
    )
    return _serialize_provider(provider)


@router.get("/providers/active", response_model=ActiveSelectionResponse | None)
async def get_active_selection(
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object] | None:
    selection = await provider_store.get_active_selection()
    if selection is None:
        return None
    return {
        "provider_id": selection.provider_id,
        "model_id": selection.model_id,
        "provider_name": selection.provider_name,
        "model_name": selection.model_name,
    }


@router.put("/providers/active", response_model=ActiveSelectionResponse)
async def set_active_selection(
    payload: ActiveSelectionUpdateRequest,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    await provider_store.set_active_selection(payload.provider_id, payload.model_id)
    selection = await provider_store.get_active_selection()
    if selection is None:
        raise NoActiveProviderError()
    return {
        "provider_id": selection.provider_id,
        "model_id": selection.model_id,
        "provider_name": selection.provider_name,
        "model_name": selection.model_name,
    }


@router.get("/providers/{provider_id}", response_model=ProviderDetailResponse)
async def get_provider(
    provider_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    provider = await provider_store.get_provider(provider_id)
    return _serialize_provider_detail(provider)


@router.put("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    payload: ProviderUpdateRequest,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    provider = await provider_store.update_provider(
        provider_id=provider_id,
        name=payload.name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        extra_headers=payload.extra_headers,
    )
    return _serialize_provider(provider)


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    active_cleared = await provider_store.delete_provider(provider_id)
    result: dict[str, object] = {"status": "deleted", "provider_id": provider_id}
    if active_cleared:
        result["active_cleared"] = True
    return result


@router.get("/providers/{provider_id}/models", response_model=list[ModelResponse])
async def list_models(
    provider_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> list[dict[str, object]]:
    models = await provider_store.list_models(provider_id)
    return [
        {"id": m.model_id, "provider_id": m.provider_id, "name": m.name}
        for m in models
    ]


@router.post("/providers/{provider_id}/models", response_model=ModelResponse, status_code=http_status.HTTP_201_CREATED)
async def add_model(
    provider_id: str,
    payload: ModelCreateRequest,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    model = await provider_store.add_model(provider_id, payload.name)
    return {"id": model.model_id, "provider_id": model.provider_id, "name": model.name}


@router.delete("/providers/{provider_id}/models/{model_id}")
async def delete_model(
    provider_id: str,
    model_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, str]:
    await provider_store.delete_model(model_id)
    return {"status": "deleted", "model_id": model_id}


@router.post("/providers/{provider_id}/test", response_model=TestResultResponse)
async def test_provider(
    provider_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    config = await provider_store.get_provider_config(provider_id)
    models = await provider_store.list_models(provider_id)
    if not models:
        return {"success": False, "message": "No models configured for this provider", "latency_ms": None}

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
    model_name = models[0].name
    start = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        latency = int((time.perf_counter() - start) * 1000)
        if response.choices:
            return {"success": True, "message": "Connection successful", "latency_ms": latency}
        return {"success": False, "message": "Unexpected response format", "latency_ms": latency}
    except Exception as exc:
        latency = int((time.perf_counter() - start) * 1000)
        exc_str = str(exc)
        if "timeout" in exc_str.lower() or "connect" in exc_str.lower() or "NameResolutionError" in type(exc).__name__:
            raise ProviderConnectionError(f"Connection failed: {exc}") from exc
        return {"success": False, "message": f"Test failed: {exc}", "latency_ms": latency}


# ─── Serializers ───────────────────────────────────────────────────────────────

def _serialize_provider(p: ProviderRow) -> dict[str, object]:
    return {
        "id": p.provider_id,
        "name": p.name,
        "base_url": p.base_url,
        "has_api_key": p.has_api_key,
        "created_at": p.created_at,
    }


def _serialize_provider_detail(p: ProviderRow) -> dict[str, object]:
    return {
        "id": p.provider_id,
        "name": p.name,
        "base_url": p.base_url,
        "has_api_key": p.has_api_key,
        "extra_headers": p.extra_headers,
        "created_at": p.created_at,
    }
