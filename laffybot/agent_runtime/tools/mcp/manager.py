"""MCP server lifecycle manager — AsyncManagedClient + McpServerManager."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from loguru import logger

from laffybot.agent_runtime.tools.mcp.client import McpClient
from laffybot.agent_runtime.tools.mcp.transports import (
    SseTransport,
    StdioTransport,
    StreamableHttpTransport,
    Transport,
    TransportError,
)
from laffybot.agent_runtime.tools.mcp.wrappers import (
    McpPromptTool,
    McpResourceTool,
    McpToolCall,
    ToolFilter,
    normalise_server_name,
)


class ServerStatus(Enum):
    created = "created"
    starting = "starting"
    ready = "ready"
    failed = "failed"
    disconnected = "disconnected"


@dataclass
class MCPServerConfig:
    name: str
    transport_type: str  # "stdio" | "sse" | "streamableHttp"
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    tool_timeout: int = 30
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] | None = None
    startup_timeout: int = 30
    enabled: bool = True


def create_transport(config: MCPServerConfig) -> Transport:
    """Factory: return a Transport for the given config."""
    if config.transport_type == "stdio":
        if not config.command:
            raise ValueError("stdio transport requires a command")
        return StdioTransport(
            command=config.command,
            args=config.args,
            env=config.env,
        )
    if config.transport_type == "sse":
        if not config.url:
            raise ValueError("SSE transport requires a url")
        return SseTransport(
            url=config.url,
            headers=config.headers,
            http_timeout=config.tool_timeout,
        )
    if config.transport_type == "streamableHttp":
        if not config.url:
            raise ValueError("streamableHttp transport requires a url")
        return StreamableHttpTransport(
            url=config.url,
            headers=config.headers,
            http_timeout=config.tool_timeout,
        )
    raise ValueError(f"Unknown transport type: {config.transport_type}")


# ── AsyncManagedClient ───────────────────────────────────────────────────


@dataclass
class AsyncManagedClient:
    server_name: str
    config: MCPServerConfig
    client: McpClient | None = None
    transport: Transport | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_filter: ToolFilter = field(default_factory=ToolFilter)
    status: ServerStatus = ServerStatus.created
    started_at: datetime | None = None
    error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status == ServerStatus.ready


# ── McpServerManager ─────────────────────────────────────────────────────


class McpServerManager:
    """Manager for multiple MCP server connections.

    Parallel startup, per-server routing, hot-swap, and clean shutdown.
    """

    def __init__(
        self,
        configs: list[MCPServerConfig],
        tool_registry: Any = None,  # ToolRegistry (forward ref)
    ) -> None:
        self._tool_registry = tool_registry
        self._config_map: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, AsyncManagedClient] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._server_tasks: dict[str, asyncio.Task[None]] = {}
        for cfg in configs:
            self._config_map[cfg.name] = cfg
            self._clients[cfg.name] = AsyncManagedClient(
                server_name=cfg.name,
                config=cfg,
                tool_filter=ToolFilter(
                    enabled_tools=cfg.enabled_tools,
                    disabled_tools=cfg.disabled_tools,
                ),
            )
        self._started = False

    async def start(self) -> dict[str, str]:
        """Parallel start of all enabled servers.

        Returns a dict of ``{server_name: status_or_error}``.
        """
        self._started = True
        tasks: list[asyncio.Task[str | None]] = []
        for name, client in self._clients.items():
            if not client.config.enabled:
                continue
            task = asyncio.create_task(self._start_one(name))
            tasks.append(task)
            self._server_tasks[name] = task  # type: ignore[assignment]
        if not tasks:
            return {}

        results = await asyncio.gather(*tasks, return_exceptions=True)
        status_map: dict[str, str] = {}
        for name, result in zip(
            [n for n, c in self._clients.items() if c.config.enabled], results
        ):
            if isinstance(result, Exception):
                status_map[name] = f"failed: {result}"
            elif isinstance(result, str):
                status_map[name] = result
            else:
                status_map[name] = "ready"
        return status_map

    async def _start_one(self, server_name: str) -> str | None:
        client = self._clients.get(server_name)
        if client is None:
            return None
        client.status = ServerStatus.starting
        client.started_at = datetime.now(timezone.utc)
        cfg = client.config

        try:
            transport = create_transport(cfg)
            client.transport = transport
            await asyncio.wait_for(transport.connect(), timeout=cfg.startup_timeout)
            transport.on_disconnect = lambda: self._on_server_disconnected(server_name)

            mcp_client = McpClient(transport)
            client.client = mcp_client
            await asyncio.wait_for(mcp_client.initialize(), timeout=cfg.startup_timeout)

            raw_tools = await asyncio.wait_for(
                mcp_client.list_tools(), timeout=cfg.startup_timeout
            )
            filtered = client.tool_filter.apply(raw_tools)
            client.tools = filtered

            wrapped: list[Any] = []
            for td in filtered:
                wrapped.append(McpToolCall(server_name, td, self))
            # List resources if capability present
            caps = mcp_client.server_capabilities
            if caps.get("resources", {}):
                try:
                    raw_resources = await asyncio.wait_for(
                        mcp_client.list_resources(), timeout=cfg.startup_timeout
                    )
                    for rd in raw_resources:
                        if client.tool_filter.allows(rd.get("name", rd.get("uri", ""))):
                            wrapped.append(McpResourceTool(server_name, rd, self))
                except Exception as exc:
                    logger.warning(
                        "Failed to list resources for {}: {}", server_name, exc
                    )
            # List prompts if capability present
            if caps.get("prompts", {}):
                try:
                    raw_prompts = await asyncio.wait_for(
                        mcp_client.list_prompts(), timeout=cfg.startup_timeout
                    )
                    for pd in raw_prompts:
                        if client.tool_filter.allows(pd.get("name", "")):
                            wrapped.append(McpPromptTool(server_name, pd, self))
                except Exception as exc:
                    logger.warning(
                        "Failed to list prompts for {}: {}", server_name, exc
                    )

            # Register to ToolRegistry
            if self._tool_registry is not None:
                for tool in wrapped:
                    self._tool_registry.register(tool)

            client.status = ServerStatus.ready
            logger.info("MCP server '{}' ready ({} tools)", server_name, len(wrapped))
            return None
        except asyncio.TimeoutError:
            client.status = ServerStatus.failed
            client.error = f"Timed out after {cfg.startup_timeout}s"
        except Exception as exc:
            client.status = ServerStatus.failed
            client.error = str(exc)
            logger.warning("MCP server '{}' failed: {}", server_name, exc)
        finally:
            if client.status != ServerStatus.ready:
                if client.transport is not None:
                    try:
                        await client.transport.close()
                    except Exception:
                        pass
                    client.transport = None
                if client.client is not None:
                    client.client = None
                await self._on_server_disconnected(server_name)
        return client.error

    async def _on_server_disconnected(self, server_name: str) -> None:
        """统一清理入口：断开后更新状态、注销工具、取消运行中的任务。"""
        client = self._clients.get(server_name)
        if client is None:
            logger.debug("Server {} already removed, skip cleanup", server_name)
            return

        if client.status == ServerStatus.disconnected:
            logger.debug("Server {} already disconnected, skip cleanup", server_name)
            return

        logger.info("MCP server '{}' disconnected, cleaning up tools", server_name)
        client.status = ServerStatus.disconnected
        self._unregister_server_tools(server_name)

        task = self._server_tasks.get(server_name)
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.warning(
                    "Unexpected error awaiting cancelled MCP task for '{}'",
                    server_name,
                    exc_info=True,
                )

    async def shutdown(self) -> None:
        """Cancel all tasks and close all transports."""
        for name, task in self._server_tasks.items():
            if not task.done():
                task.cancel()
        if self._tasks:
            for t in self._tasks:
                if not t.done():
                    t.cancel()
        await self._cleanup_transports()

    async def _cleanup_transports(self) -> None:
        for client in self._clients.values():
            if client.transport is not None:
                try:
                    await client.transport.close()
                except Exception:
                    pass
                client.transport = None
            await self._on_server_disconnected(client.server_name)

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Route a tool call to the appropriate server."""
        client = self._clients.get(server_name)
        if client is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: MCP server '{server_name}' not found",
                    }
                ],
                "isError": True,
            }
        if client.status != ServerStatus.ready:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: MCP server '{server_name}' disconnected",
                    }
                ],
                "isError": True,
            }
        if not client.tool_filter.allows(tool_name):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Tool '{tool_name}' is disabled on server '{server_name}'",
                    }
                ],
                "isError": True,
            }
        if client.client is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: MCP server '{server_name}' not initialized",
                    }
                ],
                "isError": True,
            }
        try:
            result = await asyncio.wait_for(
                client.client.call_tool(tool_name, arguments),
                timeout=client.config.tool_timeout,
            )
            return result
        except asyncio.TimeoutError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Tool '{tool_name}' timed out after {client.config.tool_timeout}s",
                    }
                ],
                "isError": True,
            }
        except TransportError:
            await self._on_server_disconnected(server_name)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: MCP server '{server_name}' disconnected during tool call",
                    }
                ],
                "isError": True,
            }
        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"Error: {_sanitize_error(exc)}"}],
                "isError": True,
            }

    async def read_resource(self, server_name: str, uri: str) -> list[dict[str, Any]]:
        """Read a resource by URI from the given server."""
        client = self._clients.get(server_name)
        if (
            client is None
            or client.client is None
            or client.status != ServerStatus.ready
        ):
            return []
        return await client.client.read_resource(uri)

    async def get_prompt(
        self,
        server_name: str,
        prompt_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get a prompt from the given server."""
        client = self._clients.get(server_name)
        if (
            client is None
            or client.client is None
            or client.status != ServerStatus.ready
        ):
            return {"messages": []}
        return await client.client.get_prompt(prompt_name, arguments)

    def list_all_tools(self) -> list[dict[str, Any]]:
        """Aggregate (filtered) tool definitions from all ready servers."""
        result: list[dict[str, Any]] = []
        for name, client in sorted(self._clients.items()):
            if client.status == ServerStatus.ready:
                for td in client.tools:
                    result.append(
                        {
                            "server_name": name,
                            "tool_name": td.get("name", ""),
                            "description": td.get("description", ""),
                            "inputSchema": td.get(
                                "inputSchema", td.get("input_schema", {})
                            ),
                        }
                    )
        return result

    async def list_all_resources(self) -> list[dict[str, Any]]:
        """Concurrently list resources from all ready servers."""
        from asyncio import gather

        results: list[dict[str, Any]] = []
        tasks = []
        names = []
        for name, client in self._clients.items():
            if client.status == ServerStatus.ready and client.client is not None:
                caps = client.client.server_capabilities
                if caps.get("resources", {}):
                    tasks.append(client.client.list_resources())
                    names.append(name)
        if tasks:
            resource_lists = await gather(*tasks, return_exceptions=True)
            for name, rl in zip(names, resource_lists):
                if isinstance(rl, list):
                    for r in rl:
                        results.append({"server_name": name, **r})
        return results

    async def list_all_prompts(self) -> list[dict[str, Any]]:
        """Concurrently list prompts from all ready servers."""
        from asyncio import gather

        results: list[dict[str, Any]] = []
        tasks = []
        names = []
        for name, client in self._clients.items():
            if client.status == ServerStatus.ready and client.client is not None:
                caps = client.client.server_capabilities
                if caps.get("prompts", {}):
                    tasks.append(client.client.list_prompts())
                    names.append(name)
        if tasks:
            prompt_lists = await gather(*tasks, return_exceptions=True)
            for name, pl in zip(names, prompt_lists):
                if isinstance(pl, list):
                    for p in pl:
                        results.append({"server_name": name, **p})
        return results

    def get_status(self, server_name: str) -> dict[str, Any]:
        client = self._clients.get(server_name)
        if client is None:
            return {"status": "not_found"}
        return {
            "status": client.status.value,
            "error": client.error,
            "started_at": client.started_at.isoformat() if client.started_at else None,
            "tool_count": len(client.tools),
        }

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        return {name: self.get_status(name) for name in self._clients}

    async def hot_swap(self, new_configs: list[MCPServerConfig]) -> None:
        """Atomically replace all server connections.

        New servers start in parallel; stale servers get disconnected only after
        new ones are ready.
        """
        new_manager = McpServerManager(new_configs, tool_registry=self._tool_registry)
        await new_manager.start()

        new_names = {c.name for c in new_configs}
        old_names = set(self._clients.keys())
        stale_names = old_names - new_names

        # Register new tools (already done in _start_one via ToolRegistry)
        # Unregister stale tools
        if self._tool_registry is not None:
            for name in stale_names:
                self._unregister_server_tools(name)

        # Atomic swap
        old_clients = self._clients
        old_tasks = self._server_tasks
        self._clients = new_manager._clients
        self._server_tasks = new_manager._server_tasks
        self._tasks = new_manager._tasks
        self._config_map = new_manager._config_map

        # Shutdown old
        for client in old_clients.values():
            if client.transport is not None:
                try:
                    await client.transport.close()
                except Exception:
                    pass
        for task in old_tasks.values():
            if not task.done():
                task.cancel()

    def _unregister_server_tools(self, server_name: str) -> None:
        if self._tool_registry is None:
            return
        prefix = f"{normalise_server_name(server_name)}_"
        names_to_remove = [
            name for name in self._tool_registry.tool_names if name.startswith(prefix)
        ]
        for name in names_to_remove:
            self._tool_registry.unregister(name)

    def disable_server(self, server_name: str) -> None:
        """Disable a server and unregister its tools."""
        if server_name in self._server_tasks:
            task = self._server_tasks[server_name]
            if not task.done():
                task.cancel()
        self._unregister_server_tools(server_name)
        client = self._clients.get(server_name)
        if client is not None:
            client.status = ServerStatus.disconnected

    @property
    def active_servers(self) -> list[str]:
        return [n for n, c in self._clients.items() if c.status == ServerStatus.ready]


def _sanitize_error(exc: Exception) -> str:
    msg = str(exc)
    if not msg:
        return type(exc).__name__
    return msg
