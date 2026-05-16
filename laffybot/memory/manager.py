"""Lifecycle container for the memory system."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from laffybot.memory.config import MemoryConfig
from laffybot.memory.storage import MemoryStorage


class MemoryManager:
    """Owns memory lifecycle: initialisation and resource management.

    Drives startup based on MemoryConfig, coordinates initialisation
    of sub-components. Exposes a read-only storage reference and config.
    Does *not* contain extraction, selection or injection logic.
    """

    def __init__(self, config: MemoryConfig) -> None:
        self._config = config
        resolved_root = Path(config.root_dir).resolve()
        self._storage = MemoryStorage(resolved_root)

    @property
    def config(self) -> MemoryConfig:
        return self._config

    @property
    def storage(self) -> MemoryStorage:
        return self._storage

    async def initialize(self) -> None:
        """Create memory directories on disk.

        Raises OSError if the directories cannot be created.
        """
        try:
            self._storage.ensure_directories()
        except OSError:
            logger.exception("Failed to create memory directories")
            raise

        logger.info(
            "Memory system initialized: root={}, enabled={}",
            self._storage.root_dir,
            self._config.enabled,
        )

    async def close(self) -> None:
        """Release resources held by the memory system."""
        logger.info("Memory system shut down")
