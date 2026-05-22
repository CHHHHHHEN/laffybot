"""Health and readiness routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from laffybot.api.dependencies import get_session_manager
from laffybot.api.schemas import HealthResponse, ReadyResponse
from laffybot.service.protocols import SessionManager

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await session_manager.get_health_status()


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await session_manager.get_readiness_status()
