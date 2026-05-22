"""Entry point for running the Laffybot API server."""

from __future__ import annotations

import argparse
import sys

import uvicorn
from loguru import logger

from laffybot.api.app import create_app
from laffybot.config import ApiConfig
from laffybot.crypto import validate_encryption_key
from laffybot.observability.logging import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Laffybot API server")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to configuration file (default: config.json)",
    )
    args = parser.parse_args()

    config = ApiConfig.from_json(args.config)

    configure_logging(config)

    try:
        validate_encryption_key()
    except Exception as exc:
        logger.error("Startup failed: {}", exc)
        sys.exit(1)

    app = create_app(api_config=config)

    logger.info("Starting server on {}:{}", config.host, config.port)
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        timeout_graceful_shutdown=5,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
