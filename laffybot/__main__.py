"""Entry point for running the Laffybot API server."""

from __future__ import annotations

import uvicorn

from laffybot.api.app import app
from laffybot.config import ApiConfig


def main() -> None:
    config = ApiConfig()
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
    )


if __name__ == "__main__":
    main()
