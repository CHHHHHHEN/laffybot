"""Tests for AgentRunner and AgentRunSpec."""

from __future__ import annotations

from typing import Any

import pytest

from laffybot.agent_runtime.cancellation import CancellationToken
from laffybot.agent_runtime.providers.types import (
    StreamChunk,
    SuccessLLMResponse,
    ToolCallRequest,
)
from laffybot.agent_runtime.runner import AgentRunner, AgentRunSpec
from laffybot.agent_runtime.tools.base import Tool
from laffybot.agent_runtime.tools.registry import ToolRegistry


class TestAgentRunSpec:
    def test_default_values(self, tool_registry: ToolRegistry) -> None:
        spec = AgentRunSpec(
            initial_messages=[],
            tools=tool_registry,
            model="gpt-4",
            max_iterations=10,
        )
        assert spec.max_tool_result_chars == 10000
        assert spec.temperature is None
        assert spec.max_tokens is None
        assert spec.tool_timeout_s == 120

    def test_custom_values(self, tool_registry: ToolRegistry) -> None:
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": "hi"}],
            tools=tool_registry,
            model="gpt-4",
            max_iterations=5,
            max_tool_result_chars=500,
            temperature=0.5,
            max_tokens=2048,
            tool_timeout_s=60,
        )
        assert spec.max_tool_result_chars == 500
        assert spec.temperature == 0.5
        assert spec.max_tokens == 2048
        assert spec.tool_timeout_s == 60


def _make_tool(name: str, fn: Any) -> Tool:
    class _DynamicTool(Tool):
        @property
        def name(self) -> str:
            return name

        @property
        def description(self) -> str:
            return f"tool {name}"

        async def execute(self, **kwargs: Any) -> Any:
            return fn(**kwargs)

    return _DynamicTool()


class TestTextOnlyResponse:
    @pytest.mark.asyncio
    async def test_session_start_then_content_then_done(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_response(SuccessLLMResponse(content="Hello"))
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        assert events[0].type == "session_start"
        assert events[-1].type == "done"
        assert events[-1].stop_reason == "completed"
        assert all(e.type != "tool_call" for e in events)

    @pytest.mark.asyncio
    async def test_content_chunks_yielded(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_response(SuccessLLMResponse(content="Hello"))
        p.set_stream_chunks(
            [StreamChunk(content="Hel"), StreamChunk(content="lo")],
        )
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        contents = [e for e in events if e.type == "content"]
        assert len(contents) == 2
        assert contents[0].text == "Hel"
        assert contents[1].text == "lo"

    @pytest.mark.asyncio
    async def test_reasoning_chunks_yielded(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_response(SuccessLLMResponse(content="answer"))
        p.set_stream_chunks([StreamChunk(reasoning="thinking...")])
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        reasoning = [e for e in events if e.type == "reasoning"]
        assert len(reasoning) == 1
        assert reasoning[0].text == "thinking..."

    @pytest.mark.asyncio
    async def test_session_id_and_request_id_passthrough(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_response(SuccessLLMResponse(content="hi"))
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [
            e
            async for e in runner.run_stream(spec, session_id="sid1", request_id="req1")
        ]
        assert events[0].session_id == "sid1"
        assert events[0].request_id == "req1"

    @pytest.mark.asyncio
    async def test_auto_generates_ids_when_not_provided(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_response(SuccessLLMResponse(content="hi"))
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        assert events[0].session_id is not None
        assert len(events[0].session_id) > 0
        assert events[0].request_id is not None


class TestToolCallResponses:
    @pytest.mark.asyncio
    async def test_single_tool_call(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_responses(
            [
                SuccessLLMResponse(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c1", name="mock_tool", arguments={"a": 1})
                    ],
                ),
                SuccessLLMResponse(content="done"),
            ]
        )
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        tool_calls = [e for e in events if e.type == "tool_call"]
        tool_results = [e for e in events if e.type == "tool_result"]
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "mock_tool"
        assert tool_calls[0].arguments == {"a": 1}
        assert len(tool_results) == 1
        assert tool_results[0].success is True
        boundaries = [e for e in events if e.type == "iteration_boundary"]
        assert len(boundaries) == 1

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_responses(
            [
                SuccessLLMResponse(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c1", name="mock_tool", arguments={"x": 1}),
                        ToolCallRequest(id="c2", name="mock_tool", arguments={"y": 2}),
                    ],
                ),
                SuccessLLMResponse(content="done"),
            ]
        )
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        assert len([e for e in events if e.type == "tool_call"]) == 2

    @pytest.mark.asyncio
    async def test_tool_then_text(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_responses(
            [
                SuccessLLMResponse(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c1", name="mock_tool", arguments={})
                    ],
                ),
                SuccessLLMResponse(content="final answer"),
            ]
        )
        spec = AgentRunSpec([], tool_registry, "test", 5)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        assert len([e for e in events if e.type == "tool_call"]) == 1
        assert len([e for e in events if e.type == "tool_result"]) == 1
        assert [e for e in events if e.type == "done"][-1].stop_reason == "completed"


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_error_llm_response(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_error("rate_limit", "too many")
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        assert len([e for e in events if e.type == "error"]) >= 1
        assert [e for e in events if e.type == "done"][-1].stop_reason == "error"

    @pytest.mark.asyncio
    async def test_consecutive_empty_responses(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_response(SuccessLLMResponse(content=""))
        spec = AgentRunSpec([], tool_registry, "test", 5)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        errors = [e for e in events if e.type == "error"]
        assert len(errors) >= 1
        assert any("EMPTY_RESPONSE" in str(e) for e in errors)
        assert [e for e in events if e.type == "done"][-1].stop_reason == "error"

    @pytest.mark.asyncio
    async def test_non_consecutive_empty_resumes(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        call_count = [0]

        class _ResumableProvider:
            def __init__(self, base: Any) -> None:
                self.config = base.config

            async def chat_completion(self, **kwargs: Any) -> Any:
                call_count[0] += 1
                n = call_count[0]
                if n in (1, 2, 4):
                    return SuccessLLMResponse(content="")
                return SuccessLLMResponse(content="ok")

            async def chat_completion_stream(self, **kwargs: Any) -> Any:
                return await self.chat_completion(**kwargs)

        p = _ResumableProvider(mock_provider)
        spec = AgentRunSpec([], tool_registry, "test", 10)
        runner = AgentRunner(p)  # type: ignore[arg-type]
        events = [e async for e in runner.run_stream(spec)]
        assert len([e for e in events if e.type == "error"]) == 0
        assert [e for e in events if e.type == "done"][-1].stop_reason == "completed"

    @pytest.mark.asyncio
    async def test_max_iterations_exhausted(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_response(SuccessLLMResponse(content=""))
        spec = AgentRunSpec([], tool_registry, "test", 1)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        assert [e for e in events if e.type == "done"][
            -1
        ].stop_reason == "max_iterations"


class TestToolResultTruncation:
    @pytest.mark.asyncio
    async def test_short_result_preserved(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        tool_registry.register(_make_tool("trunc_test", lambda **kw: "short"))
        p.set_chat_completion_responses(
            [
                SuccessLLMResponse(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c1", name="trunc_test", arguments={})
                    ],
                ),
                SuccessLLMResponse(content="done"),
            ]
        )
        spec = AgentRunSpec([], tool_registry, "test", 3, max_tool_result_chars=10)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        results = [e for e in events if e.type == "tool_result"]
        assert results[0].result == "short"

    @pytest.mark.asyncio
    async def test_long_result_truncated(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        tool_registry.register(_make_tool("trunc_long", lambda **kw: "x" * 100))
        p.set_chat_completion_responses(
            [
                SuccessLLMResponse(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c1", name="trunc_long", arguments={})
                    ],
                ),
                SuccessLLMResponse(content="done"),
            ]
        )
        spec = AgentRunSpec([], tool_registry, "test", 3, max_tool_result_chars=10)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec)]
        results = [e for e in events if e.type == "tool_result"]
        assert "...[truncated]" in results[0].result


class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancel_before_iteration(
        self, mock_provider: Any, tool_registry: ToolRegistry
    ) -> None:
        p = mock_provider
        p.set_chat_completion_response(SuccessLLMResponse(content="hi"))
        token = CancellationToken()
        token.cancel("stopped")
        spec = AgentRunSpec([], tool_registry, "test", 3)
        runner = AgentRunner(p)
        events = [e async for e in runner.run_stream(spec, cancellation_token=token)]
        cancelled = [e for e in events if e.type == "cancelled"]
        assert len(cancelled) == 1
        assert cancelled[0].reason == "stopped"
        assert [e for e in events if e.type == "done"][-1].stop_reason == "cancelled"


# Queue timeout path is exercised by the error_llm test (error → done).
# Direct testing of the asyncio queue timeout relies on Python version-specific
# cancellation semantics and is excluded from this phase.
