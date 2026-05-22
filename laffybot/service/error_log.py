"""Error log service — in-memory ring buffer + JSONL file persistence.

Provides a central sink for error records from all parts of the system
(SSE streaming errors, API handlers, background tasks). The ring buffer
is exposed via API for the frontend; the JSONL file provides persistence
across process restarts.
"""

from __future__ import annotations

import asyncio
import json
import os
import traceback as tb
from collections import deque
from datetime import datetime, timezone
from typing import Any


class ErrorRecord:
    """A single error record with context for debugging."""

    __slots__ = (
        "timestamp",
        "level",
        "source",
        "message",
        "session_id",
        "request_id",
        "error_code",
        "traceback",
    )

    def __init__(
        self,
        *,
        level: str,
        source: str,
        message: str,
        session_id: str | None = None,
        request_id: str | None = None,
        error_code: str | None = None,
        traceback: str | None = None,
    ) -> None:
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.level = level
        self.source = source
        self.message = message
        self.session_id = session_id
        self.request_id = request_id
        self.error_code = error_code
        self.traceback = traceback

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp,
            "level": self.level,
            "source": self.source,
            "message": self.message,
        }
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.request_id is not None:
            d["request_id"] = self.request_id
        if self.error_code is not None:
            d["error_code"] = self.error_code
        if self.traceback is not None:
            d["traceback"] = self.traceback
        return d


class ErrorLogService:
    """Central error collection service.

    Maintains an in-memory ring buffer of the most recent N errors and
    optionally persists them to a JSONL file for survival across restarts.
    """

    def __init__(
        self,
        max_records: int = 200,
        jsonl_path: str | None = None,
    ) -> None:
        self._max_records = max_records
        self._jsonl_path = jsonl_path
        self._records: deque[ErrorRecord] = deque(maxlen=max_records)
        self._lock = asyncio.Lock()

    # ── Public API ───────────────────────────────────────────────────────

    def record(
        self,
        *,
        level: str = "ERROR",
        source: str = "",
        message: str,
        session_id: str | None = None,
        request_id: str | None = None,
        error_code: str | None = None,
        exc_info: BaseException | None = None,
    ) -> None:
        """Record an error. Thread-safe via asyncio.Lock when called from async code;
        for synchronous callers (loguru sink), uses a fire-and-forget pattern.
        """
        traceback_str: str | None = None
        if exc_info is not None:
            traceback_str = "".join(
                tb.format_exception(type(exc_info), exc_info, exc_info.__traceback__)
            ).strip()

        record = ErrorRecord(
            level=level,
            source=source,
            message=message,
            session_id=session_id,
            request_id=request_id,
            error_code=error_code,
            traceback=traceback_str,
        )

        # Synchronous path for loguru sink
        self._records.append(record)
        self._try_append_jsonl(record)

    async def record_async(
        self,
        *,
        level: str = "ERROR",
        source: str = "",
        message: str,
        session_id: str | None = None,
        request_id: str | None = None,
        error_code: str | None = None,
        exc_info: BaseException | None = None,
    ) -> None:
        """Async variant that acquires the lock."""
        async with self._lock:
            self.record(
                level=level,
                source=source,
                message=message,
                session_id=session_id,
                request_id=request_id,
                error_code=error_code,
                exc_info=exc_info,
            )

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent N error records."""
        records = list(self._records)
        records.reverse()
        return [r.to_dict() for r in records[:limit]]

    @property
    def count(self) -> int:
        return len(self._records)

    # ── JSONL persistence ────────────────────────────────────────────────

    def _try_append_jsonl(self, record: ErrorRecord) -> None:
        if self._jsonl_path is None:
            return
        try:
            os.makedirs(os.path.dirname(self._jsonl_path), exist_ok=True)
            with open(self._jsonl_path, "a") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass  # best-effort

    def load_from_jsonl(self) -> None:
        """Load persisted errors from the JSONL file into the ring buffer."""
        if self._jsonl_path is None or not os.path.isfile(self._jsonl_path):
            return
        try:
            with open(self._jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    record = ErrorRecord(
                        level=data.get("level", "ERROR"),
                        source=data.get("source", ""),
                        message=data.get("message", ""),
                        session_id=data.get("session_id"),
                        request_id=data.get("request_id"),
                        error_code=data.get("error_code"),
                        traceback=data.get("traceback"),
                    )
                    record.timestamp = data.get("timestamp", record.timestamp)
                    self._records.append(record)
        except OSError:
            pass


# Module-level singleton (lazy init, set by composition root)
_error_log_service: ErrorLogService | None = None


def get_error_log() -> ErrorLogService:
    """Get the global ErrorLogService singleton."""
    assert _error_log_service is not None, "ErrorLogService not initialized"
    return _error_log_service


def set_error_log(service: ErrorLogService) -> None:
    """Set the global ErrorLogService singleton (called from composition root)."""
    global _error_log_service
    _error_log_service = service
