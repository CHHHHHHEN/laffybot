"""Event bus for SSE-based real-time notifications — injectable, no global singleton."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from loguru import logger

from laffybot.eventbus.types import GlobalEvent


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[GlobalEvent | None]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncGenerator[GlobalEvent, None]:
        """Subscribe to all events. Returns an async generator.

        Usage:
            async for event in bus.subscribe():
                ...
        """
        queue: asyncio.Queue[GlobalEvent | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers.append(queue)
        logger.debug("EventBus subscriber added, total={}", len(self._subscribers))

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            async with self._lock:
                try:
                    self._subscribers.remove(queue)
                except ValueError:
                    pass
            logger.debug(
                "EventBus subscriber removed, remaining={}", len(self._subscribers)
            )

    async def add_subscriber(self, queue: asyncio.Queue[GlobalEvent | None]) -> None:
        async with self._lock:
            self._subscribers.append(queue)

    async def remove_subscriber(self, queue: asyncio.Queue[GlobalEvent | None]) -> None:
        async with self._lock:
            try:
                self._subscribers.remove(queue)
            except ValueError:
                pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def publish(self, event_type: str, data: dict[str, object]) -> None:
        if not self._subscribers:
            logger.debug("EventBus publish: no subscribers for {}", event_type)
            return

        event = GlobalEvent(type=event_type, data=data)
        async with self._lock:
            subscribers = self._subscribers.copy()

        logger.debug(
            "EventBus publishing: type={}, subscribers={}", event_type, len(subscribers)
        )

        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("EventBus subscriber queue full, dropping event")

    async def shutdown(self) -> None:
        async with self._lock:
            subscribers = self._subscribers.copy()

        for queue in subscribers:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

        logger.info("EventBus shutdown signaled to {} subscribers", len(subscribers))
