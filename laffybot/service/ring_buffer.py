"""Per-session ring buffer for SSE event replay."""

from __future__ import annotations

from collections import deque

from laffybot.agent_runtime.events import SSEEvent


class SSERingBuffer:
    """Per-session ring buffer for SSE event replay.

    Stores the last ``capacity`` events per session_id so clients that
    reconnect with a ``Last-Event-ID`` header can retrieve missed events
    without hitting the database.
    """

    def __init__(self, capacity: int = 100) -> None:
        self._capacity = capacity
        # session_id → deque of (event_id, SSEEvent)
        self._buffers: dict[str, deque[tuple[str, SSEEvent]]] = {}

    def push(self, session_id: str, event_id: str, event: SSEEvent) -> None:
        """Record an event in the session's ring buffer."""
        if session_id not in self._buffers:
            self._buffers[session_id] = deque(maxlen=self._capacity)
        self._buffers[session_id].append((event_id, event))

    def get_missed_events(
        self,
        session_id: str,
        last_event_id: str,
    ) -> list[tuple[str, SSEEvent]]:
        """Return events after ``last_event_id`` from the ring buffer.

        Returns an empty list if the session has no buffer or the
        event ID is not found (caller should fall back to the store).
        """
        buf = self._buffers.get(session_id)
        if buf is None:
            return []
        # Find the last_event_id in the buffer
        for i, (eid, _) in enumerate(buf):
            if eid == last_event_id:
                return list(buf)[i + 1 :]
        # Not found — caller should fall back to Store
        return []

    def drop_session(self, session_id: str) -> None:
        """Release the buffer for a completed/cancelled session."""
        self._buffers.pop(session_id, None)

    @property
    def active_sessions(self) -> int:
        return len(self._buffers)


# Module-level singleton — shared across all SSE streams.
ring_buffer: SSERingBuffer = SSERingBuffer(capacity=100)
