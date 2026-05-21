"""Tool wrappers — McpToolCall, McpResourceTool, McpPromptTool."""

from __future__ import annotations

import re
from typing import Any

from laffybot_agent_runtime.tools.base import Tool

# ── Name normalisation ───────────────────────────────────────────────────


_NAME_CLEAN_RE = re.compile(r"[^a-zA-Z0-9_-]")
_MULTI_UNDERSCORE_RE = re.compile(r"_+")
_MAX_TOOL_NAME_LENGTH = 64


def normalise_server_name(server_name: str) -> str:
    """Normalise a server name for use in tool name prefixes.

    * Replace ``[^a-zA-Z0-9_-]`` with ``_``
    * Collapse multiple underscores
    * Strip leading/trailing underscores
    """
    safe = _NAME_CLEAN_RE.sub("_", server_name)
    return _MULTI_UNDERSCORE_RE.sub("_", safe).strip("_")


def _normalise_tool_name(server_name: str, tool_name: str) -> str:
    """Normalise ``{server_name}_{tool_name}``.

    * Replace ``[^a-zA-Z0-9_-]`` with ``_``
    * Collapse multiple underscores
    * Truncate to 64 characters
    """
    safe_server = normalise_server_name(server_name)
    safe_tool = _NAME_CLEAN_RE.sub("_", tool_name)
    safe_tool = _MULTI_UNDERSCORE_RE.sub("_", safe_tool).strip("_")
    name = f"{safe_server}_{safe_tool}"
    if len(name) > _MAX_TOOL_NAME_LENGTH:
        name = name[:_MAX_TOOL_NAME_LENGTH]
    return name


# ── JSON Schema normalisation ────────────────────────────────────────────


def _normalise_input_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise a JSON Schema for tool input.

    * Missing ``properties`` → insert ``{"type": "object", "properties": {}}``
    * Nullable union ``["string", "null"]`` → ``{"type": "string", "nullable": true}``
    * Nullable ``anyOf/oneOf`` → extract non-null branches
    """
    if not schema:
        return {"type": "object", "properties": {}}

    result = dict(schema)

    # Remove ``$schema`` if present (not needed for tool calls)
    result.pop("$schema", None)

    if "properties" not in result:
        result["type"] = "object"
        result["properties"] = {}

    # Normalise top-level type if it's a union
    _normalise_type_field(result)

    # Walk properties
    for prop_name, prop_val in list(result.get("properties", {}).items()):
        if isinstance(prop_val, dict):
            _normalise_type_field(prop_val)
            # Handle anyOf/oneOf with null
            for key in ("anyOf", "oneOf"):
                variants = prop_val.get(key)
                if isinstance(variants, list):
                    non_null = [v for v in variants if not _is_null_schema(v)]
                    if non_null and len(non_null) < len(variants):
                        prop_val.pop(key, None)
                        if len(non_null) == 1:
                            merged = dict(non_null[0])
                            merged["nullable"] = True
                            for k, v in prop_val.items():
                                if k not in ("anyOf", "oneOf"):
                                    merged[k] = v
                            result["properties"][prop_name] = merged
                        else:
                            # Keep as anyOf/oneOf without null branch
                            prop_val[key] = non_null
                            prop_val["nullable"] = True

    return result


def _is_null_schema(s: Any) -> bool:
    return isinstance(s, dict) and s.get("type") in (None, "null")


def _normalise_type_field(schema: dict[str, Any]) -> None:
    typ = schema.get("type")
    if isinstance(typ, list):
        non_null = [t for t in typ if t != "null"]
        if non_null and len(non_null) < len(typ):
            schema["type"] = non_null[0] if len(non_null) == 1 else non_null
            schema["nullable"] = True
        elif non_null:
            schema["type"] = non_null[0] if len(non_null) == 1 else non_null


# ── Content processing ───────────────────────────────────────────────────


def _content_to_text(content: list[dict[str, Any]]) -> str:
    """Convert MCP CallToolResult content blocks to a plain string."""
    parts: list[str] = []
    for block in content:
        block_type = block.get("type", "")
        if block_type == "text":
            parts.append(block.get("text", ""))
        elif block_type == "image":
            mime = block.get("mimeType", "unknown")
            data = block.get("data", "")
            parts.append(f"[Image: {mime}, {data[:64]}...]")
        elif block_type == "resource":
            uri = block.get("resource", {}).get("uri", "unknown")
            parts.append(f"[Resource: {uri}]")
        else:
            parts.append(str(block))
    return "\n".join(parts)


# ── ToolFilter ───────────────────────────────────────────────────────────


class ToolFilter:
    """Allow-list / deny-list filter for MCP tool names.

    Applied at both startup and call-time (double-check).
    """

    def __init__(
        self,
        enabled_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
    ) -> None:
        self._enabled = enabled_tools or ["*"]
        self._disabled = set(disabled_tools or [])

    def allows(self, name: str) -> bool:
        """Check whether *name* is allowed by the filter."""
        if name in self._disabled:
            return False
        if "*" in self._enabled:
            return True
        return name in self._enabled

    def apply(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter a list of raw tool dicts by their ``name`` field."""
        return [t for t in tools if self.allows(t.get("name", ""))]


# ── McpToolCall ──────────────────────────────────────────────────────────


class McpToolCall(Tool):
    """Wraps a remote MCP Tool as an agent Tool."""

    kind = "mcp"

    def __init__(
        self,
        server_name: str,
        tool_def: dict[str, Any],
        manager: Any,  # McpServerManager (forward ref)
    ) -> None:
        self._server_name = server_name
        self._tool_def = tool_def
        self._manager = manager
        self._raw_name: str = tool_def.get("name", "")
        raw_desc = tool_def.get("description", "")
        raw_schema = tool_def.get("inputSchema") or tool_def.get("input_schema", {})
        self._schema = _normalise_input_schema(raw_schema)
        self._desc = raw_desc or ""
        self._is_read_only = (
            tool_def.get("readOnlyHint", False)
            or tool_def.get("destructiveHint", False) is False
        )

    @property
    def name(self) -> str:
        return _normalise_tool_name(self._server_name, self._raw_name)

    @property
    def description(self) -> str:
        return self._desc

    @property
    def parameters(self) -> dict[str, Any]:
        return self._schema

    @property
    def read_only(self) -> bool:
        return self._is_read_only

    async def execute(self, **kwargs: Any) -> str:
        result = await self._manager.call_tool(
            self._server_name, self._raw_name, kwargs
        )
        content = result.get("content", [])
        text = _content_to_text(content)
        if result.get("isError", False):
            text = f"Error: {text}"
        return text


# ── McpResourceTool ──────────────────────────────────────────────────────


class McpResourceTool(Tool):
    """Wraps reading an MCP Resource as a read-only Tool."""

    kind = "mcp"

    def __init__(
        self,
        server_name: str,
        resource_def: dict[str, Any],
        manager: Any,
    ) -> None:
        self._server_name = server_name
        self._resource_def = resource_def
        self._manager = manager
        uri = resource_def.get("uri", "")
        self._uri = uri
        raw_desc = resource_def.get("description", "") or f"Read resource {uri}"
        self._desc = raw_desc

    @property
    def name(self) -> str:
        raw_name = self._resource_def.get("name", self._uri)
        return _normalise_tool_name(self._server_name, f"resource_{raw_name}")

    @property
    def description(self) -> str:
        return self._desc

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        contents = await self._manager.read_resource(self._server_name, self._uri)
        parts: list[str] = []
        for c in contents:
            if c.get("type") == "text" or "text" in c:
                parts.append(c.get("text", ""))
            elif "blob" in c:
                parts.append(
                    f"[Blob: {c.get('mimeType', 'unknown')}, {c['blob'][:64]}...]"
                )
            else:
                parts.append(str(c))
        return "\n".join(parts)


# ── McpPromptTool ────────────────────────────────────────────────────────


class McpPromptTool(Tool):
    """Wraps getting an MCP Prompt as a read-only Tool."""

    kind = "mcp"

    def __init__(
        self,
        server_name: str,
        prompt_def: dict[str, Any],
        manager: Any,
    ) -> None:
        self._server_name = server_name
        self._prompt_def = prompt_def
        self._manager = manager
        self._prompt_name: str = prompt_def.get("name", "")
        raw_desc = (
            prompt_def.get("description", "") or f"Get prompt {self._prompt_name}"
        )
        self._desc = raw_desc

    @property
    def name(self) -> str:
        return _normalise_tool_name(self._server_name, f"prompt_{self._prompt_name}")

    @property
    def description(self) -> str:
        return self._desc

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        result = await self._manager.get_prompt(
            self._server_name, self._prompt_name, kwargs
        )
        messages = result.get("messages", [])
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", {})
            if isinstance(content, dict) and content.get("type") == "text":
                parts.append(f"[{role}]\n{content['text']}")
            else:
                parts.append(f"[{role}]\n{content}")
        return "\n\n".join(parts)
