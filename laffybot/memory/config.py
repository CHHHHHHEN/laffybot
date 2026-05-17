"""Memory system configuration model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryConfig(BaseModel):
    """Memory system configuration.

    Controls memory extraction, storage, and injection behavior.
    Instantiated independently and passed via DI — not embedded in ApiConfig.
    """

    enabled: bool = Field(
        default=False,
        description="Master switch for the memory system. Runtime extraction is enabled when an extract model is configured (via UI or config.yaml).",
    )
    extract_model: str | None = Field(
        default=None,
        description="Default model for memory extraction. Can be overridden via UI. Extraction silently skipped when not configured.",
    )
    max_session_summaries: int = Field(
        default=50,
        ge=1,
        description="Maximum number of session summary files to retain.",
    )
    max_unused_days: int = Field(
        default=30,
        ge=1,
        description="Days after which an unused memory is eligible for eviction.",
    )
    top_n_for_injection: int = Field(
        default=5,
        ge=1,
        description="Number of top memories to inject into context.",
    )
    max_memory_tokens: int = Field(
        default=1000,
        ge=1,
        description="Token budget reserved for memory content in the prompt.",
    )
    root_dir: str = Field(
        default="memory_data",
        description="Root directory for memory storage. Relative paths are resolved against the working directory.",
    )
    consolidation_trigger_count: int = Field(
        default=10,
        ge=1,
        description="Number of new raw memories that trigger consolidation.",
    )
    consolidation_model: str | None = Field(
        default=None,
        description="Placeholder: consolidation model name. Runtime value is read from AppSettingStore (consolidation_model).",
    )
    max_source_memories: int = Field(
        default=50,
        ge=1,
        description="Maximum raw memories to include in a single consolidation pass.",
    )
