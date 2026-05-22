from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MessageAccumulator:
    assistant_chunks: list[str] = field(default_factory=list)
    reasoning_chunks: list[str] = field(default_factory=list)
    accumulated_tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def on_content(self, text: str) -> None:
        self.assistant_chunks.append(text)

    def on_reasoning(self, text: str) -> None:
        self.reasoning_chunks.append(text)

    def on_tool_call(self, tool_call_id: str, name: str, arguments: str) -> None:
        self.accumulated_tool_calls.append(
            {
                "tool_call_id": tool_call_id,
                "name": name,
                "arguments": arguments,
                "status": "pending",
            }
        )

    def on_tool_result(
        self,
        tool_call_id: str,
        success: bool,
        result: Any,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        for tc in self.accumulated_tool_calls:
            if tc["tool_call_id"] == tool_call_id:
                tc["status"] = "completed" if success else "failed"
                tc["result"] = result
                tc["success"] = success
                if duration_ms is not None:
                    tc["duration_ms"] = duration_ms
                if error_message is not None:
                    tc["error_message"] = error_message
                break

    def build_assistant_message(
        self, usage: dict[str, int] | None = None
    ) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "content": "".join(self.assistant_chunks),
        }
        if self.reasoning_chunks:
            msg["reasoning_content"] = "".join(self.reasoning_chunks)
        if self.accumulated_tool_calls:
            msg["tool_calls"] = self.accumulated_tool_calls
        if usage:
            msg["input_tokens"] = usage.get("prompt_tokens")
            msg["output_tokens"] = usage.get("completion_tokens")
        return msg
