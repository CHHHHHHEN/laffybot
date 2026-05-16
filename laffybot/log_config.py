"""Centralized logging configuration for laffybot.

This module provides a unified logging setup using loguru, with support for:
- Configurable log levels
- Colored stderr output with timestamps and call site information
- Uvicorn log interception to prevent duplicate output
"""

from __future__ import annotations

import logging

from loguru import logger

# Uvicorn loggers that need to be intercepted
UVICORN_LOGGERS = [
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "uvicorn.asgi",
]


def configure_logging(log_level: str = "DEBUG") -> None:
    """Configure unified logging for the application.

    This function:
    1. Removes all existing loguru handlers
    2. Adds a unified stderr sink with colorized output
    3. Intercepts uvicorn loggers to prevent duplicate output

    Args:
        log_level: Log level for the stderr sink (DEBUG, INFO, WARNING, ERROR).
                   Defaults to "DEBUG".
    """
    # Remove default loguru handler
    logger.remove()

    # Add unified stderr sink
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level:>8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # Intercept uvicorn loggers: remove handlers and disable propagation
    for logger_name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = False
        uvicorn_logger.setLevel(logging.CRITICAL + 1)  # Effectively disable
