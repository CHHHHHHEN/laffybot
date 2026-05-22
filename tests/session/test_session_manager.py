"""Tests for SessionManager state machine transitions."""

from collections import namedtuple
from unittest.mock import AsyncMock

import pytest
from laffybot_agent_runtime.tools.registry import ToolRegistry

from laffybot.db.manager import DatabaseManager
from laffybot.db.session_store import SQLiteStore
from laffybot.service.context.builder import SimpleContextBuilder
from laffybot.service.context.types import ContextConfig
from laffybot.service.errors import SessionNotBusyError
from laffybot.service.session_manager import DefaultSessionManager

_FakeModel = namedtuple("FakeModel", ["name"])


@pytest.fixture
async def store() -> SQLiteStore:
    db_manager = DatabaseManager(":memory:")
    s = SQLiteStore(db_manager)
    await db_manager.connect()
    await s.run_migrations()
    return s


@pytest.fixture
async def manager(store: SQLiteStore) -> DefaultSessionManager:
    mock_app_settings = AsyncMock()
    mock_app_settings.get_default_session_config.return_value = None

    mock_provider_store = AsyncMock()
    mock_provider_store.get_provider.return_value = None
    mock_provider_store.list_models.return_value = [_FakeModel(name="test-model")]

    context_builder = SimpleContextBuilder(ContextConfig())

    m = DefaultSessionManager(
        store=store,
        provider_store=mock_provider_store,
        app_setting_store=mock_app_settings,
        tool_registry=ToolRegistry(),
        context_builder=context_builder,
        provider_factory=mock_provider_store,
    )
    await m.start()
    yield m
    await m.shutdown()


class TestSessionManagerCore:
    async def test_cancel_on_idle_raises(self, manager: DefaultSessionManager) -> None:
        session = await manager.create_session(
            provider_id="test", model_name="test-model"
        )
        with pytest.raises(SessionNotBusyError):
            await manager.cancel_request(session.session_id)

    async def test_create_session_idle_status(
        self, manager: DefaultSessionManager
    ) -> None:
        session = await manager.create_session(
            provider_id="test", model_name="test-model"
        )
        assert session.status == "idle"

    async def test_shutdown_clears_background_tasks(
        self, manager: DefaultSessionManager
    ) -> None:
        await manager.shutdown()
        assert manager._watchdog_task is None

    async def test_get_session_info(self, manager: DefaultSessionManager) -> None:
        session = await manager.create_session(
            provider_id="test", model_name="test-model"
        )
        info = await manager.get_session_info(session.session_id)
        assert info.session_id == session.session_id
        assert info.status == "idle"
