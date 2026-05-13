"""Session orchestration for message handling and stream execution."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from laffybot.agent.cancellation import CancellationToken, CancelledError
from laffybot.agent.events import SSEEvent, event_error
from laffybot.agent.runner import AgentRunner, AgentRunSpec
from laffybot.agent.tools.registry import ToolRegistry
from laffybot.config import ContextConfig
from laffybot.context import ContextBuilder, SimpleContextBuilder
from laffybot.providers.base import BaseProvider
from laffybot.session.errors import (
    SessionBusyError,
    SessionNotBusyError,
)
from laffybot.session.models import SessionInfo, SessionStatus
from laffybot.session.store import SessionStore


class SessionManager:
    """Coordinate session state, storage and agent execution."""

    def __init__(
        self,
        store: SessionStore,
        tool_registry: ToolRegistry,
        provider_factory: Callable[[str], BaseProvider],
        context_config: ContextConfig | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.store = store
        self.tool_registry = tool_registry
        self.provider_factory = provider_factory
        self._locks: dict[str, asyncio.Lock] = {}
        self._active_tokens: dict[str, CancellationToken] = {}

        # Initialize context builder
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
        model: str,
        system_prompt: str | None = None,
        max_iterations: int = 10,
    ) -> SessionInfo:
        session_id = str(uuid.uuid4())
        return await self.store.create_session(
            session_id=session_id,
            model=model,
            system_prompt=system_prompt,
            max_iterations=max_iterations,
        )

    async def get_session_info(self, session_id: str) -> SessionInfo:
        return await self.store.get_session(session_id)

    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SessionInfo], int]:
        return await self.store.list_sessions(status=status, limit=limit, offset=offset)

    async def delete_session(self, session_id: str) -> None:
        session = await self.store.get_session(session_id)
        if session.status == "busy":
            raise SessionBusyError(session_id, session.current_request_id)
        await self.store.delete_session(session_id)

    async def cancel_request(self, session_id: str, reason: str | None = None) -> str:
        session = await self.store.get_session(session_id)
        if session.status != "busy":
            raise SessionNotBusyError(session_id)
        token = self._active_tokens.get(session_id)
        if token is None:
            raise SessionNotBusyError(session_id)
        token.cancel(reason)
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

            try:
                await self.store.update_session_status(
                    session_id,
                    "busy",
                    current_request_id=request_id,
                    expected_status="idle",
                )
                await self.store.save_message(session_id, "user", content)

                messages = await self._build_messages(session, content)
                provider = self.provider_factory(session.model)
                runner = AgentRunner(provider)
                spec = AgentRunSpec(
                    initial_messages=messages,
                    tools=self.tool_registry,
                    model=session.model,
                    max_iterations=session.max_iterations,
                )

                # Track usage for token persistence
                accumulated_usage: dict[str, int] = {}

                async for event in runner.run_stream(
                    spec,
                    session_id=session_id,
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
                        # Extract usage from done event
                        if event.usage:
                            accumulated_usage = event.usage
                        if response_status == "idle" and assistant_chunks:
                            # Extract token counts from usage
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
                        break
            except CancelledError as exc:
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

    async def _build_messages(
        self,
        session: SessionInfo,
        current_message: str,
    ) -> list[dict[str, Any]]:
        """Build complete message context using ContextBuilder.

        Delegates to ContextBuilder for:
        - System prompt assembly
        - History loading
        - Capacity control
        """
        history = await self.store.get_messages(session.session_id)
        return await self._context_builder.build_messages(
            session_id=session.session_id,
            system_prompt=session.system_prompt,
            history=history,
            current_message=current_message,
            model=session.model,
            created_at=session.created_at,
        )

    @staticmethod
    def _extract_error_message(error: dict[str, Any] | None) -> str | None:
        if not error:
            return None
        message = error.get("message")
        return message if isinstance(message, str) else None
