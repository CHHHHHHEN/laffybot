"""Dependency helpers for the HTTP API."""

from __future__ import annotations

from fastapi import Request

from laffybot.agent.tools.registry import ToolRegistry
from laffybot.api.event_bus import get_event_bus
from laffybot.config import ApiConfig, ContextConfig
from laffybot.memory import MemoryConfig, MemoryManager, MemoryStore, SQLiteMemoryStore
from laffybot.providers.base import BaseProvider
from laffybot.providers.config import ProviderConfig
from laffybot.providers.factory import ProviderFactory
from laffybot.providers.openai import OpenAIProvider
from laffybot.session.app_setting_store import AppSettingStore, SQLiteAppSettingStore
from laffybot.session.manager import SessionManager
from laffybot.session.provider_store import ProviderStore, SQLiteProviderStore
from laffybot.session.store import SessionStore, SQLiteStore


class DefaultProviderFactory:
    """Concrete provider factory wired to OpenAIProvider.

    Lives in the API layer to keep provider instantiation details out of
    the session/business-logic layer.
    """

    async def create_provider(self, config: ProviderConfig) -> BaseProvider:
        return OpenAIProvider(config)


def build_store(config: ApiConfig) -> SessionStore:
    return SQLiteStore(config.database_path)


def build_provider_store(config: ApiConfig) -> ProviderStore:
    return SQLiteProviderStore(config.database_path)


def build_app_setting_store(config: ApiConfig) -> AppSettingStore:
    return SQLiteAppSettingStore(config.database_path)


def build_memory_store(config: ApiConfig) -> MemoryStore:
    return SQLiteMemoryStore(config.database_path)


def build_session_manager(
    store: SessionStore,
    provider_store: ProviderStore,
    app_setting_store: AppSettingStore,
    tool_registry: ToolRegistry,
    context_config: ContextConfig | None = None,
    memory_manager: MemoryManager | None = None,
    max_active_sessions: int = 3,
    tool_timeout_s: int = 120,
    session_timeout_s: int = 600,
    watchdog_interval_s: int = 60,
    provider_factory: ProviderFactory | None = None,
) -> SessionManager:
    return SessionManager(
        store=store,
        provider_store=provider_store,
        app_setting_store=app_setting_store,
        tool_registry=tool_registry,
        provider_factory=provider_factory or DefaultProviderFactory(),
        context_config=context_config,
        memory_manager=memory_manager,
        max_active_sessions=max_active_sessions,
        tool_timeout_s=tool_timeout_s,
        session_timeout_s=session_timeout_s,
        watchdog_interval_s=watchdog_interval_s,
        event_publisher=get_event_bus(),
    )


def get_api_config(request: Request) -> ApiConfig:
    return request.app.state.api_config  # type: ignore[no-any-return]


def get_store(request: Request) -> SessionStore:
    return request.app.state.store  # type: ignore[no-any-return]


def get_provider_store(request: Request) -> ProviderStore:
    return request.app.state.provider_store  # type: ignore[no-any-return]


def get_app_setting_store(request: Request) -> AppSettingStore:
    return request.app.state.app_setting_store  # type: ignore[no-any-return]


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager  # type: ignore[no-any-return]


def build_memory_manager(
    config: MemoryConfig | None = None,
    store: MemoryStore | None = None,
    db_path: str | None = None,
) -> MemoryManager:
    return MemoryManager(config or MemoryConfig(), store=store, db_path=db_path)


def get_memory_manager(request: Request) -> MemoryManager | None:
    return request.app.state.memory_manager  # type: ignore[no-any-return]


def get_memory_store(request: Request) -> MemoryStore | None:
    return request.app.state.memory_store  # type: ignore[no-any-return]


def get_tool_registry(request: Request) -> ToolRegistry:
    return request.app.state.tool_registry  # type: ignore[no-any-return]


_provider_factory: ProviderFactory = DefaultProviderFactory()


def get_provider_factory() -> ProviderFactory:
    return _provider_factory
