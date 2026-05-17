"""Simplified agent runner for tool-using agents."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from loguru import logger

from laffybot.agent.cancellation import CancellationToken, CancelledError
from laffybot.agent.events import (
    ERROR_INTERNAL,
    ERROR_LLM,
    SSEEvent,
    event_cancelled,
    event_content,
    event_done,
    event_error,
    event_reasoning,
    event_session_start,
    event_tool_call,
    event_tool_result,
)
from laffybot.agent.tools.errors import ToolError
from laffybot.agent.tools.registry import ToolRegistry
from laffybot.providers.base import BaseProvider
from laffybot.providers.types import LLMResponse, StreamChunk, ToolCallRequest


@dataclass(slots=True)
class AgentRunSpec:
    """Configuration for a single agent execution."""

    initial_messages: list[dict[str, Any]]
    tools: ToolRegistry
    model: str
    max_iterations: int
    max_tool_result_chars: int = 10000
    temperature: float | None = None
    max_tokens: int | None = None
    tool_timeout_s: int = 120


class AgentRunner:
    """Run a tool-capable LLM loop."""

    def __init__(self, provider: BaseProvider):
        self.provider = provider

    async def run_stream(
        self,
        spec: AgentRunSpec,
        session_id: str | None = None,
        request_id: str | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Execute agent with streaming SSE event output.

        This is the primary execution method, yielding SSE events as the
        agent processes the request. Replaces the synchronous run() method.

        Args:
            spec: Agent execution specification.
            session_id: Optional session ID for session_start event.
            request_id: Optional request ID for session_start event. If not provided, one is generated.
            cancellation_token: Optional token for cancellation support.

        Yields:
            SSEEvent objects representing the execution flow.

        Event sequence:
            session_start -> (content | reasoning)* -> [tool_call -> tool_result]+ -> done
        """
        token = cancellation_token or CancellationToken()
        session_id = session_id or str(uuid.uuid4())
        request_id = request_id or f"req_{uuid.uuid4().hex[:12]}"

        log = logger.bind(session_id=session_id, request_id=request_id)
        log.info(
            "Agent run started: model={}, max_iterations={}",
            spec.model,
            spec.max_iterations,
        )

        messages = list(spec.initial_messages)
        tools_used: list[str] = []
        usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        stop_reason: str = "completed"

        # Event queue for coordinating streaming callbacks
        event_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()

        # Emit session_start
        yield event_session_start(session_id, request_id)

        try:
            for iteration in range(spec.max_iterations):
                # Cancellation checkpoint
                token.check()

                log.debug("LLM request started: iteration={}", iteration)

                # Run LLM streaming in background task,
                # consume events concurrently in real-time
                task = asyncio.create_task(
                    self._request_model_stream_with_events(
                        spec, messages, event_queue, token
                    )
                )

                while True:
                    event = await event_queue.get()
                    if event is None:
                        break
                    yield event

                response = await task
                self._accumulate_usage(usage, response.usage)

                log.debug(
                    "LLM response received: content_len={}, tool_calls={}",
                    len(response.content or ""),
                    len(response.tool_calls or []),
                )

                # Handle tool calls
                if response.tool_calls:
                    assistant_message = self._build_assistant_message(
                        response.content or "",
                        response.tool_calls,
                    )
                    messages.append(assistant_message)
                    tools_used.extend(tc.name for tc in response.tool_calls)

                    # Execute tools and emit events
                    for tool_call in response.tool_calls:
                        # Cancellation checkpoint before each tool
                        token.check()

                        # Emit tool_call event
                        yield event_tool_call(
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                            arguments=tool_call.arguments,
                        )

                        # Execute tool with timing
                        start_time = time.perf_counter()
                        log.debug("Tool execution started: name={}", tool_call.name)
                        try:
                            result = await asyncio.wait_for(
                                spec.tools.execute(tool_call.name, tool_call.arguments),
                                timeout=spec.tool_timeout_s,
                            )
                            success = True
                            error_message = None
                        except asyncio.TimeoutError:
                            logger.warning(
                                "Tool {} timed out after {}s",
                                tool_call.name,
                                spec.tool_timeout_s,
                            )
                            result = f"Error: Tool '{tool_call.name}' timed out after {spec.tool_timeout_s}s"
                            success = False
                            error_message = f"Tool '{tool_call.name}' timed out after {spec.tool_timeout_s}s"
                        except CancelledError:
                            raise
                        except ToolError as exc:
                            logger.warning("Tool {} failed: {}", tool_call.name, exc)
                            result = f"Error: {exc}"
                            success = False
                            error_message = str(exc)
                        except Exception as exc:
                            logger.exception("Tool {} failed", tool_call.name)
                            result = f"Error: {type(exc).__name__}: {exc}"
                            success = False
                            error_message = str(exc)

                        duration_ms = int((time.perf_counter() - start_time) * 1000)
                        log.debug(
                            "Tool execution completed: name={}, duration_ms={}, success={}",
                            tool_call.name,
                            duration_ms,
                            success,
                        )

                        # Normalize result for message history
                        normalized_result = self._normalize_tool_result(
                            spec, tool_call.name, result
                        )

                        # Emit tool_result event
                        yield event_tool_result(
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                            result=normalized_result,
                            success=success,
                            duration_ms=duration_ms,
                            error_message=error_message,
                        )

                        # Append to message history
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_call.name,
                                "content": normalized_result,
                            }
                        )

                    continue  # Next iteration

                # No tool calls - check for final content
                content = response.content or ""
                if not content.strip():
                    logger.warning(
                        "Empty response on turn {} for model {}",
                        iteration,
                        spec.model,
                    )
                    continue

                # Final response
                messages.append(self._build_assistant_message(content, []))
                break

            else:
                # Loop exhausted
                stop_reason = "max_iterations"

        except CancelledError as e:
            # Cancellation - emit cancelled event
            log.warning("Agent run cancelled: reason={}", e.reason)
            yield event_cancelled(e.reason)
            stop_reason = "cancelled"
        except Exception as exc:
            # Error - emit error event
            logger.exception("Error during agent execution")
            error_code = (
                ERROR_LLM
                if "api" in str(type(exc).__name__).lower()
                else ERROR_INTERNAL
            )
            yield event_error(
                code=error_code,
                message=str(exc),
                details={"error_type": type(exc).__name__},
            )
            stop_reason = "error"

        # Emit done event
        log.info("Agent run completed: stop_reason={}, usage={}", stop_reason, usage)
        yield event_done(
            stop_reason=stop_reason,  # type: ignore
            usage=usage if usage["prompt_tokens"] > 0 else None,
            tools_used=tools_used if tools_used else None,
        )

    async def _request_model_stream_with_events(
        self,
        spec: AgentRunSpec,
        messages: list[dict[str, Any]],
        event_queue: asyncio.Queue[SSEEvent | None],
        cancellation_token: CancellationToken,
    ) -> LLMResponse:
        """Request LLM with streaming, putting content/reasoning events in queue."""
        try:
            cancellation_token.check()

            async def on_chunk(chunk: StreamChunk) -> None:
                if chunk.content:
                    await event_queue.put(event_content(chunk.content))
                if chunk.reasoning:
                    await event_queue.put(event_reasoning(chunk.reasoning))
                # Tool call deltas are accumulated by provider, not emitted here

            response = await self.provider.chat_completion_stream(
                messages=messages,
                model=spec.model,
                on_chunk=on_chunk,
                tools=spec.tools.get_definitions(),
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
            )
            return response
        finally:
            await event_queue.put(None)

    def _normalize_tool_result(
        self,
        spec: AgentRunSpec,
        tool_name: str,
        result: Any,
    ) -> Any:
        if result is None:
            return ""
        if isinstance(result, str):
            if len(result) > spec.max_tool_result_chars:
                return result[: spec.max_tool_result_chars] + "\n...[truncated]"
            return result
        return str(result)

    @staticmethod
    def _build_assistant_message(
        content: str,
        tool_calls: list[ToolCallRequest],
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }
        if tool_calls:
            message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in tool_calls
            ]
        return message

    @staticmethod
    def _accumulate_usage(target: dict[str, int], addition: dict[str, int]) -> None:
        for key, value in addition.items():
            target[key] = target.get(key, 0) + value
