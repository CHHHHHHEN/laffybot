"""Tests for ToolRegistry."""

import pytest

from laffybot.agent.tools.base import Tool
from laffybot.agent.tools.errors import ToolError
from laffybot.agent.tools.registry import ToolRegistry


class _TestTool(Tool):
    def __init__(self, name: str = "test_tool", desc: str = "A test tool") -> None:
        self._name = name
        self._desc = desc

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._desc

    async def execute(self, **kwargs: str) -> str:
        return f"executed {self._name} with {kwargs}"


class _MCPTestTool(Tool):
    kind = "mcp"

    def __init__(self, name: str = "mcp_fs_list", desc: str = "MCP test tool") -> None:
        self._name = name
        self._desc = desc

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._desc

    async def execute(self, **kwargs: str) -> str:
        return f"mcp executed {self._name}"


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


def test_register_and_get(registry: ToolRegistry) -> None:
    tool = _TestTool()
    registry.register(tool)
    assert registry.get("test_tool") is tool
    assert registry.has("test_tool")


def test_register_twice_overwrites(registry: ToolRegistry) -> None:
    a = _TestTool(name="same")
    b = _TestTool(name="same")
    registry.register(a)
    registry.register(b)
    assert registry.get("same") is b


def test_unregister(registry: ToolRegistry) -> None:
    tool = _TestTool()
    registry.register(tool)
    registry.unregister("test_tool")
    assert not registry.has("test_tool")
    assert registry.get("test_tool") is None


def test_disable(registry: ToolRegistry) -> None:
    registry.register(_TestTool())
    registry.disable("test_tool")
    assert not registry.is_enabled("test_tool")


def test_disable_unknown_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="not found"):
        registry.disable("nonexistent")


def test_enable(registry: ToolRegistry) -> None:
    registry.register(_TestTool())
    registry.disable("test_tool")
    registry.enable("test_tool")
    assert registry.is_enabled("test_tool")


def test_get_definitions_excludes_disabled(registry: ToolRegistry) -> None:
    registry.register(_TestTool(name="tool_a"))
    registry.register(_TestTool(name="tool_b"))
    registry.disable("tool_a")
    names = [registry._schema_name(s) for s in registry.get_definitions()]
    assert "tool_b" in names
    assert "tool_a" not in names


def test_get_definitions_orders_builtins_then_mcp(registry: ToolRegistry) -> None:
    registry.register(_TestTool(name="builtin_b"))
    registry.register(_TestTool(name="builtin_a"))
    registry.register(_MCPTestTool(name="mcp_zzz"))
    registry.register(_MCPTestTool(name="mcp_aaa"))
    names = [registry._schema_name(s) for s in registry.get_definitions()]
    assert names == ["builtin_a", "builtin_b", "mcp_aaa", "mcp_zzz"]


async def test_execute_success(registry: ToolRegistry) -> None:
    registry.register(_TestTool())
    result = await registry.execute("test_tool", {"arg": "val"})
    assert result == "executed test_tool with {'arg': 'val'}"


async def test_execute_unknown_tool(registry: ToolRegistry) -> None:
    result = await registry.execute("nonexistent", {})
    assert isinstance(result, str)
    assert "not found" in result


def test_tool_names(registry: ToolRegistry) -> None:
    registry.register(_TestTool(name="a"))
    registry.register(_TestTool(name="b"))
    assert set(registry.tool_names) == {"a", "b"}


def test_len(registry: ToolRegistry) -> None:
    registry.register(_TestTool(name="a"))
    registry.register(_TestTool(name="b"))
    assert len(registry) == 2


def test_contains(registry: ToolRegistry) -> None:
    registry.register(_TestTool(name="present"))
    assert "present" in registry
    assert "missing" not in registry
