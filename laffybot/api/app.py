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
from laffybot.agent.tools.errors import ToolError
from laffybot.agent.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
from laffybot.agent.tools.registry import ToolRegistry
from laffybot.agent.tools.shell import ExecTool
from laffybot.api.dependencies import (
    build_app_setting_store,
    build_memory_manager,
    build_memory_store,
    build_provider_store,
    build_session_manager,
    build_store,
)
from laffybot.api.errors import error_response, map_provider_error, map_session_error
from laffybot.api.routes import router
from laffybot.config import ApiConfig, ContextConfig
from laffybot.memory import MemoryConfig, MemoryManager, MemoryNotFoundError
from laffybot.providers.errors import ProviderError
from laffybot.session.errors import SessionError
from laffybot.session.provider_store import ProviderStore
from laffybot.session.store import SessionStore


def create_app(
    api_config: ApiConfig | None = None,
    store: SessionStore | None = None,
    provider_store: ProviderStore | None = None,
    tool_registry: ToolRegistry | None = None,
    context_config: ContextConfig | None = None,
    memory_manager: MemoryManager | None = None,
    memory_config: MemoryConfig | None = None,
) -> FastAPI:
    config = api_config or ApiConfig()
    store_obj = store or build_store(config)
    provider_store_obj = provider_store or build_provider_store(config)
    app_setting_store_obj = build_app_setting_store(config)
    tool_registry_obj = tool_registry or ToolRegistry()
    memory_store_obj = build_memory_store(config)
    memory_manager_obj = memory_manager or build_memory_manager(
        memory_config, store=memory_store_obj, db_path=config.database_path
    )
    tool_registry_obj.register(ReadFileTool(workspace=Path.cwd()))
    tool_registry_obj.register(WriteFileTool(workspace=Path.cwd()))
    tool_registry_obj.register(EditFileTool(workspace=Path.cwd()))
    tool_registry_obj.register(ListDirTool(workspace=Path.cwd()))
    tool_registry_obj.register(ExecTool(working_dir=str(Path.cwd())))
    session_manager_obj = build_session_manager(
        store=store_obj,
        provider_store=provider_store_obj,
        app_setting_store=app_setting_store_obj,
        tool_registry=tool_registry_obj,
        context_config=context_config,
        memory_manager=memory_manager_obj,
        max_active_sessions=config.max_active_sessions,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("Application started: version={}", __version__)
        await memory_manager_obj.initialize()
        await session_manager_obj.start()
        yield
        logger.info("Application shutting down")
        await session_manager_obj.shutdown()
        for obj in (provider_store_obj, store_obj, app_setting_store_obj):
            try:
                await asyncio.wait_for(obj.close(), timeout=5)
            except TimeoutError:
                logger.warning("store close timed out")
            except Exception:
                logger.exception("store close failed")
        await memory_manager_obj.close()

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
    app.state.store = store_obj
    app.state.provider_store = provider_store_obj
    app.state.app_setting_store = app_setting_store_obj
    app.state.tool_registry = tool_registry_obj
    app.state.session_manager = session_manager_obj
    app.state.memory_manager = memory_manager_obj
    app.state.memory_store = memory_store_obj
    app.state.context_config = context_config or ContextConfig()

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
        return error_response(
            500 if exc.code == "TOOL_EXECUTION_ERROR" else 400,
            exc.code,
            str(exc),
            {"tool_name": exc.tool_name} if exc.tool_name else None,
        )

    @app.exception_handler(MemoryNotFoundError)
    async def memory_not_found_handler(
        _: Request, exc: MemoryNotFoundError
    ) -> JSONResponse:
        return error_response(404, "MEMORY_NOT_FOUND", str(exc))

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return error_response(500, "INTERNAL_ERROR", str(exc))

    app.include_router(router)
    return app


app = create_app()
