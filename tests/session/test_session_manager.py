"""Tests for SessionManager state machine transitions."""

from collections import namedtuple
from unittest.mock import AsyncMock

import pytest

from laffybot.agent.tools.registry import ToolRegistry
from laffybot.config import ContextConfig
from laffybot.context.builder import SimpleContextBuilder
from laffybot.session.errors import SessionNotBusyError
from laffybot.session.manager import SessionManager
from laffybot.session.store import SQLiteStore

_FakeModel = namedtuple("FakeModel", ["name"])


@pytest.fixture
async def store() -> SQLiteStore:
    s = SQLiteStore(":memory:")
    await s._ensure_db()
    yield s
    await s.close()


@pytest.fixture
async def manager(store: SQLiteStore) -> SessionManager:
    mock_app_settings = AsyncMock()
    mock_app_settings.get_default_session_config.return_value = None

    mock_provider_store = AsyncMock()
    mock_provider_store.get_provider.return_value = None
    mock_provider_store.list_models.return_value = [_FakeModel(name="test-model")]

    context_builder = SimpleContextBuilder(ContextConfig())

    m = SessionManager(
        store=store,
        provider_store=mock_provider_store,
        app_setting_store=mock_app_settings,
        tool_registry=ToolRegistry(),
        context_builder=context_builder,
        provider_factory=store,
    )
    await m.start()
    yield m
    await m.shutdown()


class TestSessionManagerLockAndToken:
    async def test_lock_per_session(self, manager: SessionManager) -> None:
        lock1 = manager._lock_for("sess-1")
        lock2 = manager._lock_for("sess-1")
        assert lock1 is lock2

    async def test_lock_isolation(self, manager: SessionManager) -> None:
        lock_a = manager._lock_for("sess-a")
        lock_b = manager._lock_for("sess-b")
        assert lock_a is not lock_b

    async def test_cancel_on_idle_raises(self, manager: SessionManager) -> None:
        session = await manager.create_session(
            provider_id="test", model_name="test-model"
        )
        with pytest.raises(SessionNotBusyError):
            await manager.cancel_request(session.session_id)

    async def test_create_session_idle_status(self, manager: SessionManager) -> None:
        session = await manager.create_session(
            provider_id="test", model_name="test-model"
        )
        assert session.status == "idle"

    async def test_active_tokens_empty_initially(self, manager: SessionManager) -> None:
        assert len(manager._active_tokens) == 0

    async def test_locks_empty_initially(self, manager: SessionManager) -> None:
        assert len(manager._locks) == 0

    async def test_shutdown_clears_background_tasks(
        self, manager: SessionManager
    ) -> None:
        await manager.shutdown()
        assert manager._watchdog_task is None

    async def test_watchdog_configured_defaults(self, manager: SessionManager) -> None:
        assert manager._session_timeout_s == 600
        assert manager._watchdog_interval_s == 60

    async def test_get_session_info(self, manager: SessionManager) -> None:
        session = await manager.create_session(
            provider_id="test", model_name="test-model"
        )
        info = await manager.get_session_info(session.session_id)
        assert info.session_id == session.session_id
        assert info.status == "idle"
