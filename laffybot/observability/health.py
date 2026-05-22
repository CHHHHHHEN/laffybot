"""Health check logic extracted from API layer."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from laffybot import __version__


async def check_health() -> dict[str, object]:
    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc),
    }


async def check_readiness(db_check: Callable[[], Awaitable[Any]]) -> dict[str, object]:
    try:
        await db_check()
    except Exception as exc:
        return {"status": "not_ready", "checks": {"database": str(exc)}}
    return {"status": "ready", "checks": {"database": "ok"}}
