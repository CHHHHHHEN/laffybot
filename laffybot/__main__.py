"""Entry point for running the Laffybot API server."""

from __future__ import annotations

import argparse
import sys

import uvicorn
from loguru import logger

from laffybot.api.app import app
from laffybot.config import ApiConfig
from laffybot.crypto import validate_encryption_key
from laffybot.logging import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Laffybot API server")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to configuration file (default: config.json)",
    )
    args = parser.parse_args()

    # Load configuration first
    config = ApiConfig.from_json(args.config)

    # Configure logging with the specified log level
    configure_logging(config.log_level)

    try:
        validate_encryption_key()
    except Exception as exc:
        logger.error("Startup failed: {}", exc)
        sys.exit(1)

    logger.info("Starting server on {}:{}", config.host, config.port)
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        timeout_graceful_shutdown=5,
        log_config=None,  # Disable uvicorn's default logging config
        access_log=False,  # Disable uvicorn's access log
    )


if __name__ == "__main__":
    main()
