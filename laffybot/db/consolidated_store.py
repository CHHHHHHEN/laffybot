"""Consolidated memory storage — single-record table for merged memories."""

from __future__ import annotations

import json
from typing import Any

from laffybot.db.base import BaseStore
from laffybot.db.manager import DatabaseManager

_CONSOLIDATED_SCHEMA_SQL = """
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


class ConsolidatedMemoryStore(BaseStore):
    """Manages a single consolidated memory record.

    The table is constrained to a single row (id='default') to enforce
    the design invariant of one consolidated memory.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db_manager = db_manager
        db_manager.add_schema(_CONSOLIDATED_SCHEMA_SQL)

    async def get(self) -> dict[str, Any] | None:
        """Return the consolidated memory record, or None if absent."""
        db = await self._db_manager.connect()
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
        db = await self._db_manager.connect()
        now = DatabaseManager.format_dt(DatabaseManager.now())
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
        pass
