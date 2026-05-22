"""跨层 Protocol 接口 — API → 后端服务层、后端服务层 → 基础设施层的契约。

这些 Protocol 是架构的核心边界接口：
- API 层仅通过 SessionManager(Protocol) 与后端服务层通信
- 后端服务层仅通过 Store/EventBus 等端口与基础设施层通信
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Protocol

from laffybot_agent_runtime.events import SSEEvent
from laffybot_agent_runtime.providers.base import BaseProvider

from laffybot.db.provider_store import ProviderConfig
from laffybot.service.models import SessionInfo, SessionStatus


class SessionManager(Protocol):
    """API 层可见的唯一后端服务层入口。

    API 层只通过此 Protocol 调用；不直接访问 Store、Provider 或 Agent Runtime。
    """

    # ── Health / readiness ───────────────────────────────────────────────

    async def get_health_status(self) -> dict[str, object]: ...

    async def get_readiness_status(self) -> dict[str, object]: ...

    # ── Session lifecycle ────────────────────────────────────────────────

    async def create_session(
        self,
        max_iterations: int = 50,
        provider_id: str | None = None,
        model_name: str | None = None,
    ) -> SessionInfo: ...

    async def get_session_info(self, session_id: str) -> SessionInfo: ...

    async def list_sessions(
        self,
        status: SessionStatus | None = None,
        archived: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by_asc: bool = False,
    ) -> tuple[list[SessionInfo], int]: ...

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def archive_session(self, session_id: str) -> SessionInfo: ...

    async def unarchive_session(self, session_id: str) -> SessionInfo: ...

    async def cancel_request(
        self, session_id: str, reason: str | None = None
    ) -> str: ...

    async def update_session_model(
        self,
        session_id: str,
        provider_id: str,
        model_name: str,
    ) -> SessionInfo: ...

    async def update_session_title(self, session_id: str, title: str) -> bool: ...

    async def force_reset_stuck_busy(
        self, session_id: str, reason: str = "Session reset by stream cleanup"
    ) -> None: ...

    def send_message(
        self,
        session_id: str,
        content: str,
        skills_block: str = "",
    ) -> AsyncGenerator[SSEEvent, None]: ...

    # ── Provider CRUD ───────────────────────────────────────────────────

    async def list_providers(self) -> list[dict[str, Any]]: ...

    async def create_provider(
        self,
        name: str,
        base_url: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def get_provider(self, provider_id: str) -> dict[str, Any]: ...

    async def update_provider(
        self,
        provider_id: str,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def delete_provider(self, provider_id: str) -> None: ...

    async def list_models(self, provider_id: str) -> list[dict[str, Any]]: ...

    async def add_model(self, provider_id: str, name: str) -> dict[str, Any]: ...

    async def delete_model(self, model_id: str) -> None: ...

    async def test_provider(self, provider_id: str) -> dict[str, Any]: ...

    # ── MCP Server CRUD ─────────────────────────────────────────────────

    async def list_mcp_servers(self) -> list[dict[str, Any]]: ...

    async def create_mcp_server(
        self,
        name: str,
        transport_type: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        tool_timeout: int = 30,
        enabled_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
        startup_timeout: int = 30,
        enabled: bool = False,
    ) -> dict[str, Any]: ...

    async def get_mcp_server(self, server_id: str) -> dict[str, Any]: ...

    async def update_mcp_server(
        self,
        server_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def delete_mcp_server(self, server_id: str) -> None: ...

    async def enable_mcp_server(self, server_id: str) -> dict[str, Any]: ...

    async def disable_mcp_server(self, server_id: str) -> dict[str, Any]: ...

    async def toggle_mcp_server(self, server_id: str) -> dict[str, Any]: ...

    async def reconnect_mcp_server(self, server_id: str) -> dict[str, Any]: ...

    async def test_mcp_server(self, server_id: str) -> dict[str, Any]: ...

    # ── Tool management ─────────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]: ...

    async def enable_tool(self, name: str) -> dict[str, Any]: ...

    async def disable_tool(self, name: str) -> dict[str, Any]: ...

    # ── Skill management ────────────────────────────────────────────────

    async def get_skills_path(self) -> str | None: ...

    async def set_skills_path(self, path: str) -> list[dict[str, Any]]: ...

    async def list_skills(self) -> list[dict[str, Any]]: ...

    async def set_skill_enabled(self, name: str, enabled: bool) -> None: ...

    # ── Settings ────────────────────────────────────────────────────────

    async def get_system_prompt(self, _session_id: str = "") -> str | None: ...

    async def set_system_prompt(self, _session_id: str, system_prompt: str) -> None: ...

    async def get_default_session_config(self) -> dict[str, str] | None: ...

    async def set_default_session_config(
        self, provider_id: str, model_name: str
    ) -> dict[str, str]: ...

    async def delete_default_session_config(self) -> None: ...

    async def get_summary_model(self) -> dict[str, str] | None: ...

    async def set_summary_model(
        self, provider_id: str, model_name: str
    ) -> dict[str, str]: ...

    async def delete_summary_model(self) -> None: ...

    async def get_extract_model(self) -> dict[str, str] | None: ...

    async def set_extract_model(
        self, provider_id: str, model_name: str
    ) -> dict[str, str]: ...

    async def delete_extract_model(self) -> None: ...

    async def get_consolidation_model(self) -> dict[str, str] | None: ...

    async def set_consolidation_model(
        self, provider_id: str, model_name: str
    ) -> dict[str, str]: ...

    async def delete_consolidation_model(self) -> None: ...

    # ── Memory ──────────────────────────────────────────────────────────

    async def list_memories(
        self, limit: int = 20, offset: int = 0, search: str | None = None
    ) -> dict[str, Any]: ...

    async def get_memory(self, memory_id: str) -> dict[str, Any] | None: ...

    async def get_memory_source(self, memory_id: str) -> dict[str, Any] | None: ...

    async def delete_memory(self, memory_id: str) -> None: ...

    async def get_consolidated_memory(
        self, _session_id: str = ""
    ) -> dict[str, Any] | None: ...

    async def trigger_consolidation(self, _session_id: str = "") -> bool: ...


class ProviderFactory(Protocol):
    """后端服务层内部端口: Provider 选择与装配。"""

    async def create_provider(self, config: ProviderConfig) -> BaseProvider: ...


class MemoryManager(Protocol):
    """后端服务层内部端口: 记忆管理。"""

    async def get_memories_for_injection(
        self, top_n: int, max_tokens: int
    ) -> list[dict[str, Any]]: ...

    async def get_injection_content(
        self, max_tokens: int
    ) -> list[dict[str, Any]] | None: ...

    async def extract(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        provider: BaseProvider,
        model: str,
    ) -> str | None: ...
