"""FastAPI application factory for Laffybot."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from laffybot import __version__
from laffybot.agent_runtime.providers.errors import ProviderError
from laffybot.agent_runtime.tools.errors import ToolError
from laffybot.agent_runtime.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
from laffybot.agent_runtime.tools.mcp.manager import MCPServerConfig, McpServerManager
from laffybot.agent_runtime.tools.registry import ToolRegistry
from laffybot.agent_runtime.tools.shell import ExecTool
from laffybot.agent_runtime.tools.skill_view import SkillViewTool
from laffybot.api.dependencies import (
    build_app_setting_store,
    build_context_builder,
    build_db_manager,
    build_mcp_server_store,
    build_memory_manager,
    build_memory_store,
    build_provider_store,
    build_session_manager,
    build_skill_registry,
    build_skills_loader,
    build_store,
    get_provider_factory,
)
from laffybot.api.errors import (
    error_response,
    map_provider_error,
    map_session_error,
    map_tool_error,
)
from laffybot.api.router import router
from laffybot.config import ApiConfig
from laffybot.db.manager import DatabaseManager
from laffybot.db.provider_store import ProviderStore
from laffybot.db.session_store import SessionStore
from laffybot.eventbus.bus import EventBus
from laffybot.memory import MemoryConfig, MemoryManager
from laffybot.observability.logging import add_error_service_sink
from laffybot.service.context.types import ContextConfig
from laffybot.service.error_log import ErrorLogService, set_error_log
from laffybot.service.errors import SessionError


def create_app(
    api_config: ApiConfig | None = None,
    db_manager: DatabaseManager | None = None,
    store: SessionStore | None = None,
    provider_store: ProviderStore | None = None,
    tool_registry: ToolRegistry | None = None,
    context_config: ContextConfig | None = None,
    memory_manager: MemoryManager | None = None,
    memory_config: MemoryConfig | None = None,
    event_bus: EventBus | None = None,
) -> FastAPI:
    config = api_config or ApiConfig()
    db_manager_obj = db_manager or build_db_manager(config)
    event_bus_obj = event_bus or EventBus()
    store_obj = store or build_store(db_manager_obj)

    # ── Error log service (global singleton) ─────────────────────────────
    jsonl_path = str(Path(config.log_dir) / "errors.jsonl")
    if not Path(jsonl_path).parent.is_absolute():
        jsonl_path = str(Path.cwd() / jsonl_path)
    error_service = ErrorLogService(max_records=200, jsonl_path=jsonl_path)
    error_service.load_from_jsonl()
    set_error_log(error_service)
    add_error_service_sink()

    provider_store_obj = provider_store or build_provider_store(db_manager_obj)
    mcp_server_store_obj = build_mcp_server_store(db_manager_obj)
    app_setting_store_obj = build_app_setting_store(db_manager_obj)
    tool_registry_obj = tool_registry or ToolRegistry()
    memory_store_obj = build_memory_store(db_manager_obj)
    memory_manager_obj = build_memory_manager(
        db_manager=db_manager_obj,
        config=memory_config,
        store=memory_store_obj,
    )
    skills_loader_obj = build_skills_loader()
    skill_registry_obj = build_skill_registry(app_setting_store_obj)
    context_builder_obj = build_context_builder(
        context_config=context_config,
        tool_registry=tool_registry_obj,
    )
    tool_registry_obj.register(ReadFileTool(workspace=Path.cwd()))
    tool_registry_obj.register(WriteFileTool(workspace=Path.cwd()))
    tool_registry_obj.register(EditFileTool(workspace=Path.cwd()))
    tool_registry_obj.register(ListDirTool(workspace=Path.cwd()))
    tool_registry_obj.register(ExecTool(working_dir=str(Path.cwd())))
    tool_registry_obj.register(
        SkillViewTool(loader=skills_loader_obj, registry=skill_registry_obj)
    )
    session_manager_obj = build_session_manager(
        store=store_obj,
        provider_store=provider_store_obj,
        app_setting_store=app_setting_store_obj,
        tool_registry=tool_registry_obj,
        context_builder=context_builder_obj,
        memory_manager=memory_manager_obj,
        memory_store=memory_store_obj,
        mcp_server_store=mcp_server_store_obj,
        skills_loader=skills_loader_obj,
        skill_registry=skill_registry_obj,
        event_bus=event_bus_obj,
        max_active_sessions=config.max_active_sessions,
        provider_factory=get_provider_factory(),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("Application started: version={}", __version__)
        await store_obj.run_migrations()
        await memory_manager_obj.initialize()
        await session_manager_obj.start()

        mcp_manager: McpServerManager = McpServerManager(
            [], tool_registry=tool_registry_obj
        )
        try:
            raw_configs = await mcp_server_store_obj.get_enabled_server_configs()
            if raw_configs:
                configs = [MCPServerConfig(**c) for c in raw_configs]
                mcp_manager = McpServerManager(configs, tool_registry=tool_registry_obj)
                mcp_task = asyncio.create_task(mcp_manager.start())

                def _mcp_start_done(t: asyncio.Task[object]) -> None:
                    exc = t.exception()
                    if exc is not None and not isinstance(exc, asyncio.CancelledError):
                        logger.error("MCP server start failed: {}", exc)

                mcp_task.add_done_callback(_mcp_start_done)
        except Exception as exc:
            logger.warning("Failed to initialize MCP servers: {}", exc)

        app.state.mcp_manager = mcp_manager
        app.state.mcp_server_store = mcp_server_store_obj

        yield

        logger.info("Application shutting down")
        if mcp_manager is not None:
            await mcp_manager.shutdown()
        await session_manager_obj.shutdown()
        await memory_manager_obj.close()
        await event_bus_obj.shutdown()
        await db_manager_obj.close()

    app = FastAPI(title="Laffybot API", version=__version__, lifespan=lifespan)

    if config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_credentials=config.cors_allow_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.state.api_config = config
    app.state.db_manager = db_manager_obj
    app.state.event_bus = event_bus_obj
    app.state.store = store_obj
    app.state.provider_store = provider_store_obj
    app.state.error_service = error_service
    app.state.app_setting_store = app_setting_store_obj
    app.state.tool_registry = tool_registry_obj
    app.state.session_manager = session_manager_obj
    app.state.memory_manager = memory_manager_obj
    app.state.memory_store = memory_store_obj
    app.state.context_config = context_config or ContextConfig()
    app.state.skills_loader = skills_loader_obj
    app.state.skill_registry = skill_registry_obj

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            400, "INVALID_REQUEST", "Invalid request", {"errors": exc.errors()}
        )

    @app.exception_handler(SessionError)
    async def session_exception_handler(_: Request, exc: SessionError) -> JSONResponse:
        return map_session_error(exc)

    @app.exception_handler(ProviderError)
    async def provider_exception_handler(
        _: Request, exc: ProviderError
    ) -> JSONResponse:
        return map_provider_error(exc)

    @app.exception_handler(ToolError)
    async def tool_exception_handler(_: Request, exc: ToolError) -> JSONResponse:
        return map_tool_error(exc)

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.opt(exception=exc).error("Unhandled exception: {}", exc)
        error_service.record(
            level="ERROR",
            source="api.app:generic_exception_handler",
            message=str(exc),
            error_code="INTERNAL_ERROR",
            exc_info=exc,
        )
        return error_response(500, "INTERNAL_ERROR", str(exc))

    app.include_router(router)
    return app
