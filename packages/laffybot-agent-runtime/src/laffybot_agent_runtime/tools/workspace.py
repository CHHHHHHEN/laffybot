"""Per-request workspace context for tool path resolution.

Usage:
    from laffybot_agent_runtime.tools.workspace import initialize, require

    # At request entry (SessionManager.send_message):
    initialize(session.workspace_path)

    # Inside tool execution:
    ws = require()
    # ws is the absolute path string for the current session's workspace
"""

from __future__ import annotations

import contextvars

from loguru import logger

_current_workspace: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_workspace"
)


def initialize(workspace_path: str) -> None:
    """Set the workspace for the current asyncio task.

    Must be called before any tool execution in the task.
    Every subsequent tool execution in this task will resolve
    relative paths against this workspace.
    """
    logger.debug("Workspace context initialized: path={}", workspace_path)
    _current_workspace.set(workspace_path)


def require() -> str:
    """Return the current workspace path for this request.

    Raises:
        LookupError: If initialize() was not called before tool execution.
    """
    try:
        path = _current_workspace.get()
        logger.debug("Workspace resolved from context: {}", path)
        return path
    except LookupError:
        logger.error(
            "Workspace context not initialized — call initialize() before tool execution"
        )
        raise
