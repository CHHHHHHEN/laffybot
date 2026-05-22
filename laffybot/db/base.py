"""Shared abstract base for all Store classes."""

from abc import ABC, abstractmethod


class BaseStore(ABC):
    @abstractmethod
    async def close(self) -> None: ...
