# mypy: disable-error-code="untyped-decorator"
"""Tests for SQLite session store."""

import uuid

import pytest

from laffybot.db.manager import DatabaseManager
from laffybot.db.session_store import SQLiteStore
from laffybot.service.errors import SessionNotFoundError, SessionStateError
from laffybot.service.models import SessionInfo


@pytest.fixture
async def store() -> SQLiteStore:
    db_manager = DatabaseManager(":memory:")
    s = SQLiteStore(db_manager)
    await db_manager.connect()
    await s.run_migrations()
    return s


@pytest.fixture
def session_id() -> str:
    return str(uuid.uuid4())


async def _create_session(store: SQLiteStore, session_id: str) -> SessionInfo:
    return await store.create_session(
        session_id=session_id,
        provider_id="test-provider",
        model_name="test-model",
        system_prompt=None,
        max_iterations=50,
    )


class TestSessionCRUD:
    async def test_create_session(self, store: SQLiteStore, session_id: str) -> None:
        session = await _create_session(store, session_id)
        assert session.session_id == session_id
        assert session.status == "idle"
        assert session.provider_id == "test-provider"
        assert session.model_name == "test-model"

    async def test_get_session(self, store: SQLiteStore, session_id: str) -> None:
        await _create_session(store, session_id)
        session = await store.get_session(session_id)
        assert session.session_id == session_id

    async def test_get_session_not_found(self, store: SQLiteStore) -> None:
        with pytest.raises(SessionNotFoundError):
            await store.get_session("nonexistent")

    async def test_delete_session(self, store: SQLiteStore, session_id: str) -> None:
        await _create_session(store, session_id)
        await store.delete_session(session_id)
        with pytest.raises(SessionNotFoundError):
            await store.get_session(session_id)

    async def test_list_sessions(self, store: SQLiteStore) -> None:
        await _create_session(store, "sess-1")
        await _create_session(store, "sess-2")
        sessions, total = await store.list_sessions(limit=10, offset=0)
        assert total >= 2
        assert any(s.session_id == "sess-1" for s in sessions)

    async def test_list_sessions_with_status_filter(self, store: SQLiteStore) -> None:
        await _create_session(store, "sess-1")
        busy_sessions, _ = await store.list_sessions(status="busy", limit=10)
        for s in busy_sessions:
            assert s.status == "busy"


class TestSessionStatus:
    async def test_update_session_status(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        success = await store.update_session_status(
            session_id, "busy", current_request_id="req-1", expected_status="idle"
        )
        assert success
        session = await store.get_session(session_id)
        assert session.status == "busy"
        assert session.current_request_id == "req-1"

    async def test_update_status_optimistic_lock_fails(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        await store.update_session_status(session_id, "busy", expected_status="idle")
        with pytest.raises(SessionStateError):
            await store.update_session_status(
                session_id, "idle", expected_status="idle"
            )

    async def test_update_status_no_expected_status(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        success = await store.update_session_status(
            session_id, "error", current_request_id=None
        )
        assert success
        session = await store.get_session(session_id)
        assert session.status == "error"

    async def test_update_status_reset_request_id(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        await store.update_session_status(
            session_id, "busy", current_request_id="req-1", expected_status="idle"
        )
        await store.update_session_status(
            session_id, "idle", current_request_id=None, expected_status="busy"
        )
        session = await store.get_session(session_id)
        assert session.status == "idle"
        assert session.current_request_id is None


class TestMessages:
    async def test_save_and_get_messages(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        await store.save_message(session_id, "user", "Hello")
        await store.save_message(session_id, "assistant", "Hi there")
        messages = await store.get_messages(session_id)
        assert len(messages) >= 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    async def test_get_messages_limit(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        for i in range(5):
            await store.save_message(session_id, "user", f"msg {i}")
        messages = await store.get_messages(session_id, limit=3)
        assert len(messages) == 3

    async def test_get_message_count(self, store: SQLiteStore, session_id: str) -> None:
        await _create_session(store, session_id)
        await store.save_message(session_id, "user", "Hello")
        await store.save_message(session_id, "assistant", "Hi")
        assert await store.get_message_count(session_id) >= 2


class TestTitleAndArchive:
    async def test_update_session_title(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        success = await store.update_session_title(
            session_id,
            "New Title",
            expected_user_message_count=0,
            expected_title_auto_generated=False,
        )
        assert success
        session = await store.get_session(session_id)
        assert session.title == "New Title"

    async def test_update_title_optimistic_lock_fails(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        await store.save_message(session_id, "user", "Hello")
        success = await store.update_session_title(
            session_id,
            "Title",
            expected_user_message_count=0,
            expected_title_auto_generated=False,
        )
        assert not success

    async def test_archive_and_unarchive(
        self, store: SQLiteStore, session_id: str
    ) -> None:
        await _create_session(store, session_id)
        archived = await store.archive_session(session_id)
        assert archived.archived_at is not None
        unarchived = await store.unarchive_session(session_id)
        assert unarchived.archived_at is None
