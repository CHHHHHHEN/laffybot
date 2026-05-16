"""Session orchestration for message handling and stream execution."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from laffybot.agent.cancellation import CancellationToken, CancelledError
from laffybot.agent.events import SSEEvent, event_error
from laffybot.agent.runner import AgentRunner, AgentRunSpec
from laffybot.agent.title_generator import TitleGenerator
from laffybot.agent.tools.registry import ToolRegistry
from laffybot.config import ContextConfig
from laffybot.context import ContextBuilder, SimpleContextBuilder
from laffybot.memory import MemoryManager
from laffybot.providers.errors import ModelNotFoundError, ProviderNotFoundError
from laffybot.providers.openai import OpenAIProvider
from laffybot.session.app_setting_store import AppSettingStore
from laffybot.session.errors import (
    SessionBusyError,
    SessionNotBusyError,
)
from laffybot.session.models import SessionInfo, SessionStatus
from laffybot.session.provider_store import ProviderStore
from laffybot.session.store import SessionStore


class SessionManager:
    """Coordinate session state, storage and agent execution."""

    def __init__(
        self,
        store: SessionStore,
        provider_store: ProviderStore,
        app_setting_store: AppSettingStore,
        tool_registry: ToolRegistry,
        context_config: ContextConfig | None = None,
        context_builder: ContextBuilder | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self.store = store
        self.provider_store = provider_store
        self.app_setting_store = app_setting_store
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self._locks: dict[str, asyncio.Lock] = {}
        self._active_tokens: dict[str, CancellationToken] = {}

        if context_builder is not None:
            self._context_builder = context_builder
        else:
            config = context_config or ContextConfig()
            self._context_builder = SimpleContextBuilder(config)

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    @staticmethod
    def _request_id() -> str:
        return f"req_{uuid.uuid4().hex[:12]}"

    async def create_session(
        self,
        max_iterations: int = 10,
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
        return session

    async def get_session_info(self, session_id: str) -> SessionInfo:
        return await self.store.get_session(session_id)

    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SessionInfo], int]:
        return await self.store.list_sessions(status=status, limit=limit, offset=offset)

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

    async def send_message(
        self,
        session_id: str,
        content: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        lock = self._lock_for(session_id)
        async with lock:
            session = await self.store.get_session(session_id)
            if session.status == "busy":
                raise SessionBusyError(session_id, session.current_request_id)

            request_id = self._request_id()
            token = CancellationToken()
            self._active_tokens[session_id] = token
            assistant_chunks: list[str] = []
            response_status: SessionStatus = "idle"
            error_message: str | None = None

            log = logger.bind(session_id=session_id, request_id=request_id)
            log.info("Message send started: content_len={}", len(content))

            try:
                provider_config = await self.provider_store.get_provider_config(
                    session.provider_id
                )
                models = await self.provider_store.list_models(session.provider_id)
                if not any(m.name == session.model_name for m in models):
                    raise ModelNotFoundError(session.model_name)

                await self.store.update_session_status(
                    session_id,
                    "busy",
                    current_request_id=request_id,
                    expected_status="idle",
                )
                log.debug("Session status changed: idle -> busy")
                await self.store.save_message(session_id, "user", content)

                messages = await self._build_messages(
                    session, content, session.model_name
                )
                provider = OpenAIProvider(provider_config)
                runner = AgentRunner(provider)
                spec = AgentRunSpec(
                    initial_messages=messages,
                    tools=self.tool_registry,
                    model=session.model_name,
                    max_iterations=session.max_iterations,
                )

                accumulated_usage: dict[str, int] = {}

                async for event in runner.run_stream(
                    spec,
                    session_id=session_id,
                    request_id=request_id,
                    cancellation_token=token,
                ):
                    yield event
                    if event.type == "content" and event.text:
                        assistant_chunks.append(event.text)
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
                        if response_status == "idle" and assistant_chunks:
                            input_tokens = accumulated_usage.get("prompt_tokens")
                            output_tokens = accumulated_usage.get("completion_tokens")
                            await self.store.save_message(
                                session_id,
                                "assistant",
                                "".join(assistant_chunks),
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                            )
                        await self.store.update_session_status(
                            session_id,
                            response_status,
                            current_request_id=None,
                            error_message=error_message,
                            expected_status="busy",
                        )
                        # Trigger auto-title generation asynchronously
                        if response_status == "idle" and assistant_chunks:
                            asyncio.create_task(self._trigger_auto_title(session_id))
                            # Trigger memory extraction asynchronously
                            asyncio.create_task(self._trigger_extract(session_id))
                        break
            except ProviderNotFoundError as exc:
                log.error("Provider not found: {}", exc)
                yield event_error(
                    code="PROVIDER_NOT_FOUND",
                    message=str(exc),
                )
            except ModelNotFoundError as exc:
                log.error("Model not found: {}", exc)
                yield event_error(
                    code="MODEL_NOT_FOUND",
                    message=str(exc),
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
                )
            except Exception as exc:
                log.error("Message send failed: error={}", exc)
                await self.store.update_session_status(
                    session_id,
                    "error",
                    current_request_id=None,
                    error_message=str(exc),
                    expected_status="busy",
                )
                yield event_error(
                    code="INTERNAL_ERROR",
                    message=str(exc),
                    details={"error_type": type(exc).__name__},
                )
            finally:
                self._active_tokens.pop(session_id, None)
                try:
                    current = await self.store.get_session(session_id)
                    if current.status == "busy":
                        await self.store.update_session_status(
                            session_id,
                            "idle",
                            current_request_id=None,
                            error_message="Session interrupted unexpectedly",
                        )
                except Exception:
                    logger.exception("Failed to reset stuck busy session")

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

    async def _build_messages(
        self,
        session: SessionInfo,
        current_message: str,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
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

        return await self._context_builder.build_messages(
            session_id=session.session_id,
            system_prompt=self._context_builder.config.system_prompt,
            history=history,
            current_message=current_message,
            model=model or session.model_name,
            created_at=session.created_at,
            **extra_vars,
        )

    @staticmethod
    def _extract_error_message(error: dict[str, Any] | None) -> str | None:
        if not error:
            return None
        message = error.get("message")
        return message if isinstance(message, str) else None

    async def _trigger_auto_title(self, session_id: str) -> None:
        """Trigger automatic title generation for a session.

        This method runs asynchronously after message completion.
        It implements:
        - First-time title generation when title is None
        - Re-generation when user_message_count increments by >= 5
        - Optimistic locking to prevent race conditions
        """
        try:
            session = await self.store.get_session(session_id)

            # Determine if we should generate or regenerate
            should_generate = False
            is_first_time = session.title is None

            if is_first_time:
                # First-time generation
                # Check if we have assistant content (not just tool calls)
                messages = await self.store.get_messages(session_id)
                user_msgs = [m for m in messages if m["role"] == "user"]
                assistant_msgs = [m for m in messages if m["role"] == "assistant"]

                if not user_msgs or not assistant_msgs:
                    return  # Not enough messages yet

                # Check if first assistant message has content
                first_assistant = assistant_msgs[0]
                if not first_assistant.get("content"):
                    return  # First assistant message was tool_call only

                should_generate = True
            elif session.title_auto_generated:
                # Check for re-generation threshold
                msg_increment = (
                    session.user_message_count
                    - session.title_updated_at_user_message_count
                )
                if msg_increment >= 5:
                    should_generate = True

            if not should_generate:
                return

            # Get summary model or fallback to session model
            summary_config = await self.app_setting_store.get_summary_model()

            if summary_config is None:
                # No summary model configured
                if is_first_time:
                    # Fallback: truncate first user message
                    messages = await self.store.get_messages(session_id)
                    user_msgs = [m for m in messages if m["role"] == "user"]
                    if user_msgs and user_msgs[0].get("content"):
                        title = TitleGenerator.truncate_title_from_message(
                            user_msgs[0]["content"]
                        )
                        success = await self.store.update_session_title(
                            session_id,
                            title,
                            session.user_message_count,
                            False,  # expected_title_auto_generated
                        )
                        if success:
                            # Publish title_update event for fallback title
                            from laffybot.api.event_bus import get_event_bus

                            bus = get_event_bus()
                            await bus.publish(
                                "title_update",
                                {"session_id": session_id, "title": title},
                            )
                return

            # Get provider for title generation
            provider_config = await self.provider_store.get_provider_config(
                summary_config.provider_id
            )
            provider = OpenAIProvider(provider_config)
            generator = TitleGenerator(provider, summary_config.model_name)

            # Get all messages for context
            messages = await self.store.get_messages(session_id, limit=1000)

            # Generate title
            generated_title = await generator.generate_title(messages)

            if generated_title is None:
                return  # Generation failed, silent ignore

            # Optimistic lock write
            success = await self.store.update_session_title(
                session_id,
                generated_title,
                session.user_message_count,
                session.title_auto_generated,
            )

            if success:
                logger.info(
                    "Auto-title generated: session_id={}, title={}",
                    session_id,
                    generated_title,
                )
                # Publish title_update event to global event bus
                from laffybot.api.event_bus import get_event_bus

                bus = get_event_bus()
                await bus.publish(
                    "title_update",
                    {"session_id": session_id, "title": generated_title},
                )
            else:
                logger.debug(
                    "Auto-title write skipped (optimistic lock): session_id={}",
                    session_id,
                )

        except Exception as e:
            logger.warning(
                "Auto-title generation failed: session_id={}, error={}",
                session_id,
                str(e),
            )

    async def _trigger_extract(self, session_id: str) -> None:
        """Trigger asynchronous memory extraction for a completed session."""
        if self.memory_manager is None:
            return

        try:
            messages = await self.store.get_messages(session_id, limit=1000)

            # Get extract model from app settings
            extract_config = await self.app_setting_store.get_extract_model()

            if extract_config is None:
                logger.debug(
                    "Memory extraction skipped (no extract model): session_id={}",
                    session_id,
                )
                return

            provider_config = await self.provider_store.get_provider_config(
                extract_config.provider_id
            )
            provider = OpenAIProvider(provider_config)

            await self.memory_manager.extract(
                session_id=session_id,
                messages=messages,
                provider=provider,
                model=extract_config.model_name,
            )

        except Exception as e:
            logger.warning(
                "Memory extraction failed: session_id={}, error={}",
                session_id,
                str(e),
            )
