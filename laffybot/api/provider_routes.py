"""Provider and model routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from laffybot.api.dependencies import get_provider_store
from laffybot.api.schemas import (
    ModelCreateRequest,
    ModelResponse,
    ProviderCreateRequest,
    ProviderDetailResponse,
    ProviderResponse,
    ProviderUpdateRequest,
    TestResultResponse,
)
from laffybot.providers.errors import ProviderConnectionError
from laffybot.session.provider_store import ProviderRow, ProviderStore

router = APIRouter()


def _serialize_provider(p: ProviderRow) -> dict[str, object]:
    return {
        "id": p.provider_id,
        "name": p.name,
        "base_url": p.base_url,
        "has_api_key": p.has_api_key,
        "created_at": p.created_at,
    }


def _serialize_provider_detail(p: ProviderRow) -> dict[str, object]:
    return {
        "id": p.provider_id,
        "name": p.name,
        "base_url": p.base_url,
        "has_api_key": p.has_api_key,
        "extra_headers": p.extra_headers,
        "created_at": p.created_at,
    }


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    provider_store: ProviderStore = Depends(get_provider_store),
) -> list[dict[str, object]]:
    providers = await provider_store.list_providers()
    return [_serialize_provider(p) for p in providers]


@router.post(
    "/providers",
    response_model=ProviderResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_provider(
    payload: ProviderCreateRequest,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    provider = await provider_store.create_provider(
        name=payload.name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        extra_headers=payload.extra_headers,
    )
    return _serialize_provider(provider)


@router.get("/providers/{provider_id}", response_model=ProviderDetailResponse)
async def get_provider(
    provider_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    provider = await provider_store.get_provider(provider_id)
    return _serialize_provider_detail(provider)


@router.put("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    payload: ProviderUpdateRequest,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    provider = await provider_store.update_provider(
        provider_id=provider_id,
        name=payload.name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        extra_headers=payload.extra_headers,
    )
    return _serialize_provider(provider)


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    await provider_store.delete_provider(provider_id)
    return {"status": "deleted", "provider_id": provider_id}


@router.get("/providers/{provider_id}/models", response_model=list[ModelResponse])
async def list_models(
    provider_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> list[dict[str, object]]:
    models = await provider_store.list_models(provider_id)
    return [
        {"id": m.model_id, "provider_id": m.provider_id, "name": m.name} for m in models
    ]


@router.post(
    "/providers/{provider_id}/models",
    response_model=ModelResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def add_model(
    provider_id: str,
    payload: ModelCreateRequest,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    model = await provider_store.add_model(provider_id, payload.name)
    return {"id": model.model_id, "provider_id": model.provider_id, "name": model.name}


@router.delete("/providers/{provider_id}/models/{model_id}")
async def delete_model(
    provider_id: str,
    model_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, str]:
    await provider_store.delete_model(model_id)
    return {"status": "deleted", "model_id": model_id}


@router.post("/providers/{provider_id}/test", response_model=TestResultResponse)
async def test_provider(
    provider_id: str,
    provider_store: ProviderStore = Depends(get_provider_store),
) -> dict[str, object]:
    config = await provider_store.get_provider_config(provider_id)
    models = await provider_store.list_models(provider_id)
    if not models:
        return {
            "success": False,
            "message": "No models configured for this provider",
            "latency_ms": None,
        }

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
    model_name = models[0].name
    start = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        latency = int((time.perf_counter() - start) * 1000)
        if response.choices:
            return {
                "success": True,
                "message": "Connection successful",
                "latency_ms": latency,
            }
        return {
            "success": False,
            "message": "Unexpected response format",
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
            raise ProviderConnectionError(f"Connection failed: {exc}") from exc
        return {
            "success": False,
            "message": f"Test failed: {exc}",
            "latency_ms": latency,
        }
