"""MCP server configuration CRUD and control routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from loguru import logger

from laffybot.agent.tools.mcp.client import McpClient, McpError, McpProtocolError
from laffybot.agent.tools.mcp.manager import (
    MCPServerConfig,
    McpServerManager,
    create_transport,
)
from laffybot.agent.tools.mcp.transports import TransportError
from laffybot.api.dependencies import get_mcp_manager, get_mcp_server_store
from laffybot.api.schemas import (
    MCPServerCreateRequest,
    MCPServerResponse,
    MCPServerTestResponse,
    MCPServerUpdateRequest,
)
from laffybot.session.mcp_server_store import McpServerStore

router = APIRouter()


def _serialize_server(
    row: Any,
    connection_status: str = "disconnected",
    tool_count: int = 0,
) -> dict[str, object]:
    return {
        "id": row.server_id,
        "name": row.name,
        "transport_type": row.transport_type,
        "command": row.command,
        "url": row.url,
        "has_env": row.has_env,
        "has_headers": row.has_headers,
        "tool_timeout": row.tool_timeout,
        "enabled_tools": row.enabled_tools,
        "disabled_tools": row.disabled_tools,
        "startup_timeout": row.startup_timeout,
        "enabled": row.enabled,
        "connection_status": connection_status,
        "tool_count": tool_count,
        "created_at": row.created_at,
    }


def _build_config_from_row(row: Any) -> MCPServerConfig:
    return MCPServerConfig(
        name=row.name,
        transport_type=row.transport_type,
        command=row.command,
        args=row.args,
        url=row.url,
        tool_timeout=row.tool_timeout,
        enabled_tools=row.enabled_tools,
        disabled_tools=row.disabled_tools,
        startup_timeout=row.startup_timeout,
        enabled=row.enabled,
    )


def _get_connection_status(
    server_name: str,
    mcp_manager: McpServerManager | None,
) -> str:
    if mcp_manager is None:
        return "disconnected"
    status = mcp_manager.get_status(server_name)
    s = status.get("status", "disconnected")
    return s if isinstance(s, str) else "disconnected"


def _get_tool_count(
    server_name: str,
    mcp_manager: McpServerManager | None,
) -> int:
    if mcp_manager is None:
        return 0
    status = mcp_manager.get_status(server_name)
    tc = status.get("tool_count", 0)
    return tc if isinstance(tc, int) else 0


@router.get("/mcp/servers", response_model=list[MCPServerResponse])
async def list_mcp_servers(
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
    mcp_manager: McpServerManager | None = Depends(get_mcp_manager),
) -> list[dict[str, object]]:
    rows = await mcp_store.list_servers()
    return [
        _serialize_server(
            r,
            connection_status=_get_connection_status(r.name, mcp_manager),
            tool_count=_get_tool_count(r.name, mcp_manager),
        )
        for r in rows
    ]


@router.post(
    "/mcp/servers",
    response_model=MCPServerResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_mcp_server(
    payload: MCPServerCreateRequest,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
) -> dict[str, object]:
    from laffybot.session.mcp_server_store import ServerNameConflictError

    try:
        row = await mcp_store.create_server(
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
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            raise ServerNameConflictError(payload.name) from exc
        raise
    return _serialize_server(row)


@router.get("/mcp/servers/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(
    server_id: str,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
    mcp_manager: McpServerManager | None = Depends(get_mcp_manager),
) -> dict[str, object]:
    row = await mcp_store.get_server(server_id)
    return _serialize_server(
        row,
        connection_status=_get_connection_status(row.name, mcp_manager),
        tool_count=_get_tool_count(row.name, mcp_manager),
    )


@router.put("/mcp/servers/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server(
    server_id: str,
    payload: MCPServerUpdateRequest,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
    mcp_manager: McpServerManager | None = Depends(get_mcp_manager),
) -> dict[str, object]:
    from laffybot.session.mcp_server_store import ServerNameConflictError

    try:
        row = await mcp_store.update_server(
            server_id=server_id,
            name=payload.name,
            transport_type=payload.transport_type,
            command=payload.command,
            args=payload.args,
            env=payload.env,
            url=payload.url,
            headers=payload.headers,
            tool_timeout=payload.tool_timeout,
            enabled_tools=payload.enabled_tools,
            disabled_tools=payload.disabled_tools,
            startup_timeout=payload.startup_timeout,
            enabled=payload.enabled,
        )
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            raise ServerNameConflictError(payload.name or "") from exc
        raise

    # Trigger hot_swap if server is currently enabled
    if row.enabled and mcp_manager is not None:
        await _trigger_hot_swap(mcp_store, mcp_manager)

    return _serialize_server(
        row,
        connection_status=_get_connection_status(row.name, mcp_manager),
        tool_count=_get_tool_count(row.name, mcp_manager),
    )


@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(
    server_id: str,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
    mcp_manager: McpServerManager | None = Depends(get_mcp_manager),
) -> dict[str, str]:
    row = await mcp_store.get_server(server_id)

    # If enabled, disconnect first
    if row.enabled and mcp_manager is not None:
        mcp_manager.disable_server(row.name)

    await mcp_store.delete_server(server_id)
    return {"status": "deleted", "server_id": server_id}


@router.post(
    "/mcp/servers/{server_id}/enable",
    response_model=MCPServerResponse,
)
async def enable_mcp_server(
    server_id: str,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
    mcp_manager: McpServerManager | None = Depends(get_mcp_manager),
) -> dict[str, object]:
    row = await mcp_store.update_server(server_id, enabled=True)

    if mcp_manager is not None:
        await _trigger_hot_swap(mcp_store, mcp_manager)

    return _serialize_server(
        row,
        connection_status=_get_connection_status(row.name, mcp_manager),
        tool_count=_get_tool_count(row.name, mcp_manager),
    )


@router.post(
    "/mcp/servers/{server_id}/disable",
    response_model=MCPServerResponse,
)
async def disable_mcp_server(
    server_id: str,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
    mcp_manager: McpServerManager | None = Depends(get_mcp_manager),
) -> dict[str, object]:
    row = await mcp_store.get_server(server_id)
    row = await mcp_store.update_server(server_id, enabled=False)

    if mcp_manager is not None:
        mcp_manager.disable_server(row.name)
        await _trigger_hot_swap(mcp_store, mcp_manager)

    return _serialize_server(
        row,
        connection_status="disconnected",
    )


@router.post(
    "/mcp/servers/{server_id}/toggle",
    response_model=MCPServerResponse,
)
async def toggle_mcp_server(
    server_id: str,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
    mcp_manager: McpServerManager | None = Depends(get_mcp_manager),
) -> dict[str, object]:
    row = await mcp_store.get_server(server_id)
    new_enabled = not row.enabled
    return await (enable_mcp_server if new_enabled else disable_mcp_server)(
        server_id,
        mcp_store,
        mcp_manager,
    )


@router.post(
    "/mcp/servers/{server_id}/test",
    response_model=MCPServerTestResponse,
)
async def test_mcp_server(
    server_id: str,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
) -> dict[str, object]:
    row = await mcp_store.get_server(server_id)
    config = _build_config_from_row(row)

    try:
        transport = create_transport(config)
        await asyncio.wait_for(transport.connect(), timeout=config.startup_timeout)

        client = McpClient(transport)
        await asyncio.wait_for(client.initialize(), timeout=config.startup_timeout)

        tools = await asyncio.wait_for(
            client.list_tools(), timeout=config.startup_timeout
        )

        await client.close()

        return {
            "success": True,
            "message": f"Connected successfully, found {len(tools)} tool(s)",
        }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": f"Connection timed out after {config.startup_timeout}s",
        }
    except TransportError as exc:
        return {"success": False, "message": f"Transport error: {exc}"}
    except McpProtocolError as exc:
        return {"success": False, "message": f"Protocol error: {exc}"}
    except McpError as exc:
        return {"success": False, "message": f"Server error (code {exc.code}): {exc}"}
    except Exception as exc:
        return {"success": False, "message": f"Test failed: {exc}"}


@router.post(
    "/mcp/servers/{server_id}/reconnect",
    response_model=MCPServerResponse,
)
async def reconnect_mcp_server(
    server_id: str,
    mcp_store: McpServerStore = Depends(get_mcp_server_store),
    mcp_manager: McpServerManager | None = Depends(get_mcp_manager),
) -> dict[str, object]:
    row = await mcp_store.get_server(server_id)

    if mcp_manager is not None:
        mcp_manager.disable_server(row.name)
        await _trigger_hot_swap(mcp_store, mcp_manager)

    return _serialize_server(
        row,
        connection_status=_get_connection_status(row.name, mcp_manager),
        tool_count=_get_tool_count(row.name, mcp_manager),
    )


async def _build_configs_from_store(
    mcp_store: McpServerStore,
) -> list[MCPServerConfig]:
    """Build MCPServerConfig list from enabled servers in the store."""
    raw_configs = await mcp_store.get_enabled_server_configs()
    return [MCPServerConfig(**c) for c in raw_configs]


async def _trigger_hot_swap(
    mcp_store: McpServerStore,
    mcp_manager: McpServerManager,
) -> None:
    """Rebuild all enabled server configs and hot-swap the manager."""
    try:
        configs = await _build_configs_from_store(mcp_store)
        await mcp_manager.hot_swap(configs)
    except Exception as exc:
        logger.error("MCP hot-swap failed: {}", exc)
