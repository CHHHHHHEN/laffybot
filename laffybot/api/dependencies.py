"""Dependency helpers for the HTTP API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request

from laffybot.agent.tools.registry import ToolRegistry
from laffybot.config import ApiConfig, ContextConfig, ProviderConfig
from laffybot.providers.base import BaseProvider
from laffybot.providers.openai import OpenAIProvider
from laffybot.session.manager import SessionManager
from laffybot.session.store import SessionStore, SQLiteStore


def default_provider_factory() -> Callable[[str], BaseProvider]:
    """Build the default provider factory from process configuration."""

    def factory(_: str) -> BaseProvider:
        return OpenAIProvider(ProviderConfig())

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
