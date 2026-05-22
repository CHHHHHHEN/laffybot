"""Dependency helpers for the HTTP API — provides store/manager instances via DI."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from laffybot_agent_runtime.providers.openai import OpenAIProvider
from laffybot_agent_runtime.skills import SkillRegistry, SkillsLoader
from laffybot_agent_runtime.tools.registry import ToolRegistry

from laffybot.config import ApiConfig
from laffybot.db.app_setting_store import AppSettingStore, SQLiteAppSettingStore
from laffybot.db.manager import DatabaseManager
from laffybot.db.mcp_server_store import McpServerStore, SQLiteMcpServerStore
from laffybot.db.memory_store import MemoryStore, SQLiteMemoryStore
from laffybot.db.provider_store import ProviderStore, SQLiteProviderStore
from laffybot.db.session_store import SessionStore, SQLiteStore
from laffybot.eventbus.bus import EventBus
from laffybot.memory import MemoryConfig, MemoryManager
from laffybot.service.context.builder import SimpleContextBuilder
from laffybot.service.context.types import ContextConfig
from laffybot.service.protocols import SessionManager
from laffybot.service.provider_factory import DefaultProviderFactory, ProviderFactory
from laffybot.service.session_manager import DefaultSessionManager

# ── Database manager (shared connection) ────────────────────────────────────


def build_db_manager(config: ApiConfig) -> DatabaseManager:
    return DatabaseManager(config.database_path)


# ── Builders (composition root helpers) ──────────────────────────────────────


def build_store(db_manager: DatabaseManager) -> SessionStore:
    return SQLiteStore(db_manager)


def build_provider_store(db_manager: DatabaseManager) -> ProviderStore:
    return SQLiteProviderStore(db_manager)


def build_mcp_server_store(db_manager: DatabaseManager) -> McpServerStore:
    return SQLiteMcpServerStore(db_manager)


def build_app_setting_store(db_manager: DatabaseManager) -> AppSettingStore:
    return SQLiteAppSettingStore(db_manager)


def build_memory_store(db_manager: DatabaseManager) -> MemoryStore:
    return SQLiteMemoryStore(db_manager)


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
    context_builder: SimpleContextBuilder | None = None,
    memory_manager: MemoryManager | None = None,
    memory_store: MemoryStore | None = None,
    mcp_server_store: McpServerStore | None = None,
    mcp_manager: Any | None = None,
    skills_loader: SkillsLoader | None = None,
    skill_registry: SkillRegistry | None = None,
    event_bus: EventBus | None = None,
    max_active_sessions: int = 3,
    tool_timeout_s: int = 120,
    session_timeout_s: int = 600,
    watchdog_interval_s: int = 60,
    provider_factory: ProviderFactory | None = None,
) -> DefaultSessionManager:
    if context_builder is None:
        context_builder = build_context_builder(tool_registry=tool_registry)
    return DefaultSessionManager(
        store=store,
        provider_store=provider_store,
        app_setting_store=app_setting_store,
        tool_registry=tool_registry,
        provider_factory=provider_factory or DefaultProviderFactory(),
        context_builder=context_builder,
        memory_manager=memory_manager,
        memory_store=memory_store,
        mcp_server_store=mcp_server_store,
        mcp_manager=mcp_manager,
        skills_loader=skills_loader,
        skill_registry=skill_registry,
        event_bus=event_bus,
        max_active_sessions=max_active_sessions,
        tool_timeout_s=tool_timeout_s,
        session_timeout_s=session_timeout_s,
        watchdog_interval_s=watchdog_interval_s,
    )


async def render_skills_block(
    app_setting_store: AppSettingStore,
    skills_loader: SkillsLoader,
    skill_registry: SkillRegistry,
) -> str:
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


# ── Build memory manager ────────────────────────────────────────────────────


def build_memory_manager(
    db_manager: DatabaseManager,
    config: MemoryConfig | None = None,
    store: MemoryStore | None = None,
) -> MemoryManager:
    return MemoryManager(config or MemoryConfig(), store=store, db_manager=db_manager)


# ── FastAPI Depends accessors ────────────────────────────────────────────────


def get_db_manager(request: Request) -> DatabaseManager:
    return request.app.state.db_manager  # type: ignore[no-any-return]


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


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus  # type: ignore[no-any-return]


_provider_factory: ProviderFactory = DefaultProviderFactory(
    provider_map={"openai": OpenAIProvider},
)


def get_provider_factory() -> ProviderFactory:
    return _provider_factory
