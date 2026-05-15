"""Global event bus for SSE-based real-time notifications."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass(slots=True)
class GlobalEvent:
    """Event payload for global event bus."""

    type: str
    data: dict[str, Any]

    def to_sse(self) -> str:
        """Serialize event to SSE format.

        Returns:
            SSE-formatted string: "event: <type>\\ndata: <json>\\n\\n"
        """
        data_str = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.type}\ndata: {data_str}\n\n"


class EventBus:
    """Global event bus for broadcasting events to all connected clients.

    This implements a simple pub/sub pattern where:
    - Publishers call publish() to broadcast events
    - Subscribers are async generators that yield events
    - Events are broadcast to all active subscribers

    Usage:
        bus = EventBus()

        # In publisher (e.g., SessionManager):
        bus.publish("title_update", {"session_id": "xxx", "title": "New Title"})

        # In subscriber (e.g., SSE endpoint):
        async for event in bus.subscribe():
            yield event.to_sse()
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[GlobalEvent | None]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncGenerator[GlobalEvent, None]:
        """Subscribe to all events.

        Yields:
            GlobalEvent: Events as they are published.

        Note:
            The subscription is automatically cleaned up when the generator
            is closed or goes out of scope.
        """
        queue: asyncio.Queue[GlobalEvent | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers.append(queue)
        logger.debug("EventBus subscriber added, total={}", len(self._subscribers))

        try:
            while True:
                event = await queue.get()
                if event is None:
                    # Shutdown signal
                    break
                yield event
        finally:
            async with self._lock:
                try:
                    self._subscribers.remove(queue)
                except ValueError:
                    pass  # Already removed
            logger.debug(
                "EventBus subscriber removed, remaining={}", len(self._subscribers)
            )

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers.

        Args:
            event_type: Event type string (e.g., "title_update")
            data: Event payload as dictionary
        """
        if not self._subscribers:
            logger.debug("EventBus publish: no subscribers for {}", event_type)
            return

        event = GlobalEvent(type=event_type, data=data)
        async with self._lock:
            subscribers = self._subscribers.copy()

        logger.debug(
            "EventBus publishing: type={}, subscribers={}",
            event_type,
            len(subscribers),
        )

        # Broadcast to all subscribers
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("EventBus subscriber queue full, dropping event")

    async def shutdown(self) -> None:
        """Signal all subscribers to stop.

        This is typically called during application shutdown.
        """
        async with self._lock:
            subscribers = self._subscribers.copy()

        for queue in subscribers:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass  # Queue full, subscriber will handle it

        logger.info("EventBus shutdown signaled to {} subscribers", len(subscribers))


# Global singleton instance
_global_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global EventBus singleton.

    Returns:
        EventBus: The global event bus instance.
    """
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus
