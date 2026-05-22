"""Centralized logging configuration for laffybot.

Provides console logging, rotating file logging, and integration with
the ErrorLogService for structured error capture.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from loguru import logger

from laffybot.config import ApiConfig
from laffybot.service.error_log import ErrorLogService

UVICORN_LOGGERS = [
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "uvicorn.asgi",
]

_LOGURU_CONSOLE_HANDLER_ID: int | None = None
_LOGURU_FILE_HANDLER_ID: int | None = None
_LOGURU_ERROR_FILE_HANDLER_ID: int | None = None


def _file_format_string() -> str:
    """Return the format string for file handlers.

    Uses str.format_map with the loguru record. Extra keys (session_id,
    request_id) are always populated via logger.configure(extra=...) so
    the format_map substitution never raises KeyError.
    """
    return (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:>8} | "
        "{name}:{function}:{line}"
        " [{extra[session_id]:<36}] [{extra[request_id]:<18}]"
        " - {message}\n{exception}"
    )


def configure_logging(config: ApiConfig) -> None:
    """Configure loguru with console output and rotating file handlers.

    Call once at startup from __main__.py.  A third handler that forwards
    ERROR-level records to the ErrorLogService is added later by the
    composition root (app.py) once the ErrorLogService is instantiated.

    Default values for ``session_id`` and ``request_id`` are set so that
    the file format string does not KeyError when those keys are absent.
    """
    logger.remove()

    # Register default extra keys so the file format string never crashes
    # even when a log call does not use logger.bind(session_id=...).
    logger.configure(extra={"session_id": "", "request_id": ""})

    # ── Console handler (coloured, human-readable) ──────────────────────
    global _LOGURU_CONSOLE_HANDLER_ID
    _LOGURU_CONSOLE_HANDLER_ID = logger.add(
        sink=lambda msg: print(msg, end=""),
        level=config.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "| <level>{level:>8}</level> "
            "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
            " - <level>{message}</level>"
        ),
        colorize=True,
    )

    # ── Rotating file handler (all levels) ──────────────────────────────
    log_dir = _ensure_log_dir(config.log_dir)
    all_log_path = str(log_dir / "laffybot.log")

    global _LOGURU_FILE_HANDLER_ID
    _LOGURU_FILE_HANDLER_ID = logger.add(
        sink=all_log_path,
        level=config.log_level,
        format=_file_format_string(),
        rotation=config.log_max_bytes,
        retention=config.log_backup_count,
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    # ── Error-only rotating file handler ────────────────────────────────
    error_log_path = str(log_dir / "laffybot-error.log")

    global _LOGURU_ERROR_FILE_HANDLER_ID
    _LOGURU_ERROR_FILE_HANDLER_ID = logger.add(
        sink=error_log_path,
        level="ERROR",
        format=_file_format_string(),
        rotation=config.log_max_bytes,
        retention=config.log_backup_count,
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    # ── Suppress uvicorn access logs (we use loguru for everything) ─────
    for logger_name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = False
        uvicorn_logger.setLevel(logging.CRITICAL + 1)


def add_error_service_sink() -> None:
    """Add a loguru sink that forwards ERROR+ records to the ErrorLogService.

    Called from the composition root (app.py) after ErrorLogService is created.
    """
    logger.add(
        sink=_error_sink,
        level="ERROR",
        format="{message}",
    )


def _error_sink(message: Any) -> None:
    """Loguru sink callback — forwards ERROR records to ErrorLogService."""
    try:
        svc = _get_error_log_safe()
        if svc is None:
            return
        record = message.record
        svc.record(
            level=record["level"].name,
            source=f"{record['name']}:{record['function']}:{record['line']}",
            message=record["message"],
            session_id=record["extra"].get("session_id") or None,
            request_id=record["extra"].get("request_id") or None,
        )
    except Exception:
        pass  # sink must never throw


def _get_error_log_safe() -> ErrorLogService | None:
    """Get ErrorLogService without raising if not initialized."""
    try:
        from laffybot.service.error_log import get_error_log

        return get_error_log()
    except (AssertionError, ImportError):
        return None


def _ensure_log_dir(log_dir: str) -> Path:
    """Create log directory if it doesn't exist, return absolute Path."""
    p = Path(log_dir)
    if not p.is_absolute():
        p = Path.cwd() / p
    os.makedirs(str(p), exist_ok=True)
    return p
