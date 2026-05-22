from __future__ import annotations

from typing import Protocol


class LockAcquisitionError(Exception):
    def __init__(
        self, session_id: str, message: str = "Failed to acquire lock"
    ) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id}: {message}")


class LockMismatchError(Exception):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id}: lock key mismatch")


class SessionLockPort(Protocol):
    async def try_lock(self, session_id: str, timeout: float = 30.0) -> str: ...

    async def unlock(self, session_id: str, lock_key: str) -> None: ...

    async def force_unlock(self, session_id: str) -> None: ...
