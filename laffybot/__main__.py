"""Entry point for running the Laffybot API server."""

from __future__ import annotations

import sys

import uvicorn
from loguru import logger

from laffybot.api.app import app
from laffybot.config import ApiConfig
from laffybot.crypto import validate_encryption_key


def main() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level:>8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    try:
        validate_encryption_key()
    except Exception as exc:
        logger.error("Startup failed: {}", exc)
        sys.exit(1)

    config = ApiConfig()
    logger.info("Starting server on {}:{}", config.host, config.port)
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()
