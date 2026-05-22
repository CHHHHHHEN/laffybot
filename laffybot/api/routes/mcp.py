"""MCP server configuration CRUD and control routes — delegates to SessionManager."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from laffybot.api.dependencies import get_session_manager
from laffybot.api.schemas import (
    MCPServerCreateRequest,
    MCPServerResponse,
    MCPServerTestResponse,
    MCPServerUpdateRequest,
)
from laffybot.service.protocols import SessionManager

router = APIRouter()


@router.get("/mcp/servers", response_model=list[MCPServerResponse])
async def list_mcp_servers(
    manager: SessionManager = Depends(get_session_manager),
) -> list[dict[str, object]]:
    return await manager.list_mcp_servers()


@router.post(
    "/mcp/servers",
    response_model=MCPServerResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_mcp_server(
    payload: MCPServerCreateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.create_mcp_server(
        name=payload.name,
        transport_type=payload.transport_type,
        command=payload.command,
        args=payload.args,
        env=payload.env,
        url=payload.url,
        headers=payload.headers,
        tool_timeout=payload.tool_timeout or 30,
        enabled_tools=payload.enabled_tools,
        disabled_tools=payload.disabled_tools,
        startup_timeout=payload.startup_timeout or 30,
        enabled=payload.enabled,
    )


@router.get("/mcp/servers/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(
    server_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.get_mcp_server(server_id)


@router.put("/mcp/servers/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server(
    server_id: str,
    payload: MCPServerUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    kwargs = {}
    for key in (
        "name",
        "transport_type",
        "command",
        "args",
        "env",
        "url",
        "headers",
        "tool_timeout",
        "enabled_tools",
        "disabled_tools",
        "startup_timeout",
        "enabled",
    ):
        val = getattr(payload, key, None)
        if val is not None:
            kwargs[key] = val
    return await manager.update_mcp_server(server_id=server_id, **kwargs)


@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(
    server_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, str]:
    await manager.delete_mcp_server(server_id)
    return {"status": "deleted", "server_id": server_id}


@router.post("/mcp/servers/{server_id}/enable", response_model=MCPServerResponse)
async def enable_mcp_server(
    server_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.enable_mcp_server(server_id)


@router.post("/mcp/servers/{server_id}/disable", response_model=MCPServerResponse)
async def disable_mcp_server(
    server_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.disable_mcp_server(server_id)


@router.post("/mcp/servers/{server_id}/toggle", response_model=MCPServerResponse)
async def toggle_mcp_server(
    server_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.toggle_mcp_server(server_id)


@router.post("/mcp/servers/{server_id}/test", response_model=MCPServerTestResponse)
async def test_mcp_server(
    server_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.test_mcp_server(server_id)


@router.post("/mcp/servers/{server_id}/reconnect", response_model=MCPServerResponse)
async def reconnect_mcp_server(
    server_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, object]:
    return await manager.reconnect_mcp_server(server_id)
