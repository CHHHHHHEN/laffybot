"""Tool management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from laffybot.agent.tools.registry import ToolRegistry
from laffybot.api.dependencies import get_tool_registry

router = APIRouter()


@router.get("/tools")
async def list_tools(
    registry: ToolRegistry = Depends(get_tool_registry),
) -> list[dict[str, object]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "read_only": tool.read_only,
            "enabled": registry.is_enabled(tool.name),
        }
        for tool in sorted(registry._tools.values(), key=lambda t: t.name)
    ]


@router.post("/tools/{name}/disable")
async def disable_tool(
    name: str,
    registry: ToolRegistry = Depends(get_tool_registry),
) -> dict[str, object]:
    registry.disable(name)
    return {"name": name, "enabled": False}


@router.post("/tools/{name}/enable")
async def enable_tool(
    name: str,
    registry: ToolRegistry = Depends(get_tool_registry),
) -> dict[str, object]:
    registry.enable(name)
    return {"name": name, "enabled": True}
