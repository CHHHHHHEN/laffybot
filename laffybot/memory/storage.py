"""File-system interaction layer for memory storage (deprecated).

All memory operations now go through MemoryStore/SQLiteMemoryStore.
This module is retained as a no-op stub for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path


class MemoryStorage:
    """Deprecated. Memory is now stored in the database."""

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir.resolve()
        self._summaries_dir = self._root / "session_summaries"
        self._phase2_dir = self._root / "phase2_output"

    @property
    def root_dir(self) -> Path:
        return self._root

    def ensure_directories(self) -> None:
        pass

    def write_summary(self, session_id: str, content: str) -> None:
        pass

    def read_summary(self, session_id: str) -> str | None:
        return None

    def list_summaries(self) -> list[Path]:
        return []

    def delete_summary(self, session_id: str) -> bool:
        return False
