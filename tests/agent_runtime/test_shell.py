# mypy: disable-error-code="untyped-decorator"
"""Tests for ExecTool shell execution tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from laffybot.agent_runtime.tools.shell import ExecTool


class TestBasicExecution:
    @pytest.mark.asyncio
    async def test_echo(self) -> None:
        tool = ExecTool()
        result = await tool.execute(command='echo "hello world"')
        assert "hello world" in result
        assert "Exit code: 0" in result

    @pytest.mark.asyncio
    async def test_exit_code_displayed(self) -> None:
        tool = ExecTool()
        result = await tool.execute(command="true")
        assert "Exit code: 0" in result

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self) -> None:
        tool = ExecTool()
        result = await tool.execute(command="false")
        assert "Exit code: 1" in result

    @pytest.mark.asyncio
    async def test_stderr_captured(self) -> None:
        tool = ExecTool()
        result = await tool.execute(command='echo "err" >&2')
        assert "STDERR" in result
        assert "err" in result


class TestTimeout:
    @pytest.mark.asyncio
    async def test_command_timeout(self) -> None:
        tool = ExecTool(timeout=60)
        result = await tool.execute(command="sleep 10", timeout=1)
        assert "timed out" in result.lower()


class TestOutputTruncation:
    @pytest.mark.asyncio
    async def test_long_output_truncated(self) -> None:
        tool = ExecTool()
        result = await tool.execute(command="python3 -c \"print('x' * 20000)\"")
        assert "truncated" in result.lower()


class TestGuardCommand:
    """_guard_command — tested directly per safety convention."""

    def test_denies_rm_rf(self) -> None:
        tool = ExecTool()
        result = tool._guard_command("rm -rf /", "/tmp")
        assert result is not None
        assert "blocked" in result.lower()

    def test_denies_shutdown(self) -> None:
        tool = ExecTool()
        result = tool._guard_command("shutdown -h now", "/tmp")
        assert result is not None

    def test_denies_mkfs(self) -> None:
        tool = ExecTool()
        result = tool._guard_command("mkfs.ext4 /dev/sda1", "/tmp")
        assert result is not None

    def test_allows_benign_command(self) -> None:
        tool = ExecTool()
        result = tool._guard_command("ls -la", "/tmp")
        assert result is None

    def test_allows_with_allow_pattern(self) -> None:
        tool = ExecTool(allow_patterns=[r"ls"])
        result = tool._guard_command("ls -la", "/tmp")
        assert result is None

    def test_blocks_non_allowed_when_allowlist_active(self) -> None:
        tool = ExecTool(allow_patterns=[r"git"])
        result = tool._guard_command("ls -la", "/tmp")
        assert result is not None

    def test_path_traversal_detected(self) -> None:
        tool = ExecTool(restrict_to_workspace=True, working_dir="/workspace")
        result = tool._guard_command("cat ../secret.txt", "/workspace")
        assert result is not None
        assert "traversal" in result.lower()

    def test_path_outside_workspace_blocked(self) -> None:
        tool = ExecTool(restrict_to_workspace=True, working_dir="/workspace")
        result = tool._guard_command("cat /etc/passwd", "/workspace")
        # /etc/passwd is absolute and outside /workspace
        assert result is not None

    def test_benign_device_path_allowed(self) -> None:
        tool = ExecTool(restrict_to_workspace=True, working_dir="/workspace")
        result = tool._guard_command("cat /dev/null", "/workspace")
        assert result is None  # benign device paths are allowed


class TestEnvironment:
    @pytest.mark.asyncio
    async def test_build_env_linux_has_home(self) -> None:
        tool = ExecTool()
        env = tool._build_env()
        assert "HOME" in env
        assert "PATH" not in env  # Linux env only has whitelisted keys

    def test_allowed_env_keys_included(self) -> None:
        tool = ExecTool(allowed_env_keys=["USER", "SHELL"])
        env = tool._build_env()
        if "USER" in __import__("os").environ:
            assert "USER" in env


class TestWorkingDirectory:
    @pytest.mark.asyncio
    async def test_custom_working_dir(self, tmp_path: Path) -> None:
        tool = ExecTool(working_dir=str(tmp_path))
        result = await tool.execute(command="pwd")
        assert str(tmp_path) in result


class TestExtractAbsolutePaths:
    def test_extracts_posix_paths(self) -> None:
        paths = ExecTool._extract_absolute_paths("cat /etc/passwd")
        assert "/etc/passwd" in paths

    def test_ignores_relative_paths(self) -> None:
        paths = ExecTool._extract_absolute_paths("cat file.txt")
        assert "/file.txt" not in paths
        assert not any(p.startswith("/file.txt") for p in paths)

    def test_extracts_home_paths(self) -> None:
        paths = ExecTool._extract_absolute_paths("cat ~/.bashrc")
        assert any("~" in p for p in paths)
