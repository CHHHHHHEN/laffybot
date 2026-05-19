"""Dependency helpers for the HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from laffybot.agent.skills import SkillRegistry, SkillsLoader
from laffybot.agent.tools.registry import ToolRegistry
from laffybot.api.event_bus import get_event_bus
from laffybot.config import ApiConfig, ContextConfig
from laffybot.context import ContextBuilder, SimpleContextBuilder
from laffybot.memory import MemoryConfig, MemoryManager, MemoryStore, SQLiteMemoryStore
from laffybot.providers.base import BaseProvider
from laffybot.providers.config import ProviderConfig
from laffybot.providers.factory import ProviderFactory
from laffybot.providers.openai import OpenAIProvider
from laffybot.session.app_setting_store import AppSettingStore, SQLiteAppSettingStore
from laffybot.session.manager import SessionManager
from laffybot.session.mcp_server_store import McpServerStore, SQLiteMcpServerStore
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


def build_mcp_server_store(config: ApiConfig) -> McpServerStore:
    return SQLiteMcpServerStore(config.database_path)


def build_app_setting_store(config: ApiConfig) -> AppSettingStore:
    return SQLiteAppSettingStore(config.database_path)


def build_memory_store(config: ApiConfig) -> MemoryStore:
    return SQLiteMemoryStore(config.database_path)


def build_skills_loader() -> SkillsLoader:
    return SkillsLoader()


def build_skill_registry(
    app_setting_store: AppSettingStore,
) -> SkillRegistry:
    return SkillRegistry(app_setting_store)


def build_context_builder(
    context_config: ContextConfig | None = None,
    tool_registry: ToolRegistry | None = None,
) -> SimpleContextBuilder:
    return SimpleContextBuilder(
        config=context_config or ContextConfig(),
        tool_registry=tool_registry,
    )


def build_session_manager(
    store: SessionStore,
    provider_store: ProviderStore,
    app_setting_store: AppSettingStore,
    tool_registry: ToolRegistry,
    context_builder: ContextBuilder | None = None,
    memory_manager: MemoryManager | None = None,
    max_active_sessions: int = 3,
    tool_timeout_s: int = 120,
    session_timeout_s: int = 600,
    watchdog_interval_s: int = 60,
    provider_factory: ProviderFactory | None = None,
) -> SessionManager:
    if context_builder is None:
        context_builder = build_context_builder(tool_registry=tool_registry)
    return SessionManager(
        store=store,
        provider_store=provider_store,
        app_setting_store=app_setting_store,
        tool_registry=tool_registry,
        provider_factory=provider_factory or DefaultProviderFactory(),
        context_builder=context_builder,
        memory_manager=memory_manager,
        max_active_sessions=max_active_sessions,
        tool_timeout_s=tool_timeout_s,
        session_timeout_s=session_timeout_s,
        watchdog_interval_s=watchdog_interval_s,
        event_publisher=get_event_bus(),
    )


async def render_skills_block(
    app_setting_store: AppSettingStore,
    skills_loader: SkillsLoader,
    skill_registry: SkillRegistry,
) -> str:
    """Render the ``skills_block`` XML fragment for system prompt injection.

    Returns an empty string when no skills are enabled or configured.
    """
    enabled_skills = await skill_registry.get_enabled_skills()
    if not enabled_skills:
        return ""

    skills_path = await app_setting_store.get_skills_path()
    if not skills_path:
        return ""

    all_skills = skills_loader.discover_skills(skills_path)
    enabled_metadata = [s for s in all_skills if s.name in enabled_skills]
    if not enabled_metadata:
        return ""

    blocks: list[str] = []
    for s in enabled_metadata:
        blocks.append(
            f"<skill>\n<name>{s.name}</name>\n<description>{s.description}</description>\n</skill>"
        )
    return "<available_skills>\n" + "\n".join(blocks) + "\n</available_skills>"


def get_api_config(request: Request) -> ApiConfig:
    return request.app.state.api_config  # type: ignore[no-any-return]


def get_store(request: Request) -> SessionStore:
    return request.app.state.store  # type: ignore[no-any-return]


def get_provider_store(request: Request) -> ProviderStore:
    return request.app.state.provider_store  # type: ignore[no-any-return]


def get_mcp_server_store(request: Request) -> McpServerStore:
    return request.app.state.mcp_server_store  # type: ignore[no-any-return]


def get_mcp_manager(request: Request) -> Any | None:
    return getattr(request.app.state, "mcp_manager", None)


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


def get_skills_loader(request: Request) -> SkillsLoader:
    return request.app.state.skills_loader  # type: ignore[no-any-return]


def get_skill_registry(request: Request) -> SkillRegistry:
    return request.app.state.skill_registry  # type: ignore[no-any-return]


_provider_factory: ProviderFactory = DefaultProviderFactory()


def get_provider_factory() -> ProviderFactory:
    return _provider_factory
