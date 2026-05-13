"""FastAPI application factory for Laffybot."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from laffybot import __version__
from laffybot.agent.tools.registry import ToolRegistry
from laffybot.api.dependencies import (
    build_session_manager,
    build_store,
    default_provider_factory,
)
from laffybot.api.errors import error_response, map_session_error
from laffybot.api.routes import router
from laffybot.config import ApiConfig, ContextConfig
from laffybot.providers.base import BaseProvider
from laffybot.session.errors import SessionError
from laffybot.session.manager import SessionManager
from laffybot.session.store import SessionStore


def create_app(
    api_config: ApiConfig | None = None,
    store: SessionStore | None = None,
    session_manager: SessionManager | None = None,
    tool_registry: ToolRegistry | None = None,
    provider_factory: Callable[[str], BaseProvider] | None = None,
    context_config: ContextConfig | None = None,
) -> FastAPI:
    config = api_config or ApiConfig()
    store_obj = store or build_store(config)
    tool_registry_obj = tool_registry or ToolRegistry()
    provider_factory_obj = provider_factory or default_provider_factory()
    session_manager_obj = session_manager or build_session_manager(
        store=store_obj,
        tool_registry=tool_registry_obj,
        provider_factory=provider_factory_obj,
        context_config=context_config,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await store_obj.close()

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
    app.state.tool_registry = tool_registry_obj
    app.state.provider_factory = provider_factory_obj
    app.state.session_manager = session_manager_obj

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return error_response(400, "INVALID_REQUEST", "Invalid request", {"errors": exc.errors()})

    @app.exception_handler(SessionError)
    async def session_exception_handler(_: Request, exc: SessionError) -> JSONResponse:
        return map_session_error(exc)

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return error_response(500, "INTERNAL_ERROR", str(exc))

    app.include_router(router)
    return app


app = create_app()
