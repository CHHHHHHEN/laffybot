from __future__ import annotations

from laffybot.service.lock_port import SessionLockPort
from laffybot.service.models import SessionStatus


class SessionStateMachine:
    def __init__(self, lock_port: SessionLockPort) -> None:
        self._lock_port = lock_port

    async def transition_to_busy(self, session_id: str) -> tuple[SessionStatus, str]:
        lock_key = await self._lock_port.try_lock(session_id)
        return ("busy", lock_key)

    async def transition_to_idle(
        self, session_id: str, lock_key: str, error_message: str | None = None
    ) -> SessionStatus:
        await self._lock_port.unlock(session_id, lock_key)
        return "error" if error_message else "idle"

    async def force_to_idle(self, session_id: str) -> SessionStatus:
        await self._lock_port.force_unlock(session_id)
        return "idle"

    def cancel(self, session_id: str, reason: str | None = None) -> None:
        pass
