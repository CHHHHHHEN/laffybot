"""Database persistence layer for memories."""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from laffybot.memory.exceptions import MemoryNotFoundError

_MEMORIES_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0,
    last_usage TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories(session_id);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
"""


class MemoryStore(ABC):
    @abstractmethod
    async def save_memory(
        self, session_id: str, content: str, tags: list[str] | None = None
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def list_memories(
        self,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        raise NotImplementedError

    @abstractmethod
    async def get_memories_by_session(self, session_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def delete_memory(self, memory_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class SQLiteMemoryStore(MemoryStore):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            db_path = self.db_path
            if db_path != ":memory:":
                Path(db_path).expanduser().resolve().parent.mkdir(
                    parents=True, exist_ok=True
                )
            self._db = await aiosqlite.connect(db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA foreign_keys = ON")
            await self._db.executescript(_MEMORIES_SCHEMA_SQL)
            await self._db.commit()
        return self._db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _row_to_memory(
        row: aiosqlite.Row, include_session_title: bool = False
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "memory_id": row["memory_id"],
            "session_id": row["session_id"],
            "content": row["content"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "usage_count": row["usage_count"],
            "last_usage": row["last_usage"],
        }
        if include_session_title and "session_title" in row.keys():
            result["session_title"] = row["session_title"]
        return result

    async def save_memory(
        self, session_id: str, content: str, tags: list[str] | None = None
    ) -> str:
        db = await self._ensure_db()
        memory_id = str(uuid.uuid4())
        now = self._format_dt(self._now())
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        await db.execute(
            """
            INSERT INTO memories (memory_id, session_id, content, tags, created_at, updated_at, usage_count, last_usage)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (memory_id, session_id, content, tags_json, now, now, now),
        )
        await db.commit()
        return memory_id

    async def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        db = await self._ensure_db()
        async with db.execute(
            """
            SELECT m.*, s.title AS session_title
            FROM memories m
            LEFT JOIN sessions s ON s.session_id = m.session_id
            WHERE m.memory_id = ?
            """,
            (memory_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_memory(row, include_session_title=True)

    async def list_memories(
        self,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        db = await self._ensure_db()
        clauses: list[str] = []
        params: list[Any] = []
        if search:
            clauses.append("m.content LIKE ?")
            params.append(f"%{search}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        count_sql = f"SELECT COUNT(*) AS total FROM memories m {where}"
        async with db.execute(count_sql, params) as cursor:
            count_row = await cursor.fetchone()
        total = int(count_row["total"]) if count_row else 0

        query = f"""
            SELECT m.*, s.title AS session_title
            FROM memories m
            LEFT JOIN sessions s ON s.session_id = m.session_id
            {where}
            ORDER BY m.created_at DESC
            LIMIT ? OFFSET ?
        """
        async with db.execute(query, [*params, limit, offset]) as cursor:
            rows = await cursor.fetchall()
        return [
            self._row_to_memory(row, include_session_title=True) for row in rows
        ], total

    async def get_memories_by_session(self, session_id: str) -> list[dict[str, Any]]:
        db = await self._ensure_db()
        async with db.execute(
            "SELECT * FROM memories WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_memory(row) for row in rows]

    async def delete_memory(self, memory_id: str) -> None:
        db = await self._ensure_db()
        cursor = await db.execute(
            "DELETE FROM memories WHERE memory_id = ?", (memory_id,)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise MemoryNotFoundError(memory_id)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.debug("Memory store closed")
