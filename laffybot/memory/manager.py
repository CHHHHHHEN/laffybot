"""Lifecycle container for the memory system."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from laffybot.memory.config import MemoryConfig
from laffybot.memory.store import MemoryStore, SQLiteMemoryStore

if TYPE_CHECKING:
    from laffybot.providers.base import BaseProvider


class MemoryManager:
    """Owns memory lifecycle: initialisation, extraction, and resource management."""

    def __init__(
        self,
        config: MemoryConfig,
        store: MemoryStore | None = None,
        db_path: str | None = None,
    ) -> None:
        self._config = config
        self._store: MemoryStore | None = store
        self._db_path = db_path

    @property
    def config(self) -> MemoryConfig:
        return self._config

    @property
    def store(self) -> MemoryStore | None:
        return self._store

    async def initialize(self) -> None:
        if self._store is None and self._db_path is not None:
            self._store = SQLiteMemoryStore(self._db_path)

        logger.info(
            "Memory system initialized: enabled={}",
            self._config.enabled,
        )

    async def extract(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        provider: BaseProvider,
        model: str,
    ) -> str | None:
        """Coordinate memory extraction from session messages.

        Returns memory_id if persisted, None if skipped/no-op.
        """
        log = logger.bind(session_id=session_id)

        if self._store is None:
            log.warning("Memory store not available")
            return None

        existing = await self._store.get_memories_by_session(session_id)
        if existing:
            log.debug("Memory extraction skipped (already exists)")
            return cast(str, existing[0]["memory_id"])

        from laffybot.memory.extractor import MemoryExtractor

        extractor = MemoryExtractor(provider=provider, model=model)
        result = await extractor.extract(messages)

        if result is None:
            log.debug("Memory extraction no-op: session_id={}", session_id)
            return None

        content, tags = result
        memory_id = await self._store.save_memory(
            session_id=session_id,
            content=content,
            tags=tags,
        )
        log.info("Memory extracted: session_id={}, memory_id={}", session_id, memory_id)
        return memory_id

    async def close(self) -> None:
        if self._store is not None:
            await self._store.close()
        logger.info("Memory system shut down")
