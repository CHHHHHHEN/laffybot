from __future__ import annotations

import asyncio
import uuid

from laffybot.service.lock_port import LockAcquisitionError, LockMismatchError


class LocalSessionLockPort:
    _locks: dict[str, asyncio.Lock] = {}
    _keys: dict[str, str] = {}

    async def try_lock(self, session_id: str, timeout: float = 30.0) -> str:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock

        try:
            acquired = await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise LockAcquisitionError(session_id, f"Lock timeout after {timeout}s")

        if not acquired:
            raise LockAcquisitionError(session_id)

        lock_key = uuid.uuid4().hex
        self._keys[session_id] = lock_key
        return lock_key

    async def unlock(self, session_id: str, lock_key: str) -> None:
        stored_key = self._keys.get(session_id)
        if stored_key is None or stored_key != lock_key:
            raise LockMismatchError(session_id)

        lock = self._locks.get(session_id)
        if lock is not None and lock.locked():
            lock.release()
            self._keys.pop(session_id, None)

    async def force_unlock(self, session_id: str) -> None:
        lock = self._locks.get(session_id)
        if lock is not None and lock.locked():
            lock.release()
        self._keys.pop(session_id, None)
        self._locks.pop(session_id, None)
