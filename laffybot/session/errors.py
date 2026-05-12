"""Domain errors for session management."""

from __future__ import annotations


class SessionError(Exception):
    """Base class for session-related errors."""

    def __init__(self, session_id: str, message: str | None = None):
        self.session_id = session_id
        super().__init__(message or session_id)


class SessionNotFoundError(SessionError):
    """Raised when a session does not exist."""

    def __init__(self, session_id: str):
        super().__init__(session_id, f"Session {session_id} not found")


class SessionBusyError(SessionError):
    """Raised when a session is already busy."""

    def __init__(self, session_id: str, request_id: str | None = None):
        self.request_id = request_id
        suffix = f" (request_id={request_id})" if request_id else ""
        super().__init__(session_id, f"Session {session_id} is busy{suffix}")


class SessionInactiveError(SessionError):
    """Raised when a session is inactive."""

    def __init__(self, session_id: str):
        super().__init__(session_id, f"Session {session_id} is inactive")


class SessionNotBusyError(SessionError):
    """Raised when a busy-only operation is invoked on an idle session."""

    def __init__(self, session_id: str):
        super().__init__(session_id, f"Session {session_id} is not busy")


class SessionStateError(SessionError):
    """Raised when a state transition conflicts with the stored status."""

    def __init__(self, session_id: str, current_status: str):
        self.current_status = current_status
        super().__init__(
            session_id,
            f"Session {session_id} has unexpected status {current_status}",
        )
