"""Memory system exceptions."""

from __future__ import annotations


class ConfigError(Exception):
    """Raised when memory system configuration is invalid or incomplete."""


class MemoryNotFoundError(Exception):
    """Raised when a memory record does not exist."""

    def __init__(self, memory_id: str) -> None:
        self.memory_id = memory_id
        super().__init__(f"Memory {memory_id} not found")
