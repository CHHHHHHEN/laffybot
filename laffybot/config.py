"""Application configuration."""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ContextConfig(BaseModel):
    """Context building configuration.

    Controls how messages are assembled and context window limits.
    """

    max_tokens: int | None = Field(
        default=None,
        description="Maximum total tokens for context (system + history + current). None means no limit.",
    )
    max_messages: int | None = Field(
        default=None,
        description="Maximum number of historical messages to include. None means no limit.",
    )

    system_prompt: str = Field(
        default="You are a helpful assistant.",
        description="Default system prompt. UI-editable global setting.",
    )
    system_prompt_template: str | None = Field(
        default="""{% if memories %}
The following are relevant memories from past conversations:

{% for m in memories %}
- {{ m.content }}
{% endfor %}

{% endif %}
You are a helpful assistant.
{% if skills_block %}
{{ skills_block }}
{% endif %}""",
        description="Jinja2 template for system prompt. When set (non-None), used as the complete prompt. "
        "Variables: session_id, model, created_at, memories, skills_block, custom vars. "
        "When None, falls back to system_prompt.",
    )
    template_variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom variables for system prompt template.",
    )
    use_exact_token_count: bool = Field(
        default=True,
        description="Prefer exact token counts from LLM usage when available.",
    )

    enable_compression: bool = Field(
        default=True,
        description="Global switch for context compression. Default enabled.",
    )
    compress_threshold_ratio: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Token usage ratio threshold to trigger compression.",
    )
    compress_preserve_pairs: int = Field(
        default=3,
        ge=1,
        description="Number of recent user-assistant message pairs to preserve intact during compression.",
    )
    compress_preserve_recent_tokens: int | None = Field(
        default=None,
        description="Token budget for the recent preserved tail. None means dynamic from max_tokens.",
    )
    compress_reserved_tokens: int = Field(
        default=20000,
        ge=0,
        description="Reserved token buffer to prevent compression from triggering overflow.",
    )
    compress_max_summary_tokens: int = Field(
        default=512,
        ge=1,
        description="Token budget reserved for the summary message.",
    )
    compress_model: str | None = Field(
        default=None,
        description="Dedicated model for summary generation. None reuses the session model.",
    )
    compress_tool_output_max_chars: int = Field(
        default=2000,
        ge=0,
        description="Maximum characters for tool output before pruning. 0 disables pruning.",
    )
    compress_protected_tools: list[str] = Field(
        default=["skill"],
        description="Tool types whose outputs are protected from pruning.",
    )

    request_timeout_seconds: float = Field(
        default=600.0,
        ge=1.0,
        description="Maximum total time in seconds for a single request. 0 or negative disables timeout.",
    )


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
