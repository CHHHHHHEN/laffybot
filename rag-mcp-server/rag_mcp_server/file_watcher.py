from __future__ import annotations

import time
from pathlib import Path
from threading import Thread
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from rag_mcp_server.logger import get_logger


class FileChangeHandler(FileSystemEventHandler):  # type: ignore[misc]
    def __init__(
        self,
        on_created: Callable[[str], None],
        on_modified: Callable[[str], None],
        on_deleted: Callable[[str], None],
        debounce_seconds: float = 1.0,
    ) -> None:
        super().__init__()
        self._on_created = on_created
        self._on_modified = on_modified
        self._on_deleted = on_deleted
        self._debounce_seconds = debounce_seconds
        self._last_triggered: dict[str, float] = {}
        self._logger = get_logger("rag_mcp_server.watcher")

    def _debounce(self, path: str) -> bool:
        now = time.monotonic()
        last = self._last_triggered.get(path, 0.0)
        if now - last < self._debounce_seconds:
            return True
        self._last_triggered[path] = now
        return False

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = str(event.src_path)
        if self._debounce(path):
            return
        self._logger.info("[watcher] file created: %s", path)
        self._on_created(path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = str(event.src_path)
        if self._debounce(path):
            return
        self._logger.info("[watcher] file modified: %s", path)
        self._on_modified(path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = str(event.src_path)
        if self._debounce(path):
            return
        self._logger.info("[watcher] file deleted: %s", path)
        self._on_deleted(path)


class FileWatcher:
    def __init__(self, debounce_ms: int = 1000) -> None:
        self._debounce_seconds = debounce_ms / 1000.0
        self._observer: Observer | None = None
        self._handler: FileChangeHandler | None = None
        self._paths: list[str] = []
        self._watch_thread: Thread | None = None
        self._running = False
        self._logger = get_logger("rag_mcp_server.watcher")

    def start(
        self,
        paths: list[str],
        on_created: Callable[[str], None],
        on_modified: Callable[[str], None],
        on_deleted: Callable[[str], None],
    ) -> None:
        if self._running:
            return

        self._paths = list(paths)
        self._handler = FileChangeHandler(
            on_created=on_created,
            on_modified=on_modified,
            on_deleted=on_deleted,
            debounce_seconds=self._debounce_seconds,
        )
        self._observer = Observer()

        for p in self._paths:
            resolved = Path(p).expanduser().resolve()
            if resolved.is_dir():
                self._observer.schedule(self._handler, str(resolved), recursive=True)
                self._logger.info("[watcher] watching path: %s", resolved)

        self._running = True
        self._watch_thread = Thread(target=self._observer.start, daemon=True)
        self._watch_thread.start()
        self._logger.info("[watcher] file watcher started: paths=%s", self._paths)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._logger.info("[watcher] file watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def watched_paths(self) -> list[str]:
        return list(self._paths)
