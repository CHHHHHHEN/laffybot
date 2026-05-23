"""Shared database connection manager — single connection owned by composition root.

All stores share one DatabaseManager instance to avoid connection proliferation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


class DatabaseManager:
    """Manages a single SQLite connection shared by all stores.

    Schema registration (add_schema) allows each store to declare its DDL at
    import time; the manager runs all schemas in a single transaction on first
    connect.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._schemas: list[str] = []

    def add_schema(self, sql: str) -> None:
        self._schemas.append(sql)

    async def connect(self) -> aiosqlite.Connection:
        if self._db is not None:
            return self._db
        db_path = self.db_path
        if db_path != ":memory:":
            Path(db_path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        self._db = await aiosqlite.connect(db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        for schema in self._schemas:
            await self._db.executescript(schema)
        await self._db.commit()
        return self._db

    async def execute(self, sql: str, parameters: object = None) -> aiosqlite.Cursor:
        db = await self.connect()
        return (
            await db.execute(sql, parameters)
            if parameters is not None
            else await db.execute(sql)
        )

    async def commit(self) -> None:
        if self._db is not None:
            await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def format_dt(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def parse_dt(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
