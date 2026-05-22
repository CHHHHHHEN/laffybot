"""Session domain models — re-exported from db layer.

These types live in laffybot.db.models so infrastructure does not
depend on the service layer.  Service-layer code still imports them
from here for convenience.
"""

from __future__ import annotations

from laffybot.db.models import (
    MessageRole,
    SessionInfo,
    SessionMessage,
    SessionStatus,
    validate_role,
    validate_status,
)

__all__ = [
    "MessageRole",
    "SessionInfo",
    "SessionMessage",
    "SessionStatus",
    "validate_role",
    "validate_status",
]
