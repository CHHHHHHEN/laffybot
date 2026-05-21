from __future__ import annotations

from typing import Any

import httpx
from llama_index.core.bridge.pydantic import Field
from llama_index.core.embeddings import BaseEmbedding

from rag_mcp_server.logger import get_logger


class OpenAICompatibleEmbedding(BaseEmbedding):  # type: ignore[misc]
    """Embedding model targeting any OpenAI-compatible /v1/embeddings endpoint.

    Unlike ``llama_index.embeddings.openai.OpenAIEmbedding``, this class does
    **not** validate the model name against a fixed enum, making it suitable
    for proxies, local inference servers, and any OpenAI-compatible API.
    """

    model: str = Field(description="The embedding model name")
    api_base: str = Field(description="Base URL for the OpenAI-compatible API")
    api_key: str | None = Field(default=None, description="Optional API key")
    http_timeout: float = Field(default=60.0, description="HTTP request timeout")

    def __init__(
        self,
        model: str,
        api_base: str,
        api_key: str | None = None,
        http_timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model=model,
            api_base=api_base,
            api_key=api_key,
            http_timeout=http_timeout,
            **kwargs,
        )
        self._client = httpx.Client(timeout=http_timeout)
        self._async_client = httpx.AsyncClient(timeout=http_timeout)
        self._logger = get_logger("rag_mcp_server.embeddings")

    def _build_embedding_request(
        self, texts: list[str]
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.api_base.rstrip('/')}/embeddings"
        payload: dict[str, Any] = {"input": texts, "model": self.model}
        return url, headers, payload

    def _check_response(self, resp: httpx.Response, url: str) -> None:
        if resp.status_code == 401:
            raise RuntimeError("Embedding API returned 401 — check your API key")
        if resp.status_code == 404:
            raise RuntimeError(
                f"Embedding API returned 404 — {url} not found "
                "(is the server running and does it expose /embeddings?)"
            )
        resp.raise_for_status()

    def _parse_embedding_response(self, texts: list[str], data: Any) -> list[list[float]]:
        if "data" not in data or not isinstance(data["data"], list):
            raise RuntimeError(f"Embedding API response missing 'data' array: {str(data)[:500]}")

        results: list[list[float] | None] = [None] * len(texts)
        for item in data["data"]:
            idx = item.get("index")
            if idx is not None and 0 <= idx < len(texts):
                results[idx] = item["embedding"]

        if any(r is None for r in results):
            missing = [i for i, r in enumerate(results) if r is None]
            self._logger.warning(
                "Embedding API returned incomplete results: missing indices %s for inputs %s",
                missing,
                [texts[i][:100] for i in missing],
            )
            results = [r if r is not None else [] for r in results]

        return results  # type: ignore[return-value]

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        url, headers, payload = self._build_embedding_request(texts)

        try:
            resp = self._client.post(url, json=payload, headers=headers)
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Embedding API connection failed: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Embedding API timed out after {self.http_timeout}s: {exc}"
            ) from exc

        self._check_response(resp, url)

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"Embedding API returned non-JSON response: {resp.text[:500]}"
            ) from exc

        return self._parse_embedding_response(texts, data)

    async def _acall_api(self, texts: list[str]) -> list[list[float]]:
        url, headers, payload = self._build_embedding_request(texts)

        try:
            resp = await self._async_client.post(url, json=payload, headers=headers)
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Embedding API connection failed: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"Embedding API timed out after {self.http_timeout}s: {exc}"
            ) from exc

        self._check_response(resp, url)

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"Embedding API returned non-JSON response: {resp.text[:500]}"
            ) from exc

        return self._parse_embedding_response(texts, data)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._call_api([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) == 1:
            return [self._get_text_embedding(texts[0])]
        return self._call_api(texts)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._get_text_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        results = await self._acall_api([text])
        return results[0]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await self._aget_text_embedding(query)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._acall_api(texts)

    def close(self) -> None:
        self._client.close()
