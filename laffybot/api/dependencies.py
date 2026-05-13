"""Dependency helpers for the HTTP API."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from fastapi import Request

from laffybot.agent.tools.registry import ToolRegistry
from laffybot.config import ApiConfig, ContextConfig, ProviderConfig
from laffybot.providers.base import BaseProvider
from laffybot.providers.openai import OpenAIProvider
from laffybot.session.manager import SessionManager
from laffybot.session.store import SessionStore, SQLiteStore


def _load_provider_config() -> ProviderConfig:
    """Load ProviderConfig from config.json or env vars."""
    config_path = Path("config.json")
    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
        api_key = data.get("api_key")
        base_url = data.get("base_url")
        if api_key and base_url:
            extra_headers = data.get("extra_headers") or {}
            extra_body = data.get("extra_body") or {}
            return ProviderConfig(
                api_key=api_key,
                base_url=base_url,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
    return ProviderConfig()  # type: ignore[call-arg]  # BaseSettings reads from env


def default_provider_factory() -> Callable[[str], BaseProvider]:
    """Build the default provider factory from process configuration."""
    config = _load_provider_config()

    def factory(_: str) -> BaseProvider:
        return OpenAIProvider(config)

    return factory


def build_store(config: ApiConfig) -> SessionStore:
    return SQLiteStore(config.database_path)


def build_session_manager(
    store: SessionStore,
    tool_registry: ToolRegistry,
    provider_factory: Callable[[str], BaseProvider],
    context_config: ContextConfig | None = None,
) -> SessionManager:
    return SessionManager(
        store=store,
        tool_registry=tool_registry,
        provider_factory=provider_factory,
        context_config=context_config,
    )


def get_api_config(request: Request) -> ApiConfig:
    return request.app.state.api_config


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager
