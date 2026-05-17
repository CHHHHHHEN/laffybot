"""Lifecycle container for the memory system."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from laffybot.context.tokens import ApproximateTokenCounter
from laffybot.memory.config import MemoryConfig
from laffybot.memory.consolidated_store import ConsolidatedMemoryStore
from laffybot.memory.store import MemoryStore, SQLiteMemoryStore

if TYPE_CHECKING:
    from laffybot.memory.consolidator import MemoryConsolidator
    from laffybot.providers.base import BaseProvider


class MemoryManager:
    """Owns memory lifecycle: initialisation, extraction, and resource management."""

    def __init__(
        self,
        config: MemoryConfig,
        store: MemoryStore | None = None,
        db_path: str | None = None,
        consolidator: MemoryConsolidator | None = None,
    ) -> None:
        self._config = config
        self._store: MemoryStore | None = store
        self._db_path = db_path
        self._consolidated_store: ConsolidatedMemoryStore | None = None
        self._consolidator: MemoryConsolidator | None = consolidator

    @property
    def config(self) -> MemoryConfig:
        return self._config

    @property
    def store(self) -> MemoryStore | None:
        return self._store

    @property
    def consolidator(self) -> MemoryConsolidator | None:
        return self._consolidator

    @property
    def consolidated_store(self) -> ConsolidatedMemoryStore | None:
        return self._consolidated_store

    async def initialize(self) -> None:
        if self._store is None and self._db_path is not None:
            self._store = SQLiteMemoryStore(self._db_path)

        if self._db_path is not None:
            self._consolidated_store = ConsolidatedMemoryStore(self._db_path)

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
        After saving, triggers consolidation asynchronously.
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

        if self._consolidator is not None:
            asyncio.create_task(self._consolidator.try_consolidate())

        return memory_id

    async def get_memories_for_injection(
        self, top_n: int, max_tokens: int
    ) -> list[dict[str, Any]]:
        """Return structured memory list for context injection.

        Delegates to MemoryStore for scoring, then truncates by token budget.
        Each item contains memory_id, content, tags, and session_title.

        Returns empty list when store is unavailable or no memories exist.
        """
        if self._store is None:
            return []

        candidates = await self._store.get_top_memories(top_n)
        if not candidates:
            return []

        token_counter = ApproximateTokenCounter()
        result: list[dict[str, Any]] = []
        total_tokens = 0

        for mem in candidates:
            mem_tokens = token_counter.count_tokens(mem["content"])
            if total_tokens + mem_tokens > max_tokens and result:
                break
            result.append(
                {
                    "memory_id": mem["memory_id"],
                    "content": mem["content"],
                    "tags": mem["tags"],
                    "session_title": mem.get("session_title"),
                }
            )
            total_tokens += mem_tokens

        return result

    async def get_injection_content(
        self, max_tokens: int
    ) -> list[dict[str, Any]] | None:
        """Return consolidated memory content for context injection.

        Priority:
        1. Consolidated memory exists → return as single-item list
        2. No consolidated memory → fall back to get_memories_for_injection
        3. Consolidated memory exceeds max_tokens → truncate then return

        Returns None when no content is available at all.
        """
        consolidated = None
        if self._consolidated_store is not None:
            consolidated = await self._consolidated_store.get()

        if consolidated is not None and consolidated["content"]:
            content = consolidated["content"]
            token_counter = ApproximateTokenCounter()
            tokens = token_counter.count_tokens(content)

            if tokens > max_tokens:
                content = self._truncate_content(
                    content, tokens, max_tokens, token_counter
                )

            return [
                {
                    "memory_id": "consolidated",
                    "content": content,
                    "tags": [],
                    "session_title": None,
                }
            ]

        memories = await self.get_memories_for_injection(
            top_n=self._config.top_n_for_injection,
            max_tokens=max_tokens,
        )
        return memories or None

    @staticmethod
    def _truncate_content(
        content: str,
        total_tokens: int,
        max_tokens: int,
        counter: ApproximateTokenCounter,
    ) -> str:
        ratio = max_tokens / total_tokens
        char_limit = max(int(len(content) * ratio), 100)
        return content[:char_limit] + "\n\n[truncated]"

    async def close(self) -> None:
        if self._store is not None:
            await self._store.close()
        if self._consolidated_store is not None:
            await self._consolidated_store.close()
        logger.info("Memory system shut down")
