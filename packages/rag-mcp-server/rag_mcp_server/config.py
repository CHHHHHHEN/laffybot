from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel


class RerankConfig(BaseModel):  # type: ignore[misc]
    provider: str = "none"
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k: int = 5


class WatchConfig(BaseModel):  # type: ignore[misc]
    enabled: bool = True
    paths: list[str] = []
    debounce_ms: int = 1000


class RAGConfig(BaseModel):  # type: ignore[misc]
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str | None = None
    embedding_api_base: str | None = None
    vector_store_type: str = "chroma"
    vector_store_path: str = "./rag_vectors"
    collection_name: str = "laffybot_docs"
    chunk_size: int = 512
    chunk_overlap: int = 50
    default_top_k: int = 5
    dense_top_k: int = 20
    sparse_top_k: int = 20
    rrf_k: int = 60
    rerank: RerankConfig = RerankConfig()
    watch: WatchConfig = WatchConfig()
    sse_host: str = "0.0.0.0"
    sse_port: int = 8000
    document_paths: list[str] = ["./docs"]
    include_patterns: list[str] = ["**/*.md", "**/*.txt", "**/*.pdf"]
    exclude_patterns: list[str] = ["**/node_modules/**", "**/__pycache__/**"]
    allowed_extensions: list[str] = [
        ".md",
        ".txt",
        ".pdf",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".rst",
    ]
    log_level: str = "INFO"
    log_file: str | None = None


def load_config(path: str | Path) -> RAGConfig:
    path = Path(path)
    if not path.exists():
        return RAGConfig()

    with open(path, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    rerank_raw = raw.pop("rerank", {}) or {}
    watch_raw = raw.pop("watch", {}) or {}

    config = RAGConfig(**raw)

    if isinstance(rerank_raw, dict):
        for k, v in rerank_raw.items():
            if hasattr(config.rerank, k):
                setattr(config.rerank, k, v)

    if isinstance(watch_raw, dict):
        for k, v in watch_raw.items():
            if hasattr(config.watch, k):
                setattr(config.watch, k, v)

    # Environment variable overrides (take precedence over YAML)
    if os.environ.get("EMBEDDING_API_KEY"):
        config.embedding_api_key = os.environ["EMBEDDING_API_KEY"]

    return config
