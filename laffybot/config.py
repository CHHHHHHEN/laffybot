"""Application configuration."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field


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
    min_preserve_pairs: int = Field(
        default=3,
        ge=1,
        description="Minimum number of user-assistant message pairs to preserve when truncating.",
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
You are a helpful assistant.""",
        description="Jinja2 template for system prompt. When set (non-None), used as the complete prompt. "
        "Variables: session_id, model, created_at, memories, custom vars. "
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


class ApiConfig(BaseModel):
    """HTTP API configuration."""

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

    @classmethod
    def from_json(cls, path: str) -> ApiConfig:
        with open(path) as f:
            data = json.load(f)
        return cls(**data)
