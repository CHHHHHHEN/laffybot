# mypy: disable-error-code="untyped-decorator"
"""Tests for FileStates and FileStateStore."""

from __future__ import annotations

import collections.abc
from pathlib import Path

import pytest

from laffybot.agent_runtime.tools.file_state import (
    FileStates,
    FileStateStore,
    ReadState,
    bind_file_states,
    check_read,
    clear,
    current_file_states,
    is_unchanged,
    record_read,
    record_write,
    reset_file_states,
)


class TestFileStates:
    """FileStates — per-session read/write tracker."""

    def test_fresh_state_check_read_warns(self) -> None:
        fs = FileStates()
        msg = fs.check_read("/nonexistent")
        assert msg is not None
        assert "not been read" in msg

    def test_record_read_then_check_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        fs.record_read(f)
        assert fs.check_read(f) is None

    def test_record_write_then_check_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        fs.record_write(f)
        assert fs.check_read(f) is None

    def test_check_read_detects_content_change(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        fs.record_read(f)
        f.write_text("world")
        msg = fs.check_read(f)
        assert msg is not None
        assert "modified" in msg

    def test_check_read_detects_unread_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        msg = fs.check_read(f)
        assert msg is not None
        assert "not been read" in msg

    def test_is_unchanged_after_read(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        fs.record_read(f)
        assert fs.is_unchanged(f) is True

    def test_is_unchanged_false_after_write(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        fs.record_read(f)
        f.write_text("world")
        assert fs.is_unchanged(f) is False

    def test_is_unchanged_with_different_offset(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello\nworld\nfoo\n")
        fs = FileStates()
        fs.record_read(f, offset=1, limit=2)
        assert fs.is_unchanged(f, offset=1, limit=2) is True
        assert fs.is_unchanged(f, offset=2, limit=2) is False

    def test_record_write_disables_dedup(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        fs.record_read(f)
        assert fs.is_unchanged(f) is True
        fs.record_write(f)
        assert fs.is_unchanged(f) is False

    def test_get_returns_read_state(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        fs.record_read(f)
        state = fs.get(f)
        assert state is not None
        assert isinstance(state, ReadState)
        assert state.offset == 1
        assert state.limit is None

    def test_get_nonexistent_returns_none(self) -> None:
        fs = FileStates()
        assert fs.get("/nonexistent") is None

    def test_clear_resets_state(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        fs = FileStates()
        fs.record_read(f)
        assert fs.get(f) is not None
        fs.clear()
        assert fs.get(f) is None

    def test_nonexistent_file_skips_record_read(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.txt"
        fs = FileStates()
        fs.record_read(f)
        assert fs.get(f) is None  # can't get mtime → skip

    def test_record_read_stores_offset_and_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("a\nb\nc\n")
        fs = FileStates()
        fs.record_read(f, offset=2, limit=1)
        state = fs.get(f)
        assert state is not None
        assert state.offset == 2
        assert state.limit == 1


class TestFileStateStore:
    """FileStateStore — lookup table for per-session states."""

    def test_for_session_returns_file_states(self) -> None:
        store = FileStateStore()
        fs = store.for_session("session_1")
        assert isinstance(fs, FileStates)

    def test_same_key_returns_same_instance(self) -> None:
        store = FileStateStore()
        fs1 = store.for_session("session_1")
        fs2 = store.for_session("session_1")
        assert fs1 is fs2

    def test_different_keys_return_different_instances(self) -> None:
        store = FileStateStore()
        fs1 = store.for_session("session_1")
        fs2 = store.for_session("session_2")
        assert fs1 is not fs2

    def test_default_key_for_none(self) -> None:
        store = FileStateStore()
        fs1 = store.for_session(None)
        fs2 = store.for_session(None)
        assert fs1 is fs2

    def test_clear_resets_all(self) -> None:
        store = FileStateStore()
        fs1 = store.for_session("s1")
        fs2 = store.for_session("s2")
        assert fs1 is not fs2
        store.clear()
        # After clear, new calls return fresh instances
        fs3 = store.for_session("s1")
        assert fs3 is not fs1


class TestContextVarBindings:
    """ContextVar-based per-task state binding."""

    def test_current_file_states_falls_back(self) -> None:
        default = FileStates()
        result = current_file_states(default)
        assert result is default

    def test_bind_and_current(self) -> None:
        default = FileStates()
        bound = FileStates()
        token = bind_file_states(bound)
        result = current_file_states(default)
        assert result is bound
        reset_file_states(token)
        result2 = current_file_states(default)
        assert result2 is default

    def test_nested_bind_restores(self) -> None:
        default = FileStates()
        outer = FileStates()
        inner = FileStates()
        t1 = bind_file_states(outer)
        t2 = bind_file_states(inner)
        assert current_file_states(default) is inner
        reset_file_states(t2)
        assert current_file_states(default) is outer
        reset_file_states(t1)
        assert current_file_states(default) is default

    def test_current_without_bind_uses_default(self) -> None:
        default = FileStates()
        result = current_file_states(default)
        assert result is default


class TestModuleLevelFunctions:
    """Module-level backward-compat helper functions."""

    @pytest.fixture(autouse=True)
    def _auto_cleanup(self) -> collections.abc.Generator[None, None, None]:
        clear()
        yield
        clear()

    def test_record_read_and_is_unchanged(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        record_read(f)
        assert is_unchanged(f) is True

    def test_record_write_disables_dedup(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        record_read(f)
        record_write(f)
        assert is_unchanged(f) is False

    def test_check_read_unread(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        msg = check_read(f)
        assert msg is not None

    def test_clear(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        record_read(f)
        assert is_unchanged(f) is True
        clear()
        assert is_unchanged(f) is False
