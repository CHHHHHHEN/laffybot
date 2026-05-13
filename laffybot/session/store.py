"""SQLite-backed persistence for sessions and messages."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from laffybot.session.errors import (
    SessionNotFoundError,
    SessionStateError,
)
from laffybot.session.models import (
    MessageRole,
    SessionInfo,
    SessionMessage,
    SessionStatus,
    validate_role,
    validate_status,
)

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    current_request_id TEXT,
    error_message TEXT,
    system_prompt TEXT,
    max_iterations INTEGER NOT NULL DEFAULT 10
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
"""

_MIGRATION_SQL = """
-- Migration: Add token columns to messages table (idempotent)
-- SQLite doesn't support IF NOT EXISTS for columns, so we check first
"""


class SessionStore(ABC):
    """Abstract session persistence contract."""

    @abstractmethod
    async def create_session(
        self,
        session_id: str,
        model: str,
        system_prompt: str | None,
        max_iterations: int,
    ) -> SessionInfo:
        raise NotImplementedError

    @abstractmethod
    async def get_session(self, session_id: str) -> SessionInfo:
        raise NotImplementedError

    @abstractmethod
    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        current_request_id: str | None = None,
        error_message: str | None = None,
        expected_status: SessionStatus | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SessionInfo], int]:
        raise NotImplementedError

    @abstractmethod
    async def save_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> SessionMessage:
        raise NotImplementedError

    @abstractmethod
    async def get_messages(
        self,
        session_id: str,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[SessionMessage]:
        raise NotImplementedError

    @abstractmethod
    async def get_message_count(self, session_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class SQLiteStore(SessionStore):
    """SQLite implementation of the session store."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            db_path = self.db_path
            if db_path != ":memory:":
                Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA foreign_keys = ON")
            await self._db.executescript(_SCHEMA_SQL)
            await self._db.commit()
            # Run migrations
            await self._run_migrations(self._db)
        return self._db

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        """Run database migrations for schema updates."""
        # Migration 1: Add token columns to messages table
        async with db.execute("PRAGMA table_info(messages)") as cursor:
            columns = {row["name"] for row in await cursor.fetchall()}

        if "input_tokens" not in columns:
            await db.execute("ALTER TABLE messages ADD COLUMN input_tokens INTEGER")
        if "output_tokens" not in columns:
            await db.execute("ALTER TABLE messages ADD COLUMN output_tokens INTEGER")
        await db.commit()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _row_to_session(row: aiosqlite.Row) -> SessionInfo:
        return SessionInfo(
            session_id=row["session_id"],
            model=row["model"],
            status=validate_status(row["status"]),
            created_at=SQLiteStore._parse_dt(row["created_at"]),
            updated_at=SQLiteStore._parse_dt(row["updated_at"]),
            message_count=row["message_count"],
            current_request_id=row["current_request_id"],
            error_message=row["error_message"],
            system_prompt=row["system_prompt"],
            max_iterations=row["max_iterations"],
        )

    @staticmethod
    def _row_to_message(row: aiosqlite.Row) -> SessionMessage:
        message: SessionMessage = {
            "role": validate_role(row["role"]),
            "content": row["content"],
            "timestamp": row["timestamp"],
        }
        metadata = row["metadata"]
        if metadata:
            message["metadata"] = json.loads(metadata)
        # Include token counts if available
        if row["input_tokens"] is not None:
            message["input_tokens"] = row["input_tokens"]
        if row["output_tokens"] is not None:
            message["output_tokens"] = row["output_tokens"]
        return message

    async def create_session(
        self,
        session_id: str,
        model: str,
        system_prompt: str | None,
        max_iterations: int,
    ) -> SessionInfo:
        db = await self._ensure_db()
        now = self._now()
        timestamp = self._format_dt(now)
        await db.execute(
            """
            INSERT INTO sessions (
                session_id, model, status, created_at, updated_at,
                message_count, current_request_id, error_message,
                system_prompt, max_iterations
            ) VALUES (?, ?, 'idle', ?, ?, 0, NULL, NULL, ?, ?)
            """,
            (session_id, model, timestamp, timestamp, system_prompt, max_iterations),
        )
        await db.commit()
        return SessionInfo(
            session_id=session_id,
            model=model,
            status="idle",
            created_at=now,
            updated_at=now,
            message_count=0,
            system_prompt=system_prompt,
            max_iterations=max_iterations,
        )

    async def get_session(self, session_id: str) -> SessionInfo:
        db = await self._ensure_db()
        async with db.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise SessionNotFoundError(session_id)
        return self._row_to_session(row)

    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        current_request_id: str | None = None,
        error_message: str | None = None,
        expected_status: SessionStatus | None = None,
    ) -> bool:
        db = await self._ensure_db()
        now = self._format_dt(self._now())
        sql = """
            UPDATE sessions
            SET status = ?, current_request_id = ?, error_message = ?, updated_at = ?
            WHERE session_id = ?
        """
        params: list[Any] = [status, current_request_id, error_message, now, session_id]
        if expected_status is not None:
            sql += " AND status = ?"
            params.append(expected_status)
        cursor = await db.execute(sql, params)
        await db.commit()
        if cursor.rowcount and cursor.rowcount > 0:
            return True
        try:
            current = await self.get_session(session_id)
        except SessionNotFoundError:
            raise
        if expected_status is not None:
            raise SessionStateError(session_id, current.status)
        raise SessionNotFoundError(session_id)

    async def delete_session(self, session_id: str) -> None:
        db = await self._ensure_db()
        cursor = await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise SessionNotFoundError(session_id)

    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SessionInfo], int]:
        db = await self._ensure_db()
        clauses = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        count_sql = f"SELECT COUNT(*) AS total FROM sessions {where}"
        async with db.execute(count_sql, params) as cursor:
            count_row = await cursor.fetchone()
        total = int(count_row["total"] if count_row is not None else 0)
        query = f"SELECT * FROM sessions {where} ORDER BY updated_at DESC, session_id DESC LIMIT ? OFFSET ?"
        async with db.execute(query, [*params, limit, offset]) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows], total

    async def save_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> SessionMessage:
        db = await self._ensure_db()
        timestamp = self._format_dt(self._now())
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else None
        await db.execute("BEGIN")
        try:
            await db.execute(
                """
                INSERT INTO messages (session_id, role, content, timestamp, metadata, input_tokens, output_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, role, content, timestamp, metadata_json, input_tokens, output_tokens),
            )
            await db.execute(
                """
                UPDATE sessions
                SET message_count = message_count + 1, updated_at = ?
                WHERE session_id = ?
                """,
                (timestamp, session_id),
            )
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            await db.rollback()
            raise SessionNotFoundError(session_id) from exc
        except Exception:
            await db.rollback()
            raise
        result: SessionMessage = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
        }
        if metadata is not None:
            result["metadata"] = metadata
        if input_tokens is not None:
            result["input_tokens"] = input_tokens
        if output_tokens is not None:
            result["output_tokens"] = output_tokens
        return result

    async def get_messages(
        self,
        session_id: str,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[SessionMessage]:
        db = await self._ensure_db()
        clauses = ["session_id = ?"]
        params: list[Any] = [session_id]
        if before is not None:
            clauses.append("timestamp < ?")
            params.append(self._format_dt(before))
        query = (
            "SELECT role, content, timestamp, metadata, input_tokens, output_tokens FROM messages "
            f"WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC, id ASC LIMIT ?"
        )
        async with db.execute(query, [*params, limit]) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            # Verify session exists
            await self.get_session(session_id)
        return [self._row_to_message(row) for row in rows]

    async def get_message_count(self, session_id: str) -> int:
        session = await self.get_session(session_id)
        return session.message_count

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
