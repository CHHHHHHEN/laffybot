"""Aggregated API routes — imports and combines all sub-routers."""

from fastapi import APIRouter

from laffybot.api.health_routes import router as health_router
from laffybot.api.provider_routes import router as provider_router
from laffybot.api.session_routes import router as session_router
from laffybot.api.tool_routes import router as tool_router

router = APIRouter(prefix="/api/v1")
router.include_router(session_router)
router.include_router(provider_router)
router.include_router(tool_router)
router.include_router(health_router)
