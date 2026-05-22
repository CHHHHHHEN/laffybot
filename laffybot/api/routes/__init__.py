"""Aggregated API routes — imports and combines all sub-routers."""

from fastapi import APIRouter

from laffybot.api.routes.health import router as health_router
from laffybot.api.routes.mcp import router as mcp_router
from laffybot.api.routes.providers import router as provider_router
from laffybot.api.routes.sessions import router as session_router
from laffybot.api.routes.skills import router as skill_router
from laffybot.api.routes.tools import router as tool_router

router = APIRouter(prefix="/api/v1")
router.include_router(session_router)
router.include_router(provider_router)
router.include_router(mcp_router)
router.include_router(tool_router)
router.include_router(skill_router)
router.include_router(health_router)
