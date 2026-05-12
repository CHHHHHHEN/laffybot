"""Simplified agent runner for tool-using agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from laffybot.agent.tools.registry import ToolRegistry
from laffybot.providers.base import BaseProvider
from laffybot.providers.types import LLMResponse, ToolCallRequest


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


@dataclass(slots=True)
class AgentRunResult:
    """Outcome of an agent execution."""

    final_content: str | None
    messages: list[dict[str, Any]]
    tools_used: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "completed"
    error: str | None = None


class AgentRunner:
    """Run a tool-capable LLM loop."""

    def __init__(self, provider: BaseProvider):
        self.provider = provider

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        messages = list(spec.initial_messages)
        final_content: str | None = None
        tools_used: list[str] = []
        usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
        error: str | None = None
        stop_reason = "completed"

        for iteration in range(spec.max_iterations):
            try:
                response = await self._request_model(spec, messages)
                self._accumulate_usage(usage, response.usage)

                if response.tool_calls:
                    assistant_message = self._build_assistant_message(
                        response.content or "",
                        response.tool_calls,
                    )
                    messages.append(assistant_message)
                    tools_used.extend(tc.name for tc in response.tool_calls)

                    results = await self._execute_tools(spec, response.tool_calls)

                    for tool_call, result in zip(response.tool_calls, results):
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": self._normalize_tool_result(
                                spec, tool_call.name, result
                            ),
                        }
                        messages.append(tool_message)
                    continue

                clean = response.content or ""
                if not clean.strip():
                    logger.warning(
                        "Empty response on turn {} for model {}",
                        iteration,
                        spec.model,
                    )
                    continue

                messages.append(self._build_assistant_message(clean, []))
                final_content = clean
                break

            except Exception as exc:
                logger.exception("Error on iteration {}", iteration)
                error = f"Error: {type(exc).__name__}: {exc}"
                final_content = error
                stop_reason = "error"
                break
        else:
            stop_reason = "max_iterations"
            final_content = f"Reached max iterations ({spec.max_iterations})"

        return AgentRunResult(
            final_content=final_content,
            messages=messages,
            tools_used=tools_used,
            usage=usage,
            stop_reason=stop_reason,
            error=error,
        )

    async def _request_model(
        self,
        spec: AgentRunSpec,
        messages: list[dict[str, Any]],
    ) -> LLMResponse:
        return await self.provider.chat_completion(
            messages=messages,
            model=spec.model,
            tools=spec.tools.get_definitions(),
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
        )

    async def _execute_tools(
        self,
        spec: AgentRunSpec,
        tool_calls: list[ToolCallRequest],
    ) -> list[Any]:
        results: list[Any] = []
        for tool_call in tool_calls:
            result = await self._run_tool(spec, tool_call)
            results.append(result)
        return results

    async def _run_tool(
        self,
        spec: AgentRunSpec,
        tool_call: ToolCallRequest,
    ) -> Any:
        try:
            result = await spec.tools.execute(tool_call.name, tool_call.arguments)
            return result
        except Exception as exc:
            logger.exception("Tool {} failed", tool_call.name)
            return f"Error: {type(exc).__name__}: {exc}"

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
                return result[:spec.max_tool_result_chars] + "\n...[truncated]"
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
