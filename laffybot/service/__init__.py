"""后端服务层 — 会话编排、状态管理、上下文装配"""

from laffybot.service.errors import (
    SessionBusyError,
    SessionError,
    SessionNotBusyError,
    SessionNotFoundError,
    SessionStateError,
)
from laffybot.service.models import (
    MessageRole,
    SessionInfo,
    SessionMessage,
    SessionStatus,
)
from laffybot.service.protocols import (
    MemoryManager,
    ProviderFactory,
    SessionManager,
)
from laffybot.service.session_manager import DefaultSessionManager

__all__ = [
    "MessageRole",
    "SessionBusyError",
    "SessionError",
    "SessionInfo",
    "SessionMessage",
    "SessionNotBusyError",
    "SessionNotFoundError",
    "SessionStateError",
    "SessionStatus",
    "MemoryManager",
    "ProviderFactory",
    "SessionManager",
    "DefaultSessionManager",
]
