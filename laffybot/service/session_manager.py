"""Thin session orchestrator — coordinates state, storage, and agent execution."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from laffybot_agent_runtime.cancellation import CancellationToken, CancelledError
from laffybot_agent_runtime.events import (
    SSEEvent,
    event_cancelled,
    event_error,
    event_session_start,
)
from laffybot_agent_runtime.runner import AgentRunner, AgentRunSpec
from laffybot_agent_runtime.tools.registry import ToolRegistry
from loguru import logger

from laffybot import __version__
from laffybot.db.mcp_server_store import ServerNameConflictError
from laffybot.db.provider_store import (
    ModelNotFoundError,
    ProviderNotFoundError,
)
from laffybot.eventbus.bus import EventBus
from laffybot.service.async_events import AsyncEventProcessor
from laffybot.service.context.builder import SimpleContextBuilder
from laffybot.service.context.compressor import LLMSummarizer
from laffybot.service.error_log import get_error_log
from laffybot.service.errors import (
    SessionAlreadyArchivedError,
    SessionBusyError,
    SessionError,
    SessionNotArchivedError,
    SessionNotBusyError,
)
from laffybot.service.local_lock_port import LocalSessionLockPort
from laffybot.service.message_accumulator import MessageAccumulator
from laffybot.service.models import SessionInfo, SessionStatus
from laffybot.service.protocols import SessionManager
from laffybot.service.provider_factory import ProviderFactory
from laffybot.service.state_machine import SessionStateMachine

if TYPE_CHECKING:
    from laffybot_agent_runtime.skills import SkillRegistry, SkillsLoader
    from laffybot_agent_runtime.tools.mcp.manager import McpServerManager

    from laffybot.db.app_setting_store import AppSettingStore
    from laffybot.db.mcp_server_store import McpServerStore
    from laffybot.db.memory_store import MemoryStore
    from laffybot.db.provider_store import ProviderStore
    from laffybot.db.session_store import SessionStore
    from laffybot.memory.manager import MemoryManager


class DefaultSessionManager(SessionManager):
    """Thin coordinator: orchestration and transaction boundaries only."""

    def __init__(
        self,
        store: SessionStore,
        provider_store: ProviderStore,
        app_setting_store: AppSettingStore,
        tool_registry: ToolRegistry,
        provider_factory: ProviderFactory,
        context_builder: SimpleContextBuilder,
        memory_manager: MemoryManager | None = None,
        memory_store: MemoryStore | None = None,
        mcp_server_store: McpServerStore | None = None,
        mcp_manager: McpServerManager | None = None,
        skills_loader: SkillsLoader | None = None,
        skill_registry: SkillRegistry | None = None,
        event_bus: EventBus | None = None,
        max_active_sessions: int = 3,
        tool_timeout_s: int = 120,
        session_timeout_s: int = 600,
        watchdog_interval_s: int = 60,
    ) -> None:
        self.store = store
        self.provider_store = provider_store
        self.app_setting_store = app_setting_store
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.memory_store = memory_store
        self.mcp_server_store = mcp_server_store
        self.mcp_manager = mcp_manager
        self.skills_loader = skills_loader
        self.skill_registry = skill_registry
        self.max_active_sessions = max_active_sessions
        self.tool_timeout_s = tool_timeout_s
        self._session_timeout_s = session_timeout_s
        self._watchdog_interval_s = watchdog_interval_s
        self._active_tokens: dict[str, CancellationToken] = {}
        self._provider_factory = provider_factory
        self._context_builder = context_builder
        self._watchdog_task: asyncio.Task[Any] | None = None
        self._watchdog_stop_event = asyncio.Event()

        lock_port = LocalSessionLockPort()
        self._state = SessionStateMachine(lock_port)
        self._event_processor = AsyncEventProcessor(
            store=store,
            provider_store=provider_store,
            app_setting_store=app_setting_store,
            provider_factory=provider_factory,
            memory_manager=memory_manager,
            event_publisher=event_bus,
        )

    async def start(self) -> None:
        self._watchdog_stop_event.clear()
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def shutdown(self) -> None:
        if self._watchdog_task is not None:
            self._watchdog_stop_event.set()
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None
        await self._event_processor.shutdown()

    async def get_health_status(self) -> dict[str, object]:
        return {
            "status": "healthy",
            "version": __version__,
            "timestamp": datetime.now(timezone.utc),
        }

    async def get_readiness_status(self) -> dict[str, object]:
        try:
            await self.store.check_connection()
        except Exception as exc:
            return {"status": "not_ready", "checks": {"database": str(exc)}}
        return {"status": "ready", "checks": {"database": "ok"}}

    async def _watchdog_loop(self) -> None:
        while not self._watchdog_stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._watchdog_stop_event.wait(),
                    timeout=self._watchdog_interval_s,
                )
                break
            except asyncio.TimeoutError:
                pass

            try:
                busy_sessions, _ = await self.store.list_sessions(
                    status="busy", limit=1000
                )
                now = datetime.now(timezone.utc)
                threshold = self._session_timeout_s

                for session in busy_sessions:
                    elapsed = (now - session.updated_at).total_seconds()
                    if elapsed < threshold:
                        continue

                    logger.warning(
                        "Stuck-busy session reset: session_id={}, elapsed_s={:.0f}, threshold_s={}",
                        session.session_id,
                        elapsed,
                        threshold,
                    )

                    token = self._active_tokens.pop(session.session_id, None)
                    if token is not None:
                        token.cancel("watchdog timeout")

                    await self._state.force_to_idle(session.session_id)

                    try:
                        await self.store.update_session_status(
                            session.session_id,
                            "idle",
                            current_request_id=None,
                            error_message=f"Session stuck busy for {elapsed:.0f}s",
                            expected_status="busy",
                        )
                    except Exception:
                        logger.exception(
                            "Watchdog reset failed (optimistic lock): session_id={}",
                            session.session_id,
                        )
            except Exception:
                logger.exception("Watchdog scan failed")

    @staticmethod
    def _request_id() -> str:
        return f"req_{uuid.uuid4().hex[:12]}"

    async def create_session(
        self,
        max_iterations: int = 50,
        provider_id: str | None = None,
        model_name: str | None = None,
    ) -> SessionInfo:
        if provider_id is not None and model_name is not None:
            await self.provider_store.get_provider(provider_id)
            models = await self.provider_store.list_models(provider_id)
            if not any(m.name == model_name for m in models):
                raise ModelNotFoundError(model_name)
        elif provider_id is None and model_name is None:
            config = await self.app_setting_store.get_default_session_config()
            if config is None:
                raise ValueError(
                    "No default session model configured. "
                    "Please configure a default model in settings."
                )
            provider_id = config.provider_id
            model_name = config.model_name
        else:
            raise ValueError("provider_id and model_name must be provided together")
        session_id = str(uuid.uuid4())
        session = await self.store.create_session(
            session_id=session_id,
            provider_id=provider_id,
            model_name=model_name,
            system_prompt=None,
            max_iterations=max_iterations,
        )
        logger.info(
            "Session created: session_id={}, provider_id={}, model_name={}",
            session_id,
            provider_id,
            model_name,
        )
        await self._event_processor.submit_auto_archive(session_id)
        return session

    async def get_session_info(self, session_id: str) -> SessionInfo:
        return await self.store.get_session(session_id)

    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        archived: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by_asc: bool = False,
    ) -> tuple[list[SessionInfo], int]:
        return await self.store.list_sessions(
            status=status,
            archived=archived,
            limit=limit,
            offset=offset,
            order_by_asc=order_by_asc,
        )

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self.store.get_messages(session_id, limit=limit)

    async def delete_session(self, session_id: str) -> None:
        session = await self.store.get_session(session_id)
        if session.status == "busy":
            raise SessionBusyError(session_id, session.current_request_id)
        await self.store.delete_session(session_id)
        logger.info("Session deleted: session_id={}", session_id)

    async def archive_session(self, session_id: str) -> SessionInfo:
        session = await self.store.get_session(session_id)
        if session.archived_at is not None:
            raise SessionAlreadyArchivedError(session_id)
        archived = await self.store.archive_session(session_id)
        await self._event_processor.submit_memory_extract(session_id)
        return archived

    async def unarchive_session(self, session_id: str) -> SessionInfo:
        session = await self.store.get_session(session_id)
        if session.status == "busy":
            raise SessionBusyError(session_id, session.current_request_id)
        if session.archived_at is None:
            raise SessionNotArchivedError(session_id)
        return await self.store.unarchive_session(session_id)

    async def cancel_request(self, session_id: str, reason: str | None = None) -> str:
        session = await self.store.get_session(session_id)
        if session.status != "busy":
            raise SessionNotBusyError(session_id)
        token = self._active_tokens.get(session_id)
        if token is None:
            raise SessionNotBusyError(session_id)
        token.cancel(reason)
        logger.warning(
            "Request cancelled: session_id={}, request_id={}, reason={}",
            session_id,
            session.current_request_id,
            reason,
        )
        return session.current_request_id or ""

    async def update_session_model(
        self,
        session_id: str,
        provider_id: str,
        model_name: str,
    ) -> SessionInfo:
        await self.provider_store.get_provider(provider_id)
        models = await self.provider_store.list_models(provider_id)
        if not any(m.name == model_name for m in models):
            raise ModelNotFoundError(model_name)
        return await self.store.update_session_model(
            session_id,
            provider_id,
            model_name,
            expected_status=("idle", "error"),
        )

    async def update_session_title(self, session_id: str, title: str) -> bool:
        session = await self.store.get_session(session_id)
        return await self.store.update_session_title(
            session_id,
            title,
            session.user_message_count,
            session.title_auto_generated,
        )

    async def get_system_prompt(self, _session_id: str = "") -> str | None:
        return await self.app_setting_store.get_system_prompt()

    async def set_system_prompt(self, _session_id: str, system_prompt: str) -> None:
        await self.app_setting_store.set_system_prompt(system_prompt)

    async def get_consolidated_memory(
        self, _session_id: str = ""
    ) -> dict[str, Any] | None:
        if (
            self.memory_manager is None
            or self.memory_manager.consolidated_store is None
        ):
            return None
        try:
            return await self.memory_manager.consolidated_store.get()
        except Exception as exc:
            logger.warning("Failed to get consolidated memory: {}", exc)
            return None

    async def trigger_consolidation(self, _session_id: str = "") -> bool:
        if self.memory_manager is None or self.memory_manager.consolidator is None:
            return False
        try:
            return await self.memory_manager.consolidator.try_consolidate()
        except Exception:
            logger.exception("Consolidation failed")
            return False

    async def send_message(
        self,
        session_id: str,
        content: str,
        skills_block: str = "",
    ) -> AsyncGenerator[SSEEvent, None]:
        request_id = self._request_id()
        log = logger.bind(session_id=session_id, request_id=request_id)

        lock_key: str | None = None
        token = CancellationToken()
        self._active_tokens[session_id] = token
        accumulator = MessageAccumulator()
        response_status: SessionStatus = "idle"
        error_message: str | None = None

        try:
            session = await self.store.get_session(session_id)
            if session.status == "busy":
                raise SessionBusyError(session_id, session.current_request_id)
            _, lock_key = await self._state.transition_to_busy(session_id)
            log.info("Message send started: content_len={}", len(content))

            yield event_session_start(session_id, request_id)

            await self.store.update_session_status(
                session_id,
                "busy",
                current_request_id=request_id,
                expected_status="idle",
            )

            provider_config = await self.provider_store.get_provider_config(
                session.provider_id
            )
            models = await self.provider_store.list_models(session.provider_id)
            if not any(m.name == session.model_name for m in models):
                raise ModelNotFoundError(session.model_name)
            provider = await self._provider_factory.create_provider(provider_config)

            messages, region_info = await self._build_messages(
                session, content, session.model_name, skills_block=skills_block
            )

            if region_info is not None:
                compress_model = (
                    self._context_builder.config.compress_model or session.model_name
                )
                summarizer = LLMSummarizer(provider, compress_model)
                await self._event_processor.submit_context_compress(
                    session_id, region_info, summarizer
                )

            runner = AgentRunner(provider)
            spec = AgentRunSpec(
                initial_messages=messages,
                tools=self.tool_registry,
                model=session.model_name,
                max_iterations=session.max_iterations,
                tool_timeout_s=self.tool_timeout_s,
            )
            accumulated_usage: dict[str, int] = {}
            user_message_saved = False

            timeout = self._context_builder.config.request_timeout_seconds
            deadline: float | None = None
            if timeout is not None and timeout > 0:
                deadline = asyncio.get_event_loop().time() + timeout

            async for event in runner.run_stream(
                spec,
                session_id=session_id,
                request_id=request_id,
                cancellation_token=token,
            ):
                if deadline is not None and asyncio.get_event_loop().time() >= deadline:
                    token.cancel(reason="request_timeout")
                    yield event_cancelled("request_timeout")
                    response_status = "idle"
                    break

                if not user_message_saved:
                    await self.store.save_message(session_id, "user", content)
                    user_message_saved = True

                yield event

                if event.type == "content" and event.text:
                    accumulator.on_content(event.text)
                elif event.type == "reasoning" and event.text:
                    accumulator.on_reasoning(event.text)
                elif event.type == "tool_call":
                    args_str = (
                        event.arguments if isinstance(event.arguments, str) else "{}"
                    )
                    accumulator.on_tool_call(
                        event.tool_call_id or "", event.name or "", args_str
                    )
                elif event.type == "tool_result" and event.tool_call_id:
                    accumulator.on_tool_result(
                        event.tool_call_id or "",
                        event.success or False,
                        event.result,
                        event.duration_ms,
                        event.error_message,
                    )
                elif event.type == "error":
                    response_status = "error"
                    error_message = self._extract_error_message(event.error)
                elif event.type == "cancelled":
                    response_status = "idle"
                    error_message = None
                elif event.type == "done":
                    if event.stop_reason == "error":
                        response_status = "error"
                    else:
                        response_status = "idle"
                    if event.usage:
                        accumulated_usage = event.usage
                    if response_status == "idle" and accumulator.assistant_chunks:
                        msg = accumulator.build_assistant_message(accumulated_usage)
                        await self.store.save_message(
                            session_id,
                            "assistant",
                            msg.pop("content"),
                            input_tokens=msg.get("input_tokens"),
                            output_tokens=msg.get("output_tokens"),
                            reasoning_content=msg.get("reasoning_content"),
                            tool_calls=msg.get("tool_calls"),
                        )
                    await self.store.update_session_status(
                        session_id,
                        response_status,
                        current_request_id=None,
                        error_message=error_message,
                        expected_status="busy",
                    )
                    if response_status == "idle" and accumulator.assistant_chunks:
                        await self._event_processor.submit_auto_title(session_id)
                    break

            await self._state.transition_to_idle(session_id, lock_key, error_message)

        except ProviderNotFoundError as exc:
            log.error("Provider not found: {}", exc)
            get_error_log().record(
                level="ERROR",
                source="session_manager:send_message",
                message=str(exc),
                session_id=session_id,
                request_id=request_id,
                error_code="PROVIDER_NOT_FOUND",
                exc_info=exc,
            )
            yield event_error(
                code="PROVIDER_NOT_FOUND",
                message=str(exc),
                error_type="provider_error",
                recoverable=True,
            )
        except ModelNotFoundError as exc:
            log.error("Model not found: {}", exc)
            get_error_log().record(
                level="ERROR",
                source="session_manager:send_message",
                message=str(exc),
                session_id=session_id,
                request_id=request_id,
                error_code="MODEL_NOT_FOUND",
                exc_info=exc,
            )
            yield event_error(
                code="MODEL_NOT_FOUND",
                message=str(exc),
                error_type="internal_error",
                recoverable=True,
            )
        except CancelledError as exc:
            log.warning("Message send cancelled: reason={}", exc.reason)
            await self.store.update_session_status(
                session_id,
                "idle",
                current_request_id=None,
                error_message=None,
                expected_status="busy",
            )
            yield event_error(
                code="CANCELLED",
                message=str(exc),
                details={"reason": exc.reason} if exc.reason else None,
                error_type="session_cancelled",
                recoverable=True,
            )
        except SessionError as exc:
            log.error("Session error: {}", exc)
            yield event_error(
                code="SESSION_ERROR",
                message=str(exc),
                error_type="internal_error",
                recoverable=True,
            )
        except ValueError as exc:
            log.error("Provider configuration error: {}", exc)
            get_error_log().record(
                level="ERROR",
                source="session_manager:send_message",
                message=str(exc),
                session_id=session_id,
                request_id=request_id,
                error_code="PROVIDER_CONFIG_ERROR",
                exc_info=exc,
            )
            yield event_error(
                code="PROVIDER_CONFIG_ERROR",
                message=str(exc),
                error_type="provider_error",
                recoverable=True,
            )
        except Exception as exc:
            log.exception("Unexpected error in send_message: {}", exc)
            get_error_log().record(
                level="CRITICAL",
                source="session_manager:send_message",
                message=f"Unexpected error: {exc}",
                session_id=session_id,
                request_id=request_id,
                error_code="INTERNAL_ERROR",
                exc_info=exc,
            )
            yield event_error(
                code="INTERNAL_ERROR",
                message=f"Unexpected error: {exc}",
                error_type="internal_error",
                recoverable=False,
            )
        finally:
            self._active_tokens.pop(session_id, None)
            try:
                await self._state.force_to_idle(session_id)
                await self.force_reset_stuck_busy(
                    session_id, "Session interrupted unexpectedly"
                )
            except Exception:
                logger.exception("Failed to reset stuck busy session")

    async def force_reset_stuck_busy(
        self, session_id: str, reason: str = "Session reset by stream cleanup"
    ) -> None:
        current = await self.store.get_session(session_id)
        if current.status == "busy":
            logger.warning(
                "Session stuck busy after stream cleanup: session_id={}", session_id
            )
            await self.store.update_session_status(
                session_id,
                "idle",
                current_request_id=None,
                error_message=reason,
            )

    # ── Provider CRUD ────────────────────────────────────────────────────────

    async def list_providers(self) -> list[dict[str, Any]]:
        providers = await self.provider_store.list_providers()
        return [
            {
                "id": p.provider_id,
                "name": p.name,
                "base_url": p.base_url,
                "has_api_key": p.has_api_key,
                "created_at": p.created_at,
            }
            for p in providers
        ]

    async def create_provider(
        self,
        name: str,
        base_url: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        p = await self.provider_store.create_provider(
            name=name,
            base_url=base_url,
            api_key=api_key,
            extra_headers=extra_headers,
            extra_body=extra_body,
        )
        return {
            "id": p.provider_id,
            "name": p.name,
            "base_url": p.base_url,
            "has_api_key": p.has_api_key,
            "created_at": p.created_at,
        }

    async def get_provider(self, provider_id: str) -> dict[str, Any]:
        p = await self.provider_store.get_provider(provider_id)
        return {
            "id": p.provider_id,
            "name": p.name,
            "base_url": p.base_url,
            "has_api_key": p.has_api_key,
            "extra_headers": p.extra_headers,
            "created_at": p.created_at,
        }

    async def update_provider(
        self,
        provider_id: str,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        p = await self.provider_store.update_provider(
            provider_id=provider_id,
            name=name,
            base_url=base_url,
            api_key=api_key,
            extra_headers=extra_headers,
            extra_body=extra_body,
        )
        return {
            "id": p.provider_id,
            "name": p.name,
            "base_url": p.base_url,
            "has_api_key": p.has_api_key,
            "created_at": p.created_at,
        }

    async def delete_provider(self, provider_id: str) -> None:
        await self.provider_store.delete_provider(provider_id)

    async def list_models(self, provider_id: str) -> list[dict[str, Any]]:
        models = await self.provider_store.list_models(provider_id)
        return [
            {"id": m.model_id, "provider_id": m.provider_id, "name": m.name}
            for m in models
        ]

    async def add_model(self, provider_id: str, name: str) -> dict[str, Any]:
        m = await self.provider_store.add_model(provider_id, name)
        return {"id": m.model_id, "provider_id": m.provider_id, "name": m.name}

    async def delete_model(self, model_id: str) -> None:
        await self.provider_store.delete_model(model_id)

    async def test_provider(self, provider_id: str) -> dict[str, Any]:
        config = await self.provider_store.get_provider_config(provider_id)
        models = await self.provider_store.list_models(provider_id)
        if not models:
            return {
                "success": False,
                "message": "No models configured for this provider",
                "latency_ms": None,
            }

        model_name = models[0].name
        start = time.perf_counter()
        try:
            provider = await self._provider_factory.create_provider(config)
            response = await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                model=model_name,
                max_tokens=1,
            )
            latency = int((time.perf_counter() - start) * 1000)
            if hasattr(response, "error_kind") and response.error_kind:
                return {
                    "success": False,
                    "message": f"Provider error: {response.error_kind}",
                    "latency_ms": latency,
                }
            return {
                "success": True,
                "message": "Connection successful",
                "latency_ms": latency,
            }
        except Exception as exc:
            latency = int((time.perf_counter() - start) * 1000)
            exc_str = str(exc)
            if (
                "timeout" in exc_str.lower()
                or "connect" in exc_str.lower()
                or "NameResolutionError" in type(exc).__name__
            ):
                return {
                    "success": False,
                    "message": f"Connection failed: {exc}",
                    "latency_ms": latency,
                }
            return {
                "success": False,
                "message": f"Test failed: {exc}",
                "latency_ms": latency,
            }

    # ── MCP Server CRUD ──────────────────────────────────────────────────────

    async def list_mcp_servers(self) -> list[dict[str, Any]]:
        if self.mcp_server_store is None:
            return []
        rows = await self.mcp_server_store.list_servers()
        return [self._serialize_mcp_server(r) for r in rows]

    async def create_mcp_server(
        self,
        name: str,
        transport_type: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        tool_timeout: int = 30,
        enabled_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
        startup_timeout: int = 30,
        enabled: bool = False,
    ) -> dict[str, Any]:
        if self.mcp_server_store is None:
            raise RuntimeError("MCP server store not available")
        try:
            row = await self.mcp_server_store.create_server(
                name=name,
                transport_type=transport_type,
                command=command,
                args=args,
                env=env,
                url=url,
                headers=headers,
                tool_timeout=tool_timeout,
                enabled_tools=enabled_tools,
                disabled_tools=disabled_tools,
                startup_timeout=startup_timeout,
                enabled=enabled,
            )
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                raise ServerNameConflictError(name) from exc
            raise
        return self._serialize_mcp_server(row)

    async def get_mcp_server(self, server_id: str) -> dict[str, Any]:
        if self.mcp_server_store is None:
            raise RuntimeError("MCP server store not available")
        row = await self.mcp_server_store.get_server(server_id)
        return self._serialize_mcp_server(row)

    async def update_mcp_server(
        self,
        server_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self.mcp_server_store is None:
            raise RuntimeError("MCP server store not available")
        try:
            row = await self.mcp_server_store.update_server(
                server_id=server_id,
                **kwargs,
            )
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                name = kwargs.get("name", "")
                raise ServerNameConflictError(name) from exc
            raise

        if row.enabled and self.mcp_manager is not None:
            await self._hot_swap_mcp()

        return self._serialize_mcp_server(row)

    async def delete_mcp_server(self, server_id: str) -> None:
        if self.mcp_server_store is None:
            return
        row = await self.mcp_server_store.get_server(server_id)
        if row.enabled and self.mcp_manager is not None:
            self.mcp_manager.disable_server(row.name)
        await self.mcp_server_store.delete_server(server_id)

    async def enable_mcp_server(self, server_id: str) -> dict[str, Any]:
        if self.mcp_server_store is None:
            raise RuntimeError("MCP server store not available")
        row = await self.mcp_server_store.update_server(server_id, enabled=True)
        if self.mcp_manager is not None:
            await self._hot_swap_mcp()
        return self._serialize_mcp_server(row)

    async def disable_mcp_server(self, server_id: str) -> dict[str, Any]:
        if self.mcp_server_store is None:
            raise RuntimeError("MCP server store not available")
        row = await self.mcp_server_store.get_server(server_id)
        row = await self.mcp_server_store.update_server(server_id, enabled=False)
        if self.mcp_manager is not None:
            self.mcp_manager.disable_server(row.name)
            await self._hot_swap_mcp()
        return {"id": row.server_id, "connection_status": "disconnected"}

    async def toggle_mcp_server(self, server_id: str) -> dict[str, Any]:
        if self.mcp_server_store is None:
            raise RuntimeError("MCP server store not available")
        row = await self.mcp_server_store.get_server(server_id)
        if row.enabled:
            return await self.disable_mcp_server(server_id)
        return await self.enable_mcp_server(server_id)

    async def reconnect_mcp_server(self, server_id: str) -> dict[str, Any]:
        if self.mcp_server_store is None:
            raise RuntimeError("MCP server store not available")
        row = await self.mcp_server_store.get_server(server_id)
        if self.mcp_manager is not None:
            self.mcp_manager.disable_server(row.name)
            await self._hot_swap_mcp()
        return self._serialize_mcp_server(row)

    async def test_mcp_server(self, server_id: str) -> dict[str, Any]:
        if self.mcp_server_store is None:
            return {"success": False, "message": "MCP not available"}
        row = await self.mcp_server_store.get_server(server_id)
        from laffybot_agent_runtime.tools.mcp.client import (
            McpClient,
            McpError,
            McpProtocolError,
        )
        from laffybot_agent_runtime.tools.mcp.manager import (
            MCPServerConfig,
            create_transport,
        )
        from laffybot_agent_runtime.tools.mcp.transports import TransportError

        config = MCPServerConfig(
            name=row.name,
            transport_type=row.transport_type,
            command=row.command,
            args=row.args,
            url=row.url,
            tool_timeout=row.tool_timeout,
            enabled_tools=row.enabled_tools,
            disabled_tools=row.disabled_tools,
            startup_timeout=row.startup_timeout,
            enabled=row.enabled,
        )

        try:
            transport = create_transport(config)
            await asyncio.wait_for(transport.connect(), timeout=config.startup_timeout)
            client = McpClient(transport)
            await asyncio.wait_for(client.initialize(), timeout=config.startup_timeout)
            tools = await asyncio.wait_for(
                client.list_tools(), timeout=config.startup_timeout
            )
            await client.close()
            return {
                "success": True,
                "message": f"Connected successfully, found {len(tools)} tool(s)",
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": f"Connection timed out after {config.startup_timeout}s",
            }
        except TransportError as exc:
            return {"success": False, "message": f"Transport error: {exc}"}
        except McpProtocolError as exc:
            return {"success": False, "message": f"Protocol error: {exc}"}
        except McpError as exc:
            return {
                "success": False,
                "message": f"Server error (code {exc.code}): {exc}",
            }
        except Exception as exc:
            return {"success": False, "message": f"Test failed: {exc}"}

    def _serialize_mcp_server(self, row: Any) -> dict[str, Any]:
        connection_status = "disconnected"
        tool_count = 0
        if self.mcp_manager is not None:
            status = self.mcp_manager.get_status(row.name)
            connection_status = status.get("status", "disconnected")
            tool_count = status.get("tool_count", 0)
        return {
            "id": row.server_id,
            "name": row.name,
            "transport_type": row.transport_type,
            "command": row.command,
            "url": row.url,
            "has_env": row.has_env,
            "has_headers": row.has_headers,
            "tool_timeout": row.tool_timeout,
            "enabled_tools": row.enabled_tools,
            "disabled_tools": row.disabled_tools,
            "startup_timeout": row.startup_timeout,
            "enabled": row.enabled,
            "connection_status": connection_status,
            "tool_count": tool_count,
            "created_at": row.created_at,
        }

    async def _hot_swap_mcp(self) -> None:
        if self.mcp_server_store is None or self.mcp_manager is None:
            return
        from laffybot_agent_runtime.tools.mcp.manager import MCPServerConfig

        raw_configs = await self.mcp_server_store.get_enabled_server_configs()
        configs = [MCPServerConfig(**c) for c in raw_configs]
        await self.mcp_manager.hot_swap(configs)

    # ── Tool management ───────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "read_only": tool.read_only,
                "enabled": self.tool_registry.is_enabled(tool.name),
            }
            for tool in sorted(self.tool_registry._tools.values(), key=lambda t: t.name)
        ]

    async def enable_tool(self, name: str) -> dict[str, Any]:
        self.tool_registry.enable(name)
        return {"name": name, "enabled": True}

    async def disable_tool(self, name: str) -> dict[str, Any]:
        self.tool_registry.disable(name)
        return {"name": name, "enabled": False}

    # ── Skill management ─────────────────────────────────────────────────────

    async def get_skills_path(self) -> str | None:
        return await self.app_setting_store.get_skills_path()

    async def set_skills_path(self, path: str) -> list[dict[str, Any]]:
        await self.app_setting_store.set_skills_path(path)
        if self.skills_loader is not None:
            self.skills_loader.refresh()
        return await self.list_skills()

    async def list_skills(self) -> list[dict[str, Any]]:
        skills_path = await self.app_setting_store.get_skills_path()
        if not skills_path or self.skills_loader is None:
            return []

        all_skills = self.skills_loader.discover_skills(skills_path)
        enabled = (
            await self.skill_registry.get_enabled_skills()
            if self.skill_registry is not None
            else set()
        )
        return [
            {
                "name": s.name,
                "description": s.description,
                "enabled": s.name in enabled,
                "has_resources": s.has_resources,
            }
            for s in all_skills
        ]

    async def set_skill_enabled(self, name: str, enabled: bool) -> None:
        if self.skill_registry is not None:
            await self.skill_registry.set_enabled(name, enabled)

    # ── Settings ──────────────────────────────────────────────────────────────

    async def get_default_session_config(self) -> dict[str, str] | None:
        config = await self.app_setting_store.get_default_session_config()
        if config is None:
            return None
        return {"provider_id": config.provider_id, "model_name": config.model_name}

    async def set_default_session_config(
        self, provider_id: str, model_name: str
    ) -> dict[str, str]:
        await self.provider_store.get_provider(provider_id)
        models = await self.provider_store.list_models(provider_id)
        if not any(m.name == model_name for m in models):
            raise ModelNotFoundError(model_name)
        await self.app_setting_store.set_default_session_config(provider_id, model_name)
        return {"provider_id": provider_id, "model_name": model_name}

    async def delete_default_session_config(self) -> None:
        await self.app_setting_store.delete_default_session_config()

    async def get_summary_model(self) -> dict[str, str] | None:
        config = await self.app_setting_store.get_summary_model()
        if config is None:
            return None
        return {"provider_id": config.provider_id, "model_name": config.model_name}

    async def set_summary_model(
        self, provider_id: str, model_name: str
    ) -> dict[str, str]:
        await self.provider_store.get_provider(provider_id)
        models = await self.provider_store.list_models(provider_id)
        if not any(m.name == model_name for m in models):
            raise ModelNotFoundError(model_name)
        await self.app_setting_store.set_summary_model(provider_id, model_name)
        return {"provider_id": provider_id, "model_name": model_name}

    async def delete_summary_model(self) -> None:
        await self.app_setting_store.delete_summary_model()

    async def get_extract_model(self) -> dict[str, str] | None:
        config = await self.app_setting_store.get_extract_model()
        if config is None:
            return None
        return {"provider_id": config.provider_id, "model_name": config.model_name}

    async def set_extract_model(
        self, provider_id: str, model_name: str
    ) -> dict[str, str]:
        await self.provider_store.get_provider(provider_id)
        models = await self.provider_store.list_models(provider_id)
        if not any(m.name == model_name for m in models):
            raise ModelNotFoundError(model_name)
        await self.app_setting_store.set_extract_model(provider_id, model_name)
        return {"provider_id": provider_id, "model_name": model_name}

    async def delete_extract_model(self) -> None:
        await self.app_setting_store.delete_extract_model()

    async def get_consolidation_model(self) -> dict[str, str] | None:
        config = await self.app_setting_store.get_consolidation_model()
        if config is None:
            return None
        return {"provider_id": config.provider_id, "model_name": config.model_name}

    async def set_consolidation_model(
        self, provider_id: str, model_name: str
    ) -> dict[str, str]:
        await self.provider_store.get_provider(provider_id)
        models = await self.provider_store.list_models(provider_id)
        if not any(m.name == model_name for m in models):
            raise ModelNotFoundError(model_name)
        await self.app_setting_store.set_consolidation_model(provider_id, model_name)
        return {"provider_id": provider_id, "model_name": model_name}

    async def delete_consolidation_model(self) -> None:
        await self.app_setting_store.delete_consolidation_model()

    # ── Memory ────────────────────────────────────────────────────────────────

    async def list_memories(
        self, limit: int = 20, offset: int = 0, search: str | None = None
    ) -> dict[str, Any]:
        if self.memory_store is None:
            return {"memories": [], "total": 0, "limit": limit, "offset": offset}
        memories, total = await self.memory_store.list_memories(
            limit=limit, offset=offset, search=search
        )
        return {
            "memories": memories,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        if self.memory_store is None:
            return None
        return await self.memory_store.get_memory(memory_id)

    async def get_memory_source(self, memory_id: str) -> dict[str, Any] | None:
        if self.memory_store is None:
            return None
        memory = await self.memory_store.get_memory(memory_id)
        if memory is None:
            return None
        session_id = memory["session_id"]
        try:
            session = await self.store.get_session(session_id)
        except Exception:
            session = None
            logger.debug("Memory source session not found: session_id={}", session_id)
        messages = await self.store.get_messages(session_id, limit=1000)
        return {
            "session_id": session_id,
            "session_title": session.title if session else None,
            "messages": messages,
        }

    async def delete_memory(self, memory_id: str) -> None:
        if self.memory_store is not None:
            await self.memory_store.delete_memory(memory_id)

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_error_message(error: dict[str, Any] | None) -> str | None:
        if not error:
            return None
        message = error.get("message")
        return message if isinstance(message, str) else None

    async def _build_messages(
        self,
        session: SessionInfo,
        current_message: str,
        model: str | None = None,
        skills_block: str = "",
    ) -> tuple[list[dict[str, Any]], Any]:
        history = await self.store.get_messages(session.session_id)

        extra_vars: dict[str, Any] = {}
        if self.memory_manager is not None:
            try:
                memories = await self.memory_manager.get_memories_for_injection(
                    top_n=self.memory_manager.config.top_n_for_injection,
                    max_tokens=self.memory_manager.config.max_memory_tokens,
                )
                extra_vars["memories"] = memories
            except Exception:
                logger.warning(
                    "Failed to load memories for injection: session_id={}",
                    session.session_id,
                )
                extra_vars["memories"] = []

        extra_vars["skills_block"] = skills_block

        return await self._context_builder.build_messages(
            session_id=session.session_id,
            system_prompt=self._context_builder.config.system_prompt,
            history=history,
            current_message=current_message,
            model=model or session.model_name,
            created_at=session.created_at,
            **extra_vars,
        )
