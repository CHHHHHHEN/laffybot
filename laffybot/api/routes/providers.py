"""Provider and model routes — API layer only, delegates to SessionManager."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from laffybot.api.dependencies import get_session_manager
from laffybot.api.schemas import (
    ModelCreateRequest,
    ModelResponse,
    ProviderCreateRequest,
    ProviderDetailResponse,
    ProviderResponse,
    ProviderUpdateRequest,
    TestResultResponse,
)
from laffybot.service.protocols import SessionManager

router = APIRouter()


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    manager: SessionManager = Depends(get_session_manager),
) -> list[dict[str, object]]:
    return await manager.list_providers()


@router.post(
    "/providers",
    response_model=ProviderResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_provider(
    payload: ProviderCreateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.create_provider(
        name=payload.name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        extra_headers=payload.extra_headers,
        extra_body=payload.extra_body,
    )


@router.get("/providers/{provider_id}", response_model=ProviderDetailResponse)
async def get_provider(
    provider_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.get_provider(provider_id)


@router.put("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    payload: ProviderUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.update_provider(
        provider_id=provider_id,
        name=payload.name,
        base_url=payload.base_url,
        api_key=payload.api_key,
        extra_headers=payload.extra_headers,
    )


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    await manager.delete_provider(provider_id)
    return {"status": "deleted", "provider_id": provider_id}


@router.get("/providers/{provider_id}/models", response_model=list[ModelResponse])
async def list_models(
    provider_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> list[dict[str, object]]:
    return await manager.list_models(provider_id)


@router.post(
    "/providers/{provider_id}/models",
    response_model=ModelResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def add_model(
    provider_id: str,
    payload: ModelCreateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.add_model(provider_id, payload.name)


@router.delete("/providers/{provider_id}/models/{model_id}")
async def delete_model(
    provider_id: str,
    model_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_model(model_id)
    return {"status": "deleted", "model_id": model_id}


@router.post("/providers/{provider_id}/test", response_model=TestResultResponse)
async def test_provider(
    provider_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.test_provider(provider_id)
