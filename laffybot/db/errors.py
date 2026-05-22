"""Domain errors for session management — owned by the db/infrastructure layer.

Moved here from laffybot.service.errors so infrastructure does not
depend on the service layer.  The service layer re-exports these types.
"""

from __future__ import annotations


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session {session_id} not found")


class SessionStateError(Exception):
    def __init__(self, session_id: str, current_status: str) -> None:
        self.session_id = session_id
        self.current_status = current_status
        super().__init__(f"Session {session_id} has unexpected status {current_status}")
