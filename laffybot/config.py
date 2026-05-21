"""Application configuration."""

from __future__ import annotations

import json
import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    """HTTP API configuration."""

    model_config = SettingsConfigDict(env_prefix="LAFFYBOT_")

    database_path: str = Field(
        default="laffybot.db",
        description="SQLite database path for session persistence.",
    )
    host: str = Field(default="0.0.0.0", description="HTTP bind host.")
    port: int = Field(default=8000, ge=1, le=65535, description="HTTP bind port.")
    log_level: str = Field(
        default="DEBUG",
        description="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed CORS origins.",
    )
    cors_allow_credentials: bool = Field(
        default=False,
        description="Allow credentialed CORS requests.",
    )
    max_active_sessions: int = Field(
        default=3,
        ge=1,
        description="Maximum number of active (non-archived) sessions before auto-archiving the oldest.",
    )

    @classmethod
    def from_json(cls, path: str) -> ApiConfig:
        try:
            with open(path) as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Error: Config file not found: {path}")
            sys.exit(1)
        except json.JSONDecodeError as exc:
            print(f"Error: Config file is not valid JSON: {path}")
            print(f"  {exc.msg} (line {exc.lineno}, column {exc.colno})")
            sys.exit(1)
        return cls(**data)
