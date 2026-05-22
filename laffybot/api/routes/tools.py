"""Tool management routes — delegates to SessionManager."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from laffybot.api.dependencies import get_session_manager
from laffybot.service.protocols import SessionManager

router = APIRouter()


@router.get("/tools")
async def list_tools(
    manager: SessionManager = Depends(get_session_manager),
) -> list[dict[str, object]]:
    return await manager.list_tools()


@router.post("/tools/{name}/disable")
async def disable_tool(
    name: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.disable_tool(name)


@router.post("/tools/{name}/enable")
async def enable_tool(
    name: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.enable_tool(name)
