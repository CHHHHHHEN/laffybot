# mypy: disable-error-code="untyped-decorator"
"""Tests for filesystem tools: ReadFileTool, WriteFileTool, EditFileTool, ListDirTool."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from laffybot.agent_runtime.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
    _is_blocked_device,
    _parse_page_range,
    _resolve_path,
)

# ── Helpers ─────────────────────────────────────────────────────────────


def _read_tool(tmp_path: Path) -> ReadFileTool:
    return ReadFileTool(workspace=tmp_path, allowed_dir=tmp_path)


def _write_tool(tmp_path: Path) -> WriteFileTool:
    return WriteFileTool(workspace=tmp_path, allowed_dir=tmp_path)


def _edit_tool(tmp_path: Path, file_states: Any = None) -> EditFileTool:
    return EditFileTool(
        workspace=tmp_path, allowed_dir=tmp_path, file_states=file_states
    )


def _list_tool(tmp_path: Path) -> ListDirTool:
    return ListDirTool(workspace=tmp_path, allowed_dir=tmp_path)


# ── _resolve_path ───────────────────────────────────────────────────────


class TestResolvePath:
    def test_relative_resolves_against_workspace(self, tmp_path: Path) -> None:
        result = _resolve_path("sub/file.txt", workspace=tmp_path)
        assert result == (tmp_path / "sub/file.txt").resolve()

    def test_absolute_path_ignores_workspace(self, tmp_path: Path) -> None:
        p = tmp_path / "absolute.txt"
        p.write_text("test")
        result = _resolve_path(str(p), workspace=tmp_path, allowed_dir=tmp_path)
        assert result == p.resolve()

    def test_permission_error_outside_allowed(self, tmp_path: Path) -> None:
        outside = tmp_path / ".." / "outside"
        with pytest.raises(PermissionError):
            _resolve_path(str(outside), allowed_dir=tmp_path)


# ── _is_blocked_device ──────────────────────────────────────────────────


class TestIsBlockedDevice:
    def test_blocked_devices_return_true(self) -> None:
        assert _is_blocked_device("/dev/zero") is True
        assert _is_blocked_device("/dev/random") is True

    def test_regular_path_returns_false(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert _is_blocked_device(str(f)) is False


# ── _parse_page_range ───────────────────────────────────────────────────


class TestParsePageRange:
    def test_single_page(self) -> None:
        assert _parse_page_range("3", 10) == (2, 2)

    def test_range(self) -> None:
        assert _parse_page_range("2-5", 10) == (1, 4)

    def test_range_clamped_to_total(self) -> None:
        assert _parse_page_range("8-20", 10) == (7, 9)

    def test_single_page_clamped(self) -> None:
        # Start exceeds total — caller detects and rejects start > end
        result = _parse_page_range("15", 10)
        assert result == (14, 9)  # end is clamped but start is not


# ── ReadFileTool ────────────────────────────────────────────────────────


class TestReadFileTool:
    @pytest.mark.asyncio
    async def test_read_text_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello\nworld\n")
        tool = _read_tool(tmp_path)
        result = await tool.execute(path=str(f))
        assert "hello" in result
        assert "world" in result

    @pytest.mark.asyncio
    async def test_read_with_offset_and_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\nline4\n")
        tool = _read_tool(tmp_path)
        result = await tool.execute(path=str(f), offset=2, limit=2)
        assert "2| line2" in result
        assert "3| line3" in result
        assert "1| line1" not in result

    @pytest.mark.asyncio
    async def test_file_not_found(self, tmp_path: Path) -> None:
        tool = _read_tool(tmp_path)
        result = await tool.execute(path=str(tmp_path / "nonexistent.txt"))
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_binary_file(self, tmp_path: Path) -> None:
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\xff\xfe")  # invalid UTF-8 bytes
        tool = _read_tool(tmp_path)
        result = await tool.execute(path=str(f))
        assert "Error" in result

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not sys.platform.startswith("linux"), reason="requires Linux /dev/ paths"
    )
    async def test_device_path_blocked(self) -> None:
        tool = _read_tool(Path("/tmp"))
        result = await tool.execute(path="/dev/zero")
        assert "blocked" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("")
        tool = _read_tool(tmp_path)
        result = await tool.execute(path=str(f))
        assert "(Empty file" in result or "Empty" in result

    @pytest.mark.asyncio
    async def test_offset_beyond_file(self, tmp_path: Path) -> None:
        f = tmp_path / "short.txt"
        f.write_text("hi\n")
        tool = _read_tool(tmp_path)
        result = await tool.execute(path=str(f), offset=100)
        assert "beyond" in result.lower()

    @pytest.mark.asyncio
    async def test_path_outside_workspace_rejected(self, tmp_path: Path) -> None:
        outside = tmp_path / ".." / "secret.txt"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("secret")
        tool = _read_tool(tmp_path)
        result = await tool.execute(path=str(outside))
        assert "Error" in result


# ── WriteFileTool ───────────────────────────────────────────────────────


class TestWriteFileTool:
    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path: Path) -> None:
        f = tmp_path / "new.txt"
        tool = _write_tool(tmp_path)
        result = await tool.execute(path=str(f), content="hello world")
        assert "Successfully wrote" in result
        assert f.read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        f = tmp_path / "sub" / "nested" / "file.txt"
        tool = _write_tool(tmp_path)
        result = await tool.execute(path=str(f), content="nested")
        assert "Successfully" in result
        assert f.read_text() == "nested"

    @pytest.mark.asyncio
    async def test_overwrite_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "existing.txt"
        f.write_text("old")
        tool = _write_tool(tmp_path)
        result = await tool.execute(path=str(f), content="new")
        assert "Successfully" in result
        assert f.read_text() == "new"

    @pytest.mark.asyncio
    async def test_write_outside_workspace_rejected(self, tmp_path: Path) -> None:
        outside = tmp_path / ".." / "outside_write.txt"
        tool = _write_tool(tmp_path)
        result = await tool.execute(path=str(outside), content="test")
        assert "Error" in result


# ── ListDirTool ─────────────────────────────────────────────────────────


class TestListDirTool:
    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        tool = _list_tool(tmp_path)
        result = await tool.execute(path=str(tmp_path))
        assert "a.txt" in result
        assert "b.txt" in result

    @pytest.mark.asyncio
    async def test_recursive(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep")
        tool = _list_tool(tmp_path)
        result = await tool.execute(path=str(tmp_path), recursive=True)
        assert "deep.txt" in result

    @pytest.mark.asyncio
    async def test_ignores_noise_dirs(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / "actual.txt").write_text("real")
        tool = _list_tool(tmp_path)
        result = await tool.execute(path=str(tmp_path))
        assert ".git" not in result
        assert "actual.txt" in result

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty_dir"
        empty.mkdir()
        tool = _list_tool(tmp_path)
        result = await tool.execute(path=str(empty))
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_directory_not_found(self, tmp_path: Path) -> None:
        tool = _list_tool(tmp_path)
        result = await tool.execute(path=str(tmp_path / "nonexistent"))
        assert "not found" in result.lower()


# ── EditFileTool ────────────────────────────────────────────────────────


class TestEditFileTool:
    @pytest.mark.asyncio
    async def test_basic_replace(self, tmp_path: Path) -> None:
        f = tmp_path / "edit.txt"
        f.write_text("hello world")
        tool = _edit_tool(tmp_path)
        result = await tool.execute(path=str(f), old_text="world", new_text="there")
        assert "Successfully edited" in result
        assert f.read_text() == "hello there"

    @pytest.mark.asyncio
    async def test_replace_all(self, tmp_path: Path) -> None:
        f = tmp_path / "multi.txt"
        f.write_text("a a a")
        tool = _edit_tool(tmp_path)
        result = await tool.execute(
            path=str(f), old_text="a", new_text="b", replace_all=True
        )
        assert "Successfully" in result
        assert f.read_text() == "b b b"

    @pytest.mark.asyncio
    async def test_multiple_matches_without_replace_all_warns(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "multi.txt"
        f.write_text("a a a")
        tool = _edit_tool(tmp_path)
        result = await tool.execute(path=str(f), old_text="a", new_text="b")
        assert "appears" in result
        assert "times" in result

    @pytest.mark.asyncio
    async def test_create_file_semantics(self, tmp_path: Path) -> None:
        f = tmp_path / "new_edit.txt"
        tool = _edit_tool(tmp_path)
        result = await tool.execute(path=str(f), old_text="", new_text="created")
        assert "Successfully created" in result
        assert f.read_text() == "created"

    @pytest.mark.asyncio
    async def test_create_rejects_existing_nonempty(self, tmp_path: Path) -> None:
        f = tmp_path / "exists.txt"
        f.write_text("content")
        tool = _edit_tool(tmp_path)
        result = await tool.execute(path=str(f), old_text="", new_text="new")
        assert "already exists" in result.lower()

    @pytest.mark.asyncio
    async def test_old_text_not_found(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("hello world")
        tool = _edit_tool(tmp_path)
        result = await tool.execute(path=str(f), old_text="nonexistent", new_text="x")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_ipynb_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "notebook.ipynb"
        f.write_text("{}\n")
        tool = _edit_tool(tmp_path)
        result = await tool.execute(path=str(f), old_text="{}", new_text="x")
        assert "notebook" in result.lower()

    @pytest.mark.asyncio
    async def test_no_path_returns_error(self, tmp_path: Path) -> None:
        tool = _edit_tool(tmp_path)
        result = await tool.execute(path="", old_text="x", new_text="y")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_trimmed_match_succeeds(self, tmp_path: Path) -> None:
        f = tmp_path / "indent.txt"
        f.write_text("  hello\n  world\n")
        tool = _edit_tool(tmp_path)
        result = await tool.execute(
            path=str(f), old_text="hello\nworld", new_text="hi\nthere"
        )
        assert "Successfully" in result
        assert f.read_text() == "  hi\n  there\n"

    @pytest.mark.asyncio
    async def test_quote_normalized_match_succeeds(self, tmp_path: Path) -> None:
        f = tmp_path / "quotes.txt"
        f.write_text('he said "hello"')
        tool = _edit_tool(tmp_path)
        result = await tool.execute(
            path=str(f), old_text='he said "hello"', new_text='she said "goodbye"'
        )
        assert "Successfully" in result
        assert f.read_text() == 'she said "goodbye"'
