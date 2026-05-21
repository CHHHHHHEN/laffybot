"""Session, events, settings, and memory routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from laffybot_agent_runtime.config import ContextConfig
from laffybot_agent_runtime.events import SSEEvent, event_ping
from laffybot_agent_runtime.heartbeat import HeartbeatManager
from laffybot_agent_runtime.providers.errors import (
    ModelNotFoundError,
)
from laffybot_agent_runtime.skills import SkillRegistry, SkillsLoader
from loguru import logger

from laffybot.api.dependencies import (
    DefaultProviderFactory,
    get_app_setting_store,
    get_memory_manager,
    get_memory_store,
    get_provider_store,
    get_session_manager,
    get_skill_registry,
    get_skills_loader,
    get_store,
    render_skills_block,
)
from laffybot.api.event_bus import GlobalEvent, get_event_bus
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
from laffybot.memory import MemoryManager, MemoryNotFoundError, MemoryStore
from laffybot.memory.consolidator import MemoryConsolidator
from laffybot.session.app_setting_store import AppSettingStore
from laffybot.session.errors import (
    SessionBusyError,
    SessionNotFoundError,
)
from laffybot.session.manager import SessionManager
from laffybot.session.models import SessionInfo, SessionStatus
from laffybot.session.provider_store import ProviderStore
from laffybot.session.store import SessionStore

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
    if "metadata" in message:
        result["metadata"] = message["metadata"]
    if "input_tokens" in message:
        result["input_tokens"] = message["input_tokens"]
    if "output_tokens" in message:
        result["output_tokens"] = message["output_tokens"]
    if "reasoning_content" in message:
        result["reasoning_content"] = message["reasoning_content"]
    if "tool_calls" in message:
        result["tool_calls"] = message["tool_calls"]
    return result


def _sse_frame(event: SSEEvent, event_id: str) -> str:
    return f"id: {event_id}\n{event.to_sse()}"


async def _stream_session_events(
    manager: SessionManager,
    session_id: str,
    content: str,
    skills_block: str = "",
    last_event_id: str | None = None,
) -> AsyncGenerator[str, None]:
    del last_event_id
    event_index = 0
    heartbeat = HeartbeatManager()

    ait = manager.send_message(
        session_id, content, skills_block=skills_block
    ).__aiter__()
    heartbeat.reset()

    try:
        while True:
            try:
                event = await asyncio.wait_for(
                    ait.__anext__(),
                    timeout=heartbeat.interval_s,
                )
                event_index += 1
                yield _sse_frame(event, f"evt_{event_index}")
                heartbeat.reset()
            except asyncio.TimeoutError:
                event_index += 1
                yield f"id: evt_{event_index}\n{await heartbeat.wait_for_ping() or event_ping().to_sse()}"
    except StopAsyncIteration:
        pass
    finally:
        try:
            current = await manager.get_session_info(session_id)
            if current.status == "busy":
                logger.warning(
                    "Session stuck busy after stream cleanup: session_id={}", session_id
                )
                await manager.store.update_session_status(
                    session_id,
                    "idle",
                    current_request_id=None,
                    error_message="Session reset by stream cleanup",
                )
        except Exception:
            logger.exception("Failed to reset stuck busy session in SSE stream cleanup")
        heartbeat.stop()


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
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
    skills_loader: SkillsLoader = Depends(get_skills_loader),
    skill_registry: SkillRegistry = Depends(get_skill_registry),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    logger.info(
        "API request: POST /sessions/{}/messages, content_len={}",
        session_id,
        len(payload.content),
    )
    session = await manager.get_session_info(session_id)
    if session.status == "busy":
        raise SessionBusyError(session_id, session.current_request_id)

    skills_block = await render_skills_block(
        app_setting_store, skills_loader, skill_registry
    )
    stream = _stream_session_events(
        manager, session_id, payload.content, skills_block, last_event_id
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
async def global_events() -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        bus = get_event_bus()
        heartbeat = HeartbeatManager()
        event_index = 0

        logger.info("Global events SSE connection opened")

        queue: asyncio.Queue[GlobalEvent | None] = asyncio.Queue()
        async with bus._lock:
            bus._subscribers.append(queue)
        logger.debug("Global events subscriber added, total={}", len(bus._subscribers))

        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=heartbeat.interval_s,
                    )
                    if event is None:
                        break
                    event_index += 1
                    yield f"id: evt_{event_index}\n{event.to_sse()}"
                except asyncio.TimeoutError:
                    event_index += 1
                    yield f"id: evt_{event_index}\n{await heartbeat.wait_for_ping() or event_ping().to_sse()}"
        except Exception as e:
            logger.info("Global events SSE connection closed: {}", type(e).__name__)
            logger.debug("Global events SSE connection error details: {}", e)
        finally:
            async with bus._lock:
                try:
                    bus._subscribers.remove(queue)
                except ValueError:
                    pass
            logger.debug(
                "Global events subscriber removed, remaining={}",
                len(bus._subscribers),
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
    store: SessionStore = Depends(get_store),
) -> dict[str, object]:
    session = await store.get_session(session_id)

    success = await store.update_session_title(
        session_id,
        payload.title,
        session.user_message_count,
        session.title_auto_generated,
    )

    if not success:
        session = await store.get_session(session_id)
        success = await store.update_session_title(
            session_id,
            payload.title,
            session.user_message_count,
            session.title_auto_generated,
        )

    updated_session = await store.get_session(session_id)
    return _serialize_session_detail(updated_session)


# ─── System Prompt Routes ─────────────────────────────────────────────────────


@router.get("/settings/system-prompt")
async def get_system_prompt(
    request: Request,
) -> dict[str, str]:
    context_config: ContextConfig = request.app.state.context_config
    return {"system_prompt": context_config.system_prompt}


@router.put("/settings/system-prompt")
async def set_system_prompt(
    payload: SystemPromptUpdateRequest,
    request: Request,
) -> dict[str, str]:
    context_config: ContextConfig = request.app.state.context_config
    context_config.system_prompt = payload.system_prompt
    return {"system_prompt": context_config.system_prompt}


# ─── Settings Routes ───────────────────────────────────────────────────────────


@router.get("/settings/default-session-model")
async def get_default_session_model(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> dict[str, str] | None:
    config = await app_setting_store.get_default_session_config()
    if config is None:
        return None
    return {"provider_id": config.provider_id, "model_name": config.model_name}


@router.put("/settings/default-session-model")
async def set_default_session_model(
    payload: SessionModelUpdateRequest,
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, str]:
    await provider_store.get_provider(payload.provider_id)
    models = await provider_store.list_models(payload.provider_id)
    if not any(m.name == payload.model_name for m in models):
        raise ModelNotFoundError(payload.model_name)
    await app_setting_store.set_default_session_config(
        payload.provider_id, payload.model_name
    )
    return {"provider_id": payload.provider_id, "model_name": payload.model_name}


@router.delete("/settings/default-session-model")
async def delete_default_session_model(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> dict[str, str]:
    await app_setting_store.delete_default_session_config()
    return {"status": "cleared"}


@router.get("/settings/summary-model")
async def get_summary_model(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> dict[str, str] | None:
    config = await app_setting_store.get_summary_model()
    if config is None:
        return None
    return {"provider_id": config.provider_id, "model_name": config.model_name}


@router.put("/settings/summary-model")
async def set_summary_model(
    payload: SessionModelUpdateRequest,
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, str]:
    await provider_store.get_provider(payload.provider_id)
    models = await provider_store.list_models(payload.provider_id)
    if not any(m.name == payload.model_name for m in models):
        raise ModelNotFoundError(payload.model_name)
    await app_setting_store.set_summary_model(payload.provider_id, payload.model_name)
    return {"provider_id": payload.provider_id, "model_name": payload.model_name}


@router.delete("/settings/summary-model")
async def delete_summary_model(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> dict[str, str]:
    await app_setting_store.delete_summary_model()
    return {"status": "cleared"}


# ─── Extract-Model Settings ─────────────────────────────────────────────────────


@router.get("/settings/extract-model")
async def get_extract_model(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> dict[str, str] | None:
    config = await app_setting_store.get_extract_model()
    if config is None:
        return None
    return {"provider_id": config.provider_id, "model_name": config.model_name}


@router.put("/settings/extract-model")
async def set_extract_model(
    payload: SessionModelUpdateRequest,
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, str]:
    await provider_store.get_provider(payload.provider_id)
    models = await provider_store.list_models(payload.provider_id)
    if not any(m.name == payload.model_name for m in models):
        raise ModelNotFoundError(payload.model_name)
    await app_setting_store.set_extract_model(payload.provider_id, payload.model_name)
    return {"provider_id": payload.provider_id, "model_name": payload.model_name}


@router.delete("/settings/extract-model")
async def delete_extract_model(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> dict[str, str]:
    await app_setting_store.delete_extract_model()
    return {"status": "cleared"}


# ─── Consolidation-Model Settings ───────────────────────────────────────────────


@router.get("/settings/consolidation-model")
async def get_consolidation_model(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> dict[str, str] | None:
    config = await app_setting_store.get_consolidation_model()
    if config is None:
        return None
    return {"provider_id": config.provider_id, "model_name": config.model_name}


@router.put("/settings/consolidation-model")
async def set_consolidation_model(
    payload: SessionModelUpdateRequest,
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, str]:
    await provider_store.get_provider(payload.provider_id)
    models = await provider_store.list_models(payload.provider_id)
    if not any(m.name == payload.model_name for m in models):
        raise ModelNotFoundError(payload.model_name)
    await app_setting_store.set_consolidation_model(
        payload.provider_id, payload.model_name
    )
    return {"provider_id": payload.provider_id, "model_name": payload.model_name}


@router.delete("/settings/consolidation-model")
async def delete_consolidation_model(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> dict[str, str]:
    await app_setting_store.delete_consolidation_model()
    return {"status": "cleared"}


# ─── Memory Routes ──────────────────────────────────────────────────────────────


@router.get("/memories", response_model=MemoryListResponse)
async def list_memories(
    limit: int = 20,
    offset: int = 0,
    search: str | None = None,
    store: MemoryStore = Depends(get_memory_store),
) -> dict[str, object]:
    memories, total = await store.list_memories(
        limit=limit, offset=offset, search=search
    )
    return {
        "memories": memories,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    store: MemoryStore = Depends(get_memory_store),
) -> dict[str, object]:
    memory = await store.get_memory(memory_id)
    if memory is None:
        raise MemoryNotFoundError(memory_id)
    return memory


@router.get("/memories/{memory_id}/source", response_model=MemorySourceResponse)
async def get_memory_source(
    memory_id: str,
    store: MemoryStore = Depends(get_memory_store),
    session_store: SessionStore = Depends(get_store),
) -> dict[str, object]:
    memory = await store.get_memory(memory_id)
    if memory is None:
        raise MemoryNotFoundError(memory_id)
    session_id = memory["session_id"]
    try:
        session = await session_store.get_session(session_id)
    except SessionNotFoundError:
        session = None
    messages = await session_store.get_messages(session_id, limit=1000)
    return {
        "session_id": session_id,
        "session_title": session.title if session else None,
        "messages": [_serialize_message(m) for m in messages],
    }


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    store: MemoryStore = Depends(get_memory_store),
) -> dict[str, str]:
    await store.delete_memory(memory_id)
    return {"status": "deleted", "memory_id": memory_id}


# ─── Consolidated Memory Routes ────────────────────────────────────────────────


@router.get("/consolidated-memory", response_model=ConsolidatedMemoryResponse)
async def get_consolidated_memory(
    memory_manager: MemoryManager | None = Depends(get_memory_manager),
) -> dict[str, object]:
    if memory_manager is None or memory_manager.consolidated_store is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CONSOLIDATED_MEMORY_NOT_FOUND",
                "message": "No consolidated memory available",
            },
        )
    record = await memory_manager.consolidated_store.get()
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
    memory_manager: MemoryManager | None = Depends(get_memory_manager),
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    if memory_manager is None or memory_manager.store is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CONSOLIDATION_NOT_CONFIGURED",
                "message": "Memory system not available",
            },
        )
    if memory_manager.consolidated_store is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CONSOLIDATION_NOT_CONFIGURED",
                "message": "Consolidated memory store not available",
            },
        )

    config = await app_setting_store.get_consolidation_model()
    if config is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CONSOLIDATION_NOT_CONFIGURED",
                "message": "Consolidation model not configured",
            },
        )

    provider_config = await provider_store.get_provider_config(config.provider_id)
    provider_factory = DefaultProviderFactory()
    provider = await provider_factory.create_provider(provider_config)

    consolidator = MemoryConsolidator(
        provider=provider,
        model=config.model_name,
        memory_store=memory_manager.store,
        consolidated_store=memory_manager.consolidated_store,
        trigger_count=memory_manager.config.consolidation_trigger_count,
        max_source_memories=memory_manager.config.max_source_memories,
    )

    performed = await consolidator.try_consolidate()
    return {
        "performed": performed,
        "message": "Consolidation triggered"
        if performed
        else "Consolidation skipped (below threshold or in progress)",
    }


@router.get("/consolidated-memory/status", response_model=ConsolidationStatusResponse)
async def get_consolidation_status(
    memory_manager: MemoryManager | None = Depends(get_memory_manager),
    store: MemoryStore = Depends(get_memory_store),
) -> dict[str, object]:
    total_raw = 0
    consolidated_source_count = 0
    has_consolidated = False

    if memory_manager is not None and memory_manager.consolidated_store is not None:
        record = await memory_manager.consolidated_store.get()
        if record is not None and record["content"]:
            has_consolidated = True
            consolidated_source_count = len(record["source_memory_ids"])

    if store is not None:
        _, total_raw = await store.list_memories(limit=1, offset=0)

    return {
        "has_consolidated_memory": has_consolidated,
        "total_raw_memories": total_raw,
        "consolidated_source_count": consolidated_source_count,
        "unconsolidated_count": max(0, total_raw - consolidated_source_count),
    }
