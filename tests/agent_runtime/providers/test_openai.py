# mypy: disable-error-code="untyped-decorator"
"""Tests for OpenAIProvider — non-streaming, streaming, error handling, message sanitization."""

from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import Response

from laffybot.agent_runtime.providers.config import ProviderConfig
from laffybot.agent_runtime.providers.openai import OpenAIProvider
from laffybot.agent_runtime.providers.types import (
    ERROR_CONNECTION,
    ERROR_RATE_LIMIT,
    ERROR_SERVER,
    ERROR_TIMEOUT,
    ErrorLLMResponse,
    StreamChunk,
    SuccessLLMResponse,
)

_API_BASE = "https://api.openai.com/v1"
_CHAT_URL = f"{_API_BASE}/chat/completions"


def _provider(**kwargs: Any) -> OpenAIProvider:
    config = ProviderConfig(
        provider_id="test",
        name="test",
        api_key="sk-test",
        base_url=_API_BASE,
        **kwargs,
    )
    return OpenAIProvider(config)


class TestChatCompletionText:
    """Non-streaming text response."""

    @pytest.mark.asyncio
    async def test_text_response(self) -> None:
        with respx.mock:
            respx.post(_CHAT_URL).respond(
                json={
                    "choices": [
                        {
                            "message": {"content": "Hello", "role": "assistant"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            )
            provider = _provider()
            response = await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}], model="gpt-4"
            )
            assert isinstance(response, SuccessLLMResponse)
            assert response.content == "Hello"
            assert response.usage["prompt_tokens"] == 10

    @pytest.mark.asyncio
    async def test_empty_choices_returns_error_response(self) -> None:
        with respx.mock:
            respx.post(_CHAT_URL).respond(json={"choices": []})
            provider = _provider()
            response = await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}], model="gpt-4"
            )
            assert isinstance(response, SuccessLLMResponse)
            assert response.finish_reason == "error"


class TestChatCompletionErrorMapping:
    """Error responses are mapped to ErrorLLMResponse with correct error_kind."""

    @pytest.mark.asyncio
    async def test_rate_limit(self) -> None:
        with respx.mock:
            respx.post(_CHAT_URL).respond(status_code=429)
            provider = _provider()
            response = await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}], model="gpt-4"
            )
            assert isinstance(response, ErrorLLMResponse)
            assert response.error_kind == ERROR_RATE_LIMIT

    @pytest.mark.asyncio
    async def test_server_error(self) -> None:
        with respx.mock:
            respx.post(_CHAT_URL).respond(status_code=500)
            provider = _provider()
            response = await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}], model="gpt-4"
            )
            assert isinstance(response, ErrorLLMResponse)
            assert response.error_kind == ERROR_SERVER

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        with respx.mock:
            respx.post(_CHAT_URL).mock(side_effect=ConnectionError("connection failed"))
            provider = _provider()
            response = await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}], model="gpt-4"
            )
            assert isinstance(response, ErrorLLMResponse)
            assert response.error_kind == ERROR_CONNECTION

    @pytest.mark.asyncio
    async def test_should_retry_header(self) -> None:
        with respx.mock:
            respx.post(_CHAT_URL).respond(
                status_code=429, headers={"x-should-retry": "true"}
            )
            provider = _provider()
            response = await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}], model="gpt-4"
            )
            assert isinstance(response, ErrorLLMResponse)
            assert response.error_should_retry is True


class TestSanitizeMessages:
    """Internal _sanitize_messages method."""

    def test_allows_known_keys(self) -> None:
        provider = _provider()
        messages = [
            {"role": "user", "content": "hi", "extra": "ignored"},
        ]
        result = provider._sanitize_messages(messages)
        assert "extra" not in result[0]
        assert result[0]["role"] == "user"

    def test_normalizes_tool_call_id(self) -> None:
        provider = _provider()
        long_id = "a" * 20
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": long_id,
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    }
                ],
            }
        ]
        result = provider._sanitize_messages(messages)
        tc = result[0]["tool_calls"][0]
        assert len(tc["id"]) == 9  # truncated by SHA1

    def test_enforces_role_alternation(self) -> None:
        provider = _provider()
        messages = [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
        ]
        with pytest.raises(ValueError, match="Consecutive same-role"):
            provider._sanitize_messages(messages)


class TestNormalizeToolCallArguments:
    """_normalize_tool_call_arguments static method."""

    def test_valid_json_string(self) -> None:
        result = OpenAIProvider._normalize_tool_call_arguments('{"a": 1}')
        assert result == '{"a": 1}'

    def test_dict_preserved(self) -> None:
        result = OpenAIProvider._normalize_tool_call_arguments({"a": 1, "b": "text"})
        assert result == '{"a": 1, "b": "text"}'

    def test_invalid_json_returns_empty(self) -> None:
        result = OpenAIProvider._normalize_tool_call_arguments("not json")
        assert result == "{}"

    def test_empty_string_returns_empty(self) -> None:
        result = OpenAIProvider._normalize_tool_call_arguments("")
        assert result == "{}"


class TestNormalizeToolCallId:
    """_normalize_tool_call_id static method."""

    def test_short_id_preserved(self) -> None:
        result = OpenAIProvider._normalize_tool_call_id("abc123def")
        assert result == "abc123def"

    def test_long_id_truncated(self) -> None:
        long_id = "a" * 20
        result = OpenAIProvider._normalize_tool_call_id(long_id)
        assert len(result) == 9

    def test_non_string_passthrough(self) -> None:
        result = OpenAIProvider._normalize_tool_call_id(42)
        assert result == 42


class TestExtractUsage:
    """_extract_usage extracts token usage from API response."""

    def test_dict_response(self) -> None:
        response = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        result = OpenAIProvider._extract_usage(response)
        assert result["prompt_tokens"] == 10
        assert result["completion_tokens"] == 5

    def test_missing_usage_returns_empty(self) -> None:
        result = OpenAIProvider._extract_usage({})
        assert result == {}


class TestOpenRouter:
    """OpenRouter attribution headers."""

    def test_openrouter_headers_added(self) -> None:
        from laffybot.agent_runtime.providers.openai import _uses_openrouter_attribution

        assert _uses_openrouter_attribution("https://openrouter.ai/api/v1") is True
        assert _uses_openrouter_attribution("https://api.openai.com/v1") is False

    @pytest.mark.asyncio
    async def test_openrouter_headers_sent(self) -> None:
        or_base = "https://openrouter.ai/api/v1"
        or_url = f"{or_base}/chat/completions"
        with respx.mock:
            request_sent = None

            def capture(request: Any) -> Any:
                nonlocal request_sent
                request_sent = request
                return Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": "ok", "role": "assistant"},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                )

            respx.post(or_url).mock(side_effect=capture)
            config = ProviderConfig(
                provider_id="test",
                name="test",
                api_key="sk-test",
                base_url=or_base,
            )
            provider = OpenAIProvider(config)
            await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}], model="gpt-4"
            )
            assert request_sent is not None
            headers = request_sent.headers
            assert "HTTP-Referer" in headers


class TestExtraBody:
    """extra_body passthrough."""

    @pytest.mark.asyncio
    async def test_extra_body_included(self) -> None:
        with respx.mock:
            request_body = None

            def capture(request: Any) -> Any:
                nonlocal request_body
                request_body = request
                return Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": "ok", "role": "assistant"},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                )

            respx.post(_CHAT_URL).mock(side_effect=capture)
            provider = _provider(extra_body={"custom": "value"})
            await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}], model="gpt-4"
            )
            import json

            assert request_body is not None
            body = json.loads(request_body.content)
            assert body.get("custom") == "value"


class TestTemperatureSuppression:
    """Temperature is suppressed for o1/o3/o4 class models."""

    @pytest.mark.asyncio
    async def test_temperature_suppressed_for_o_models(self) -> None:
        with respx.mock:
            request_body = None

            def capture(request: Any) -> Any:
                nonlocal request_body
                request_body = request
                return Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": "ok", "role": "assistant"},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                )

            respx.post(_CHAT_URL).mock(side_effect=capture)
            provider = _provider()
            await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                model="o3-mini",
                temperature=0.7,
            )
            import json

            assert request_body is not None
            body = json.loads(request_body.content)
            assert "temperature" not in body

    @pytest.mark.asyncio
    async def test_temperature_included_for_gpt_models(self) -> None:
        with respx.mock:
            request_body = None

            def capture(request: Any) -> Any:
                nonlocal request_body
                request_body = request
                return Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": "ok", "role": "assistant"},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                )

            respx.post(_CHAT_URL).mock(side_effect=capture)
            provider = _provider()
            await provider.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4",
                temperature=0.7,
            )
            import json

            assert request_body is not None
            body = json.loads(request_body.content)
            assert body.get("temperature") == 0.7


class TestToolCallResponse:
    """Non-streaming tool call response."""

    @pytest.mark.asyncio
    async def test_tool_call_in_response(self) -> None:
        with respx.mock:
            respx.post(_CHAT_URL).respond(
                json={
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_abc123",
                                        "type": "function",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": '{"path": "/tmp"}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            )
            provider = _provider()
            response = await provider.chat_completion(
                messages=[{"role": "user", "content": "read a file"}],
                model="gpt-4",
                tools=[{"type": "function", "function": {"name": "read_file"}}],
            )
            assert isinstance(response, SuccessLLMResponse)
            assert len(response.tool_calls) == 1
            assert response.tool_calls[0].name == "read_file"
            assert response.tool_calls[0].arguments == {"path": "/tmp"}
            assert response.finish_reason == "tool_calls"


class TestStreamingIdleTimeout:
    """Streaming idle timeout returns ErrorLLMResponse."""

    @pytest.mark.asyncio
    async def test_streaming_idle_timeout(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("LAFFYBOT_STREAM_IDLE_TIMEOUT_S", "1")
        provider = _provider()

        class _BlockingStream:
            def __aiter__(self) -> _BlockingStream:
                return self

            async def __anext__(self) -> Any:
                if not getattr(self, "_started", False):
                    self._started = True
                    return _stream_chunk("hi")
                await asyncio.Event().wait()

        import asyncio
        from unittest.mock import patch

        async def mock_create(**kwargs: Any) -> Any:
            return _BlockingStream()

        with patch.object(provider._client.chat.completions, "create", new=mock_create):

            async def on_chunk(c: StreamChunk) -> None:
                pass

            response = await provider.chat_completion_stream(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4",
                on_chunk=on_chunk,
            )
            assert isinstance(response, ErrorLLMResponse)
            assert response.error_kind == ERROR_TIMEOUT


def _stream_chunk(content: str) -> Any:
    from types import SimpleNamespace

    choice = SimpleNamespace()
    choice.delta = SimpleNamespace()
    choice.delta.content = content
    choice.delta.reasoning_content = None
    choice.delta.reasoning = None
    choice.delta.tool_calls = None
    choice.finish_reason = None
    choice.index = 0

    chunk = SimpleNamespace()
    chunk.choices = [choice]
    chunk.id = "x"
    return chunk


class TestLocalEndpoint:
    """_is_local_endpoint detection."""

    def test_localhost(self) -> None:
        from laffybot.agent_runtime.providers.openai import _is_local_endpoint

        assert _is_local_endpoint("http://localhost:8000/v1") is True

    def test_remote(self) -> None:
        from laffybot.agent_runtime.providers.openai import _is_local_endpoint

        assert _is_local_endpoint("https://api.openai.com/v1") is False


class TestSampleStreaming:
    """Minimal streaming test — feed SSE chunks and verify on_chunk calls."""

    @pytest.mark.asyncio
    async def test_basic_streaming_content(self) -> None:
        sse_data = "\n\n".join(
            [
                'data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}',
                'data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" World"},"finish_reason":null}]}',
                'data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":5}}',
                "data: [DONE]",
            ]
        )
        with respx.mock:
            respx.post(_CHAT_URL).respond(
                status_code=200,
                headers={"Content-Type": "text/event-stream"},
                content=sse_data.encode(),
            )
            provider = _provider()
            chunks: list[StreamChunk] = []

            async def on_chunk(c: StreamChunk) -> None:
                chunks.append(c)

            response = await provider.chat_completion_stream(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4",
                on_chunk=on_chunk,
            )
            assert isinstance(response, SuccessLLMResponse)
            assert response.content == "Hello World"
            assert response.usage.get("prompt_tokens") == 10
            text_chunks = [c for c in chunks if c.content]
            assert len(text_chunks) == 2
            assert text_chunks[0].content == "Hello"
