"""Session, events, settings, and memory routes — only access service layer via SessionManager."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from loguru import logger

from laffybot.api.dependencies import get_event_bus, get_session_manager
from laffybot.api.schemas import (
    ConsolidatedMemoryResponse,
    ConsolidationStatusResponse,
    HistoryResponse,
    MemoryListResponse,
    MemoryResponse,
    MemorySourceResponse,
    MessageCreateRequest,
    SessionCancelRequest,
    SessionCancelResponse,
    SessionCreateRequest,
    SessionDeleteResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionModelUpdateRequest,
    SessionResponse,
    SessionTitleUpdateRequest,
    SystemPromptUpdateRequest,
)
from laffybot.api.sse_adapter import stream_global_events, stream_session_events
from laffybot.service.models import SessionInfo, SessionStatus
from laffybot.service.protocols import SessionManager

router = APIRouter()


def _serialize_session(session: SessionInfo) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "provider_id": session.provider_id,
        "model_name": session.model_name,
        "status": session.status,
        "created_at": session.created_at,
        "title": session.title,
        "archived_at": session.archived_at,
    }


def _serialize_session_detail(session: SessionInfo) -> dict[str, object]:
    payload = _serialize_session(session)
    payload["message_count"] = session.message_count
    payload["current_request_id"] = session.current_request_id
    payload["title_auto_generated"] = session.title_auto_generated
    return payload


def _serialize_message(message: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {
        "role": message["role"],
        "content": message["content"],
        "timestamp": message["timestamp"],
    }
    for key in (
        "metadata",
        "input_tokens",
        "output_tokens",
        "reasoning_content",
        "tool_calls",
    ):
        if key in message:
            result[key] = message[key]
    return result


# ─── Session Routes ────────────────────────────────────────────────────────────


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_session(
    payload: SessionCreateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    try:
        session = await manager.create_session(
            max_iterations=payload.max_iterations,
            provider_id=payload.provider_id,
            model_name=payload.model_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    archived: bool | None = None,
    limit: int = 20,
    offset: int = 0,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    sessions, total = await manager.list_sessions(
        status=status, archived=archived, limit=limit, offset=offset
    )
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
    logger.info(
        "API request: POST /sessions/{}/messages, content_len={}",
        session_id,
        len(payload.content),
    )
    event_stream = manager.send_message(session_id, payload.content)
    stream = stream_session_events(
        event_stream,
        session_id=session_id,
        last_event_id=last_event_id,
    )

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


@router.post("/sessions/{session_id}/archive", response_model=SessionDetailResponse)
async def archive_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    session = await manager.archive_session(session_id)
    return _serialize_session_detail(session)


@router.post("/sessions/{session_id}/unarchive", response_model=SessionDetailResponse)
async def unarchive_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    session = await manager.unarchive_session(session_id)
    return _serialize_session_detail(session)


@router.delete("/sessions/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


# ─── Global Events Route ────────────────────────────────────────────────────────


@router.get("/events")
async def global_events(
    event_bus: Any = Depends(get_event_bus),
) -> StreamingResponse:
    """SSE stream for global events (title updates, etc.)."""

    async def event_stream() -> AsyncGenerator[str, None]:
        logger.info("Global events SSE connection opened")

        queue: asyncio.Queue[Any | None] = asyncio.Queue()
        await event_bus.add_subscriber(queue)
        logger.debug(
            "Global events subscriber added, total={}", event_bus.subscriber_count
        )

        try:
            async for frame in stream_global_events(queue):
                yield frame
        except Exception as e:
            logger.info("Global events SSE connection closed: {}", type(e).__name__)
            logger.debug("Global events SSE connection error details: {}", e)
        finally:
            await event_bus.remove_subscriber(queue)
            logger.debug(
                "Global events subscriber removed, remaining={}",
                event_bus.subscriber_count,
            )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )


@router.put("/sessions/{session_id}/model", response_model=SessionResponse)
async def update_session_model(
    session_id: str,
    payload: SessionModelUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    session = await manager.update_session_model(
        session_id, payload.provider_id, payload.model_name
    )
    return _serialize_session(session)


@router.patch("/sessions/{session_id}/title", response_model=SessionDetailResponse)
async def update_session_title(
    session_id: str,
    payload: SessionTitleUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    await manager.update_session_title(session_id, payload.title)
    session = await manager.get_session_info(session_id)
    return _serialize_session_detail(session)


# ─── System Prompt Routes ─────────────────────────────────────────────────────


@router.get("/settings/system-prompt")
async def get_system_prompt(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    system_prompt = await manager.get_system_prompt("")
    return {"system_prompt": system_prompt or ""}


@router.put("/settings/system-prompt")
async def set_system_prompt(
    payload: SystemPromptUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.set_system_prompt("", payload.system_prompt)
    return {"system_prompt": payload.system_prompt}


# ─── Settings Routes ───────────────────────────────────────────────────────────


@router.get("/settings/default-session-model")
async def get_default_session_model(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str] | None:
    return await manager.get_default_session_config()


@router.put("/settings/default-session-model")
async def set_default_session_model(
    payload: SessionModelUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    return await manager.set_default_session_config(
        payload.provider_id, payload.model_name
    )


@router.delete("/settings/default-session-model")
async def delete_default_session_model(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_default_session_config()
    return {"status": "cleared"}


@router.get("/settings/summary-model")
async def get_summary_model(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str] | None:
    return await manager.get_summary_model()


@router.put("/settings/summary-model")
async def set_summary_model(
    payload: SessionModelUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    return await manager.set_summary_model(payload.provider_id, payload.model_name)


@router.delete("/settings/summary-model")
async def delete_summary_model(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_summary_model()
    return {"status": "cleared"}


@router.get("/settings/extract-model")
async def get_extract_model(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str] | None:
    return await manager.get_extract_model()


@router.put("/settings/extract-model")
async def set_extract_model(
    payload: SessionModelUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    return await manager.set_extract_model(payload.provider_id, payload.model_name)


@router.delete("/settings/extract-model")
async def delete_extract_model(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_extract_model()
    return {"status": "cleared"}


@router.get("/settings/consolidation-model")
async def get_consolidation_model(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str] | None:
    return await manager.get_consolidation_model()


@router.put("/settings/consolidation-model")
async def set_consolidation_model(
    payload: SessionModelUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    return await manager.set_consolidation_model(
        payload.provider_id, payload.model_name
    )


@router.delete("/settings/consolidation-model")
async def delete_consolidation_model(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_consolidation_model()
    return {"status": "cleared"}


# ─── Memory Routes ──────────────────────────────────────────────────────────────


@router.get("/memories", response_model=MemoryListResponse)
async def list_memories(
    limit: int = 20,
    offset: int = 0,
    search: str | None = None,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.list_memories(limit=limit, offset=offset, search=search)


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    memory = await manager.get_memory(memory_id)
    if memory is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MEMORY_NOT_FOUND",
                "message": f"Memory {memory_id} not found",
            },
        )
    return memory


@router.get("/memories/{memory_id}/source", response_model=MemorySourceResponse)
async def get_memory_source(
    memory_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    result = await manager.get_memory_source(memory_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MEMORY_NOT_FOUND",
                "message": f"Memory {memory_id} not found",
            },
        )
    return result


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_memory(memory_id)
    return {"status": "deleted", "memory_id": memory_id}


# ─── Consolidated Memory Routes ────────────────────────────────────────────────


@router.get("/consolidated-memory", response_model=ConsolidatedMemoryResponse)
async def get_consolidated_memory(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    record = await manager.get_consolidated_memory("")
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CONSOLIDATED_MEMORY_NOT_FOUND",
                "message": "No consolidated memory available",
            },
        )
    return record


@router.post("/consolidated-memory/trigger")
async def trigger_consolidation(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    performed = await manager.trigger_consolidation("")
    return {
        "performed": performed,
        "message": "Consolidation triggered"
        if performed
        else "Consolidation skipped (below threshold or in progress)",
    }


@router.get("/consolidated-memory/status", response_model=ConsolidationStatusResponse)
async def get_consolidation_status(
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    result = await manager.list_memories(limit=1, offset=0)
    total_raw = result.get("total", 0)
    record = await manager.get_consolidated_memory("")
    has_consolidated = False
    consolidated_source_count = 0
    if record is not None and record.get("content"):
        has_consolidated = True
        consolidated_source_count = len(record.get("source_memory_ids", []))
    return {
        "has_consolidated_memory": has_consolidated,
        "total_raw_memories": total_raw,
        "consolidated_source_count": consolidated_source_count,
        "unconsolidated_count": max(0, total_raw - consolidated_source_count),
    }
