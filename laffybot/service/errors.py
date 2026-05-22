"""Domain errors for session management — owned by the service layer.

SessionNotFoundError and SessionStateError are defined in
laffybot.db.errors (infrastructure) so db code doesn't depend on
the service layer.  This module re-imports them with SessionError
inheritance added so existing isinstance checks still work.
"""

from __future__ import annotations

from laffybot.db.errors import (
    SessionNotFoundError as _DbSessionNotFoundError,
)
from laffybot.db.errors import (
    SessionStateError as _DbSessionStateError,
)


class SessionError(Exception):
    def __init__(self, session_id: str, message: str | None = None):
        self.session_id = session_id
        super().__init__(message or session_id)


class SessionNotFoundError(_DbSessionNotFoundError, SessionError):
    """Re-export from db layer with SessionError inheritance."""


class SessionStateError(_DbSessionStateError, SessionError):
    """Re-export from db layer with SessionError inheritance."""


class SessionBusyError(SessionError):
    def __init__(self, session_id: str, request_id: str | None = None):
        self.request_id = request_id
        suffix = f" (request_id={request_id})" if request_id else ""
        super().__init__(session_id, f"Session {session_id} is busy{suffix}")


class SessionNotBusyError(SessionError):
    def __init__(self, session_id: str):
        super().__init__(session_id, f"Session {session_id} is not busy")


class SessionAlreadyArchivedError(SessionError):
    def __init__(self, session_id: str):
        super().__init__(session_id, f"Session {session_id} is already archived")


class SessionNotArchivedError(SessionError):
    def __init__(self, session_id: str):
        super().__init__(session_id, f"Session {session_id} is not archived")
