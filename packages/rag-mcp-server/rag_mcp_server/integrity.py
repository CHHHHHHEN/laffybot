from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

_SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestion_history (
    file_hash TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'processing')),
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_msg TEXT,
    chunk_count INTEGER
);
"""

Status = Literal["success", "failed", "processing"]


class IngestionHistoryDB:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SQL_SCHEMA)
        self._conn.commit()

    def compute_hash(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                sha256.update(block)
        return sha256.hexdigest()

    def has_changed(self, file_path: str) -> bool:
        try:
            current_hash = self.compute_hash(file_path)
        except (FileNotFoundError, PermissionError, OSError):
            return True
        row = self._conn.execute(
            "SELECT file_hash FROM ingestion_history WHERE file_path = ? AND status = 'success'",
            (file_path,),
        ).fetchone()
        if row is None:
            return True
        return row[0] != current_hash  # type: ignore[no-any-return]

    def record(
        self,
        file_path: str,
        status: Status,
        chunk_count: int = 0,
        error_msg: str | None = None,
    ) -> None:
        try:
            file_hash = self.compute_hash(file_path)
            file_size = Path(file_path).stat().st_size
        except (FileNotFoundError, PermissionError, OSError):
            file_hash = ""
            file_size = 0

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO ingestion_history
               (file_hash, file_path, file_size, status, processed_at, error_msg, chunk_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (file_hash, file_path, file_size, status, now, error_msg, chunk_count),
        )
        self._conn.commit()

    def remove(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM ingestion_history WHERE file_path = ?", (file_path,))
        self._conn.commit()

    def get_summary(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(chunk_count), 0) FROM ingestion_history WHERE status = 'success'"
        ).fetchone()
        return {
            "total_files": row[0] if row else 0,
            "total_chunks": row[1] if row else 0,
        }

    def close(self) -> None:
        self._conn.close()
