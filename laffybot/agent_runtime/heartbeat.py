"""Heartbeat mechanism for keeping SSE connections alive."""

from __future__ import annotations

import asyncio
import os

from laffybot.agent_runtime.events import event_ping

# Default heartbeat interval (15 seconds)
_DEFAULT_HEARTBEAT_INTERVAL_S = 15
_MIN_HEARTBEAT_INTERVAL_S = 5


def _heartbeat_interval_s() -> int:
    """Get heartbeat interval from environment or default."""
    raw = os.environ.get("LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S")
    if raw is None:
        return _DEFAULT_HEARTBEAT_INTERVAL_S
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_HEARTBEAT_INTERVAL_S
    return max(_MIN_HEARTBEAT_INTERVAL_S, value)


class HeartbeatManager:
    """Manages heartbeat (ping) events for idle SSE connections.

    The heartbeat mechanism sends `ping` events when the connection has been
    idle for too long, preventing intermediate proxies (nginx, load balancers)
    from closing the connection due to timeout.

    Usage:
        heartbeat = HeartbeatManager()
        task = asyncio.create_task(heartbeat.run())

        # When sending an event:
        heartbeat.reset()

        # On stream end:
        heartbeat.stop()
        await task
    """

    def __init__(self, interval_s: float | None = None):
        """Initialize heartbeat manager.

        Args:
            interval_s: Heartbeat interval in seconds. If None, uses
                       LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S env var or default (15s).
        """
        self.interval_s = _heartbeat_interval_s() if interval_s is None else interval_s
        self._reset_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._reset_event.set()  # Start with reset to begin timer

    def reset(self) -> None:
        """Reset the idle timer.

        Call this after sending any event to prevent heartbeat while active.
        """
        self._reset_event.set()

    def stop(self) -> None:
        """Stop the heartbeat manager.

        Call this when the stream ends to cancel the background task.
        """
        self._stop_event.set()

    async def wait_for_ping(self) -> str | None:
        """Wait for idle timeout and return ping event data if needed.

        Returns:
            Ping event JSON string if idle timeout expired, None if reset.
        """
        try:
            await asyncio.wait_for(
                self._reset_event.wait(),
                timeout=self.interval_s,
            )
            # Reset was called
            self._reset_event.clear()
            return None
        except asyncio.TimeoutError:
            # Idle timeout expired - return ping event
            return event_ping().to_sse()
