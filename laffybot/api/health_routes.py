"""Health and readiness routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from laffybot import __version__
from laffybot.api.dependencies import get_store
from laffybot.api.schemas import HealthResponse, ReadyResponse
from laffybot.session.store import SessionStore

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> dict[str, object]:
    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc),
    }


@router.get("/ready", response_model=ReadyResponse)
async def ready(store: SessionStore = Depends(get_store)) -> dict[str, object]:
    try:
        await store.list_sessions(limit=1, offset=0)
    except Exception as exc:
        return {"status": "not_ready", "checks": {"database": str(exc)}}
    return {"status": "ready", "checks": {"database": "ok"}}
