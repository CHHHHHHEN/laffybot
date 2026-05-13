"""Application configuration."""

from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ProviderConfig(BaseSettings):
    """LLM provider configuration."""

    api_key: str
    base_url: str
    extra_headers: dict[str, str] = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)


class ContextConfig(BaseModel):
    """Context building configuration.

    Controls how messages are assembled and context window limits.
    This is separate from ProviderConfig to avoid mixing concerns.
    """

    # Capacity limits
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

    # System prompt configuration
    system_prompt: str | None = Field(
        default=None,
        description="Default system prompt. Can be overridden by session.",
    )
    system_prompt_template: str | None = Field(
        default=None,
        description="Jinja2 template for system prompt. Variables: session_id, model, created_at, custom vars.",
    )
    template_variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom variables for system prompt template.",
    )

    # Token counting
    use_exact_token_count: bool = Field(
        default=True,
        description="Prefer exact token counts from LLM usage when available.",
    )


class ApiConfig(BaseSettings):
    """HTTP API configuration."""

    database_path: str = Field(
        default="laffybot.db",
        description="SQLite database path for session persistence.",
    )
    host: str = Field(default="0.0.0.0", description="HTTP bind host.")
    port: int = Field(default=8000, ge=1, le=65535, description="HTTP bind port.")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed CORS origins.",
    )
    cors_allow_credentials: bool = Field(
        default=False,
        description="Allow credentialed CORS requests.",
    )
