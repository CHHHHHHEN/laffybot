"""Protocol interfaces for session layer dependency inversion."""

from __future__ import annotations

from typing import Any, Protocol


class EventPublisher(Protocol):
    """Interface for publishing events to external subscribers.

    Session layer depends on this protocol instead of importing
    ``laffybot.api.event_bus`` directly, avoiding a layer violation.
    """

    async def publish(self, event_type: str, data: dict[str, Any]) -> None: ...
