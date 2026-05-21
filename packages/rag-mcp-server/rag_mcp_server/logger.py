from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_SERVER_LOGGER_NAME = "rag_mcp_server"


def setup_logging(
    level: str | int = "INFO",
    log_file: str | None = None,
    log_format: str | None = None,
) -> logging.Logger:
    fmt = log_format or _LOG_FORMAT

    root = logging.getLogger()
    root.setLevel(_resolve_level(level))

    for h in root.handlers[:]:
        root.removeHandler(h)

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(logging.Formatter(fmt))
    root.addHandler(stderr)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt))
        root.addHandler(fh)

    logger = logging.getLogger(_SERVER_LOGGER_NAME)
    return logger


def get_logger(name: str = _SERVER_LOGGER_NAME) -> logging.Logger:
    return logging.getLogger(name)


def _resolve_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    valid: set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level.upper() in valid:
        return getattr(logging, level.upper())  # type: ignore[no-any-return]
    return logging.INFO
