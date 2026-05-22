"""Consolidation agent — merges raw memories into a single consolidated memory."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from laffybot_agent_runtime.providers.types import ErrorLLMResponse
from loguru import logger

from laffybot.memory.prompts import CONSOLIDATE_MEMORY_PROMPT

if TYPE_CHECKING:
    from laffybot_agent_runtime.providers.base import BaseProvider

    from laffybot.db.consolidated_store import ConsolidatedMemoryStore
    from laffybot.db.memory_store import MemoryStore


class MemoryConsolidator:
    """Merge raw memories into a single consolidated memory via LLM.

    Uses a class-level lock to prevent concurrent consolidation triggers.
    """

    _lock = asyncio.Lock()

    def __init__(
        self,
        provider: BaseProvider,
        model: str,
        memory_store: MemoryStore,
        consolidated_store: ConsolidatedMemoryStore,
        trigger_count: int = 10,
        max_source_memories: int = 50,
    ) -> None:
        self.provider = provider
        self.model = model
        self.memory_store = memory_store
        self.consolidated_store = consolidated_store
        self.trigger_count = trigger_count
        self.max_source_memories = max_source_memories

    async def try_consolidate(self) -> bool:
        """Check if consolidation is needed and perform it.

        Returns True if consolidation was performed, False if skipped.
        Thread-safe via class-level asyncio.Lock.
        """
        if not self._lock.locked():
            async with self._lock:
                return await self._do_consolidate()
        logger.debug("Consolidation skipped: already in progress")
        return False

    async def _do_consolidate(self) -> bool:
        """Core consolidation logic — called under lock."""
        source_ids = await self.consolidated_store.get_source_ids()
        unconsolidated = await self.memory_store.get_unconsolidated_memories(
            exclude_ids=source_ids,
            limit=self.max_source_memories,
        )
        if len(unconsolidated) < self.trigger_count:
            logger.debug(
                "Consolidation skipped: unconsolidated={} < trigger_count={}",
                len(unconsolidated),
                self.trigger_count,
            )
            return False

        existing_record = await self.consolidated_store.get()
        existing_content = existing_record["content"] if existing_record else ""

        raw_memories_text = "\n\n".join(
            f"{i + 1}. {m['content']}" for i, m in enumerate(unconsolidated)
        )

        prompt = CONSOLIDATE_MEMORY_PROMPT.format(
            existing_memory=existing_content or "(no existing consolidated memory)",
            raw_memories=raw_memories_text,
        )

        try:
            response = await self.provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3,
                max_tokens=2000,
            )

            if isinstance(response, ErrorLLMResponse):
                logger.warning(
                    "Consolidation LLM call failed: error_kind={}",
                    response.error_kind,
                )
                return False

            if not response.content:
                logger.debug("Consolidation returned empty content — No-Op")
                return False

            new_content = response.content.strip()
            if not new_content:
                logger.debug("Consolidation returned empty content — No-Op")
                return False

        except Exception as e:
            logger.warning("Consolidation LLM call failed: error={}", str(e))
            return False

        new_source_ids = [m["memory_id"] for m in unconsolidated]
        all_source_ids = list(dict.fromkeys(source_ids + new_source_ids))

        try:
            await self.consolidated_store.upsert(
                content=new_content,
                source_memory_ids=all_source_ids,
            )
        except Exception as e:
            logger.error("Consolidation write failed: error={}", str(e))
            return False

        logger.info(
            "Consolidation completed: {} raw memories merged",
            len(new_source_ids),
        )
        return True
