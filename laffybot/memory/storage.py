"""File-system interaction layer for memory storage."""

from __future__ import annotations

from pathlib import Path


class MemoryStorage:
    """Low-level file-system operations for the memory system.

    Handles directory creation, summary file read/write and listing.
    Directory creation is triggered by the owner (MemoryManager).
    Metadata format is a concern of upper layers.
    """

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir.resolve()
        self._summaries_dir = self._root / "session_summaries"
        self._phase2_dir = self._root / "phase2_output"

    @property
    def root_dir(self) -> Path:
        return self._root

    @property
    def summaries_dir(self) -> Path:
        return self._summaries_dir

    def ensure_directories(self) -> None:
        """Create the full memory directory tree.

        Called once during module initialisation.
        """
        self._summaries_dir.mkdir(parents=True, exist_ok=True)
        self._phase2_dir.mkdir(parents=True, exist_ok=True)
        (self._root / "INDEX.md").touch(exist_ok=True)

    def summary_path(self, session_id: str) -> Path:
        return self._summaries_dir / f"{session_id}.md"

    def write_summary(self, session_id: str, content: str) -> None:
        """Write a session summary file. Overwrites if it already exists."""
        self.summary_path(session_id).write_text(content, encoding="utf-8")

    def read_summary(self, session_id: str) -> str | None:
        """Read a session summary file. Returns None if it does not exist."""
        path = self.summary_path(session_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def list_summaries(self) -> list[Path]:
        """Return all existing session summary file paths sorted by name."""
        if not self._summaries_dir.exists():
            return []
        return sorted(self._summaries_dir.glob("*.md"))

    def delete_summary(self, session_id: str) -> bool:
        """Delete a session summary file. Returns True if it existed."""
        path = self.summary_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True
