"""Consolidated memory storage — single-record table for merged memories."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

_CONSOLIDATED_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS consolidated_memory (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL DEFAULT '',
    source_memory_ids TEXT NOT NULL DEFAULT '[]',
    last_consolidated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class ConsolidatedMemoryNotFoundError(Exception):
    """Raised when no consolidated memory exists."""


class ConsolidatedMemoryStore:
    """Manages a single consolidated memory record.

    The table is constrained to a single row (id='default') to enforce
    the design invariant of one consolidated memory.
    """

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
            await self._db.executescript(_CONSOLIDATED_SCHEMA_SQL)
            await self._db.commit()
        return self._db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    async def get(self) -> dict[str, Any] | None:
        """Return the consolidated memory record, or None if absent."""
        db = await self._ensure_db()
        async with db.execute(
            "SELECT * FROM consolidated_memory WHERE id = 'default'"
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "content": row["content"],
            "source_memory_ids": json.loads(row["source_memory_ids"]),
            "last_consolidated_at": row["last_consolidated_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    async def upsert(
        self,
        content: str,
        source_memory_ids: list[str],
    ) -> None:
        """Insert or replace the single consolidated memory row."""
        db = await self._ensure_db()
        now = self._format_dt(self._now())
        source_ids_json = json.dumps(source_memory_ids, ensure_ascii=False)

        existing = await self.get()
        if existing is None:
            await db.execute(
                """
                INSERT INTO consolidated_memory (id, content, source_memory_ids, last_consolidated_at, created_at, updated_at)
                VALUES ('default', ?, ?, ?, ?, ?)
                """,
                (content, source_ids_json, now, now, now),
            )
        else:
            await db.execute(
                """
                UPDATE consolidated_memory
                SET content = ?, source_memory_ids = ?, last_consolidated_at = ?, updated_at = ?
                WHERE id = 'default'
                """,
                (content, source_ids_json, now, now),
            )
        await db.commit()

    async def get_source_ids(self) -> list[str]:
        """Return the list of already-consolidated raw memory IDs."""
        record = await self.get()
        if record is None:
            return []
        return list(record["source_memory_ids"])

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
