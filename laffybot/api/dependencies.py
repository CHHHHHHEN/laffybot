"""Dependency helpers for the HTTP API."""

from __future__ import annotations

from fastapi import Request

from laffybot.agent.tools.registry import ToolRegistry
from laffybot.config import ApiConfig, ContextConfig
from laffybot.session.manager import SessionManager
from laffybot.session.provider_store import ProviderStore, SQLiteProviderStore
from laffybot.session.store import SessionStore, SQLiteStore


def build_store(config: ApiConfig) -> SessionStore:
    return SQLiteStore(config.database_path)


def build_provider_store(config: ApiConfig) -> ProviderStore:
    return SQLiteProviderStore(config.database_path)


def build_session_manager(
    store: SessionStore,
    provider_store: ProviderStore,
    tool_registry: ToolRegistry,
    context_config: ContextConfig | None = None,
) -> SessionManager:
    return SessionManager(
        store=store,
        provider_store=provider_store,
        tool_registry=tool_registry,
        context_config=context_config,
    )


def get_api_config(request: Request) -> ApiConfig:
    return request.app.state.api_config  # type: ignore[no-any-return]


def get_store(request: Request) -> SessionStore:
    return request.app.state.store  # type: ignore[no-any-return]


def get_provider_store(request: Request) -> ProviderStore:
    return request.app.state.provider_store  # type: ignore[no-any-return]


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager  # type: ignore[no-any-return]


def get_tool_registry(request: Request) -> ToolRegistry:
    return request.app.state.tool_registry  # type: ignore[no-any-return]
