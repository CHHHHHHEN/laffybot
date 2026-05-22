"""SQLite-backed persistence for MCP server configurations."""

from __future__ import annotations

import json
import uuid
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiosqlite
from loguru import logger

from laffybot.crypto import decrypt_api_key, encrypt_api_key
from laffybot.db.base import BaseStore
from laffybot.db.manager import DatabaseManager

_MCP_SERVER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mcp_servers (
    server_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 0,
    transport_type TEXT,
    command TEXT,
    args TEXT NOT NULL DEFAULT '[]',
    env TEXT,
    url TEXT,
    headers TEXT,
    tool_timeout INTEGER NOT NULL DEFAULT 30,
    enabled_tools TEXT NOT NULL DEFAULT '["*"]',
    disabled_tools TEXT NOT NULL DEFAULT '[]',
    startup_timeout INTEGER NOT NULL DEFAULT 30,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def detect_transport_type(command: str | None, url: str | None) -> str:
    """Auto-detect transport type from command/url fields."""
    if command:
        return "stdio"
    if url:
        if url.rstrip("/").endswith("/sse"):
            return "sse"
        return "streamableHttp"
    return "stdio"


@dataclass
class MCPServerRow:
    server_id: str
    name: str
    enabled: bool
    transport_type: str
    command: str | None
    args: list[str]
    has_env: bool
    url: str | None
    has_headers: bool
    tool_timeout: int
    enabled_tools: list[str]
    disabled_tools: list[str]
    startup_timeout: int
    created_at: datetime
    updated_at: datetime


class McpServerStore(BaseStore):
    @abstractmethod
    async def create_server(
        self,
        name: str,
        transport_type: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        tool_timeout: int = 30,
        enabled_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
        startup_timeout: int = 30,
        enabled: bool = False,
    ) -> MCPServerRow:
        raise NotImplementedError

    @abstractmethod
    async def get_server(self, server_id: str) -> MCPServerRow:
        raise NotImplementedError

    @abstractmethod
    async def update_server(
        self,
        server_id: str,
        name: str | None = None,
        transport_type: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        tool_timeout: int | None = None,
        enabled_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
        startup_timeout: int | None = None,
        enabled: bool | None = None,
    ) -> MCPServerRow:
        raise NotImplementedError

    @abstractmethod
    async def delete_server(self, server_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_servers(self) -> list[MCPServerRow]:
        raise NotImplementedError

    @abstractmethod
    async def get_enabled_servers(self) -> list[MCPServerRow]:
        raise NotImplementedError

    @abstractmethod
    async def get_enabled_server_configs(self) -> list[dict[str, Any]]:
        """Return enabled server configs with decrypted env/headers.

        Each dict has keys matching ``MCPServerConfig`` fields plus
        ``env`` and ``headers`` (decrypted).
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class SQLiteMcpServerStore(McpServerStore):
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db_manager = db_manager
        db_manager.add_schema(_MCP_SERVER_SCHEMA_SQL)

    async def create_server(
        self,
        name: str,
        transport_type: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        tool_timeout: int = 30,
        enabled_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
        startup_timeout: int = 30,
        enabled: bool = False,
    ) -> MCPServerRow:
        db = await self._db_manager.connect()
        now = DatabaseManager.now()
        timestamp = DatabaseManager.format_dt(now)
        server_id = str(uuid.uuid4())

        tt = transport_type or detect_transport_type(command, url)

        env_json = json.dumps(env or {}, ensure_ascii=False)
        env_encrypted = encrypt_api_key(env_json) if env else None
        headers_json = json.dumps(headers or {}, ensure_ascii=False)
        headers_encrypted = encrypt_api_key(headers_json) if headers else None
        args_json = json.dumps(args or [], ensure_ascii=False)
        enabled_tools_json = json.dumps(enabled_tools or ["*"], ensure_ascii=False)
        disabled_tools_json = json.dumps(disabled_tools or [], ensure_ascii=False)

        await db.execute(
            """
            INSERT INTO mcp_servers
                (server_id, name, enabled, transport_type, command, args, env,
                 url, headers, tool_timeout, enabled_tools, disabled_tools,
                 startup_timeout, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                server_id,
                name,
                1 if enabled else 0,
                tt,
                command,
                args_json,
                env_encrypted,
                url,
                headers_encrypted,
                tool_timeout,
                enabled_tools_json,
                disabled_tools_json,
                startup_timeout,
                timestamp,
                timestamp,
            ),
        )
        await db.commit()
        return MCPServerRow(
            server_id=server_id,
            name=name,
            enabled=enabled,
            transport_type=tt,
            command=command,
            args=args or [],
            has_env=bool(env),
            url=url,
            has_headers=bool(headers),
            tool_timeout=tool_timeout,
            enabled_tools=enabled_tools or ["*"],
            disabled_tools=disabled_tools or [],
            startup_timeout=startup_timeout,
            created_at=now,
            updated_at=now,
        )

    async def get_server(self, server_id: str) -> MCPServerRow:
        db = await self._db_manager.connect()
        async with db.execute(
            "SELECT * FROM mcp_servers WHERE server_id = ?",
            (server_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ServerNotFoundError(server_id)
        return self._row_to_server(row)

    async def update_server(
        self,
        server_id: str,
        name: str | None = None,
        transport_type: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        tool_timeout: int | None = None,
        enabled_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
        startup_timeout: int | None = None,
        enabled: bool | None = None,
    ) -> MCPServerRow:
        db = await self._db_manager.connect()
        now = DatabaseManager.format_dt(DatabaseManager.now())

        fields: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]

        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if transport_type is not None:
            fields.append("transport_type = ?")
            params.append(transport_type)
        if command is not None:
            fields.append("command = ?")
            params.append(command)
        if args is not None:
            fields.append("args = ?")
            params.append(json.dumps(args, ensure_ascii=False))
        if env is not None:
            env_json = json.dumps(env, ensure_ascii=False)
            fields.append("env = ?")
            params.append(encrypt_api_key(env_json))
        elif env is not None:
            fields.append("env = NULL")
        if url is not None:
            fields.append("url = ?")
            params.append(url)
        if headers is not None:
            headers_json = json.dumps(headers, ensure_ascii=False)
            fields.append("headers = ?")
            params.append(encrypt_api_key(headers_json))
        elif headers is not None:
            fields.append("headers = NULL")
        if tool_timeout is not None:
            fields.append("tool_timeout = ?")
            params.append(tool_timeout)
        if enabled_tools is not None:
            fields.append("enabled_tools = ?")
            params.append(json.dumps(enabled_tools, ensure_ascii=False))
        if disabled_tools is not None:
            fields.append("disabled_tools = ?")
            params.append(json.dumps(disabled_tools, ensure_ascii=False))
        if startup_timeout is not None:
            fields.append("startup_timeout = ?")
            params.append(startup_timeout)
        if enabled is not None:
            fields.append("enabled = ?")
            params.append(1 if enabled else 0)

        params.append(server_id)
        sql = f"UPDATE mcp_servers SET {', '.join(fields)} WHERE server_id = ?"
        cursor = await db.execute(sql, params)
        await db.commit()
        if cursor.rowcount == 0:
            raise ServerNotFoundError(server_id)
        return await self.get_server(server_id)

    async def delete_server(self, server_id: str) -> None:
        db = await self._db_manager.connect()
        cursor = await db.execute(
            "DELETE FROM mcp_servers WHERE server_id = ?",
            (server_id,),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise ServerNotFoundError(server_id)

    async def list_servers(self) -> list[MCPServerRow]:
        db = await self._db_manager.connect()
        async with db.execute(
            "SELECT * FROM mcp_servers ORDER BY created_at ASC",
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_server(row) for row in rows]

    async def get_enabled_servers(self) -> list[MCPServerRow]:
        db = await self._db_manager.connect()
        async with db.execute(
            "SELECT * FROM mcp_servers WHERE enabled = 1 ORDER BY created_at ASC",
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_server(row) for row in rows]

    async def get_enabled_server_configs(self) -> list[dict[str, Any]]:
        db = await self._db_manager.connect()
        async with db.execute(
            "SELECT * FROM mcp_servers WHERE enabled = 1 ORDER BY created_at ASC",
        ) as cursor:
            rows = await cursor.fetchall()
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = self._row_to_server(raw)
            config: dict[str, Any] = {
                "name": row.name,
                "transport_type": row.transport_type,
                "command": row.command,
                "args": row.args,
                "url": row.url,
                "tool_timeout": row.tool_timeout,
                "enabled_tools": row.enabled_tools,
                "disabled_tools": row.disabled_tools,
                "startup_timeout": row.startup_timeout,
                "enabled": row.enabled,
                "env": None,
                "headers": None,
            }
            # Decrypt env
            if row.has_env and raw["env"]:
                try:
                    config["env"] = json.loads(decrypt_api_key(raw["env"]))
                except Exception:
                    logger.warning("Failed to decrypt env for server {}", row.server_id)
            # Decrypt headers
            if row.has_headers and raw["headers"]:
                try:
                    config["headers"] = json.loads(decrypt_api_key(raw["headers"]))
                except Exception:
                    logger.warning(
                        "Failed to decrypt headers for server {}", row.server_id
                    )
            result.append(config)
        return result

    async def close(self) -> None:
        pass

    def _row_to_server(self, row: aiosqlite.Row) -> MCPServerRow:
        return MCPServerRow(
            server_id=row["server_id"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            transport_type=row["transport_type"] or "stdio",
            command=row["command"],
            args=json.loads(row["args"]) if row["args"] else [],
            has_env=bool(row["env"]),
            url=row["url"],
            has_headers=bool(row["headers"]),
            tool_timeout=row["tool_timeout"],
            enabled_tools=json.loads(row["enabled_tools"])
            if row["enabled_tools"]
            else ["*"],
            disabled_tools=json.loads(row["disabled_tools"])
            if row["disabled_tools"]
            else [],
            startup_timeout=row["startup_timeout"],
            created_at=DatabaseManager.parse_dt(row["created_at"]),
            updated_at=DatabaseManager.parse_dt(row["updated_at"]),
        )


class ServerNotFoundError(Exception):
    def __init__(self, server_id: str) -> None:
        self.server_id = server_id
        super().__init__(f"MCP server '{server_id}' not found")


class ServerNameConflictError(Exception):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"MCP server name '{name}' already exists")
