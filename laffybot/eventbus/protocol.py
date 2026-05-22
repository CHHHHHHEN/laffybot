from __future__ import annotations

from typing import Any, Protocol


class EventPublisher(Protocol):
    async def publish(self, event_type: str, data: dict[str, Any]) -> None: ...
