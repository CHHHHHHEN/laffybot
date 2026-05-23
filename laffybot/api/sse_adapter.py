"""SSE stream adapter — encapsulates runtime SSEEvent formatting.

This module is the only place in the API layer that imports runtime event types.
Implements the ring buffer for Last-Event-ID reconnection (ARCHITECTURE.md).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from laffybot.agent_runtime.events import SSEEvent, event_ping
from laffybot.agent_runtime.heartbeat import HeartbeatManager
from laffybot.service.ring_buffer import ring_buffer


def format_sse_frame(event: SSEEvent, event_id: str) -> str:
    return f"id: {event_id}\n{event.to_sse()}"


def _parse_event_id(raw: str) -> int:
    """Extract numeric index from an event ID like ``evt_42``."""
    try:
        return int(raw.removeprefix("evt_"))
    except (ValueError, AttributeError):
        return 0


async def stream_session_events(
    event_stream: AsyncGenerator[SSEEvent, None],
    session_id: str = "",
    last_event_id: str | None = None,
    heartbeat_interval_s: int = 30,
) -> AsyncGenerator[str, None]:
    """Stream SSE events with ring-buffer replay support.

    When ``last_event_id`` is provided, attempts to replay missed events
    from the in-memory ring buffer first, falling back to the live stream.
    """
    # ── Reconnection: replay missed events from ring buffer ────────────
    if last_event_id is not None and session_id:
        missed = ring_buffer.get_missed_events(session_id, last_event_id)
        if missed:
            for eid, event in missed:
                yield format_sse_frame(event, eid)
            # Resume live stream after last replayed event
            last_idx = _parse_event_id(missed[-1][0])
            event_index = last_idx
            # Drain the original event_stream (we've already sent the missed events)
            # But the caller's manager is already running — skip old events
            # by continuing from the current index
            # Actually, we need to re-think this: the ring buffer stores events
            # from the CURRENT stream, so missed events ARE in the buffer.
            # We replayed them above; now continue live.
        else:
            # No ring buffer data — fall through to live stream
            event_index = _parse_event_id(last_event_id) if last_event_id else 0
    else:
        event_index = 0

    # ── Live stream ────────────────────────────────────────────────────
    hb = HeartbeatManager(interval_s=heartbeat_interval_s)
    hb.reset()

    try:
        ait = event_stream.__aiter__()
        while True:
            try:
                event = await asyncio.wait_for(ait.__anext__(), timeout=hb.interval_s)
                event_index += 1
                eid = f"evt_{event_index}"
                # Record to ring buffer for future reconnection
                if session_id:
                    ring_buffer.push(session_id, eid, event)
                yield format_sse_frame(event, eid)
                hb.reset()
            except asyncio.TimeoutError:
                event_index += 1
                yield f"id: evt_{event_index}\n{await hb.wait_for_ping() or event_ping().to_sse()}"
    except StopAsyncIteration:
        pass
    finally:
        hb.stop()
        if session_id:
            ring_buffer.drop_session(session_id)


async def stream_global_events(
    queue: asyncio.Queue[Any],
    heartbeat_interval_s: int = 30,
) -> AsyncGenerator[str, None]:
    """Global event bus SSE stream (no ring buffer — events are transient)."""
    event_index = 0
    hb = HeartbeatManager(interval_s=heartbeat_interval_s)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=hb.interval_s)
                if event is None:
                    break
                event_index += 1
                yield f"id: evt_{event_index}\n{event.to_sse()}"
            except asyncio.TimeoutError:
                event_index += 1
                yield f"id: evt_{event_index}\n{await hb.wait_for_ping() or event_ping().to_sse()}"
    except Exception as exc:
        logger.info("Global events SSE connection closed: {}", type(exc).__name__)
        logger.debug("Global events SSE connection error details: {}", exc)
    finally:
        hb.stop()
