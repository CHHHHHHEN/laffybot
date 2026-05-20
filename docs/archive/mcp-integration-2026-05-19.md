---
archived_from: plan.md
archived_at: 2026-05-19
implements: MCP Protocol Integration
status: implemented
summary: |
  MCP (Model Context Protocol) support for laffybot — connects external tool
  servers (stdio, SSE, Streamable HTTP) via JSON-RPC 2.0, registers their
  tools/resources/prompts as agent Tools, and provides full CRUD management
  through the UI.
---

# MCP Integration Implementation Record

## Core files changed (grouped by module)

### MCP Client Module (`laffybot/agent/tools/mcp/`)
- **`__init__.py`** — module init
- **`client.py`** — JSON-RPC 2.0 McpClient (initialize, ping, list_tools, call_tool, list_resources, read_resource, list_prompts, get_prompt, set_logging_level, close); request ID strict increment; asyncio.Lock serialisation
- **`transports.py`** — Transport ABC + StdioTransport (subprocess, env filtering, stderr redirect, Windows compat, SIGTERM→SIGKILL cleanup) + SseTransport (httpx GET + SSE line protocol parsing, endpoint discovery, HTTP POST) + StreamableHttpTransport (httpx POST + SSE response)
- **`wrappers.py`** — ToolFilter (allow/deny list, double-check), McpToolCall, McpResourceTool, McpPromptTool (kind="mcp"), JSON Schema normalisation (nullable union, oneOf/anyOf null extraction, missing properties), name normalisation with 64-char truncation, ContentBlock→text conversion
- **`manager.py`** — AsyncManagedClient (state machine: created→starting→ready|failed→disconnected), McpServerManager (parallel start with gather, per-server routing, list_all_tools/resources/prompts, get_status, hot_swap with create-before-destroy, shutdown), create_transport factory

### Config Storage (`laffybot/session/`)
- **`mcp_server_store.py`** — McpServerStore ABC + SQLiteMcpServerStore (mcp_servers table, encrypted env/headers via laffybot.crypto, auto-detect transport type, get_enabled_server_configs with decryption), ServerNotFoundError, ServerNameConflictError

### API Layer (`laffybot/api/`)
- **`schemas.py`** — MCPServerCreateRequest, MCPServerUpdateRequest, MCPServerResponse, MCPServerTestResponse
- **`mcp_routes.py`** — Full CRUD + enable/disable/toggle/test/reconnect for `/api/v1/mcp/servers`, hot_swap on update
- **`routes.py`** — mcp_router registration
- **`dependencies.py`** — build_mcp_server_store, get_mcp_server_store, get_mcp_manager factory
- **`app.py`** — MCP lifecycle (background startup, shutdown cleanup, error handlers for ServerNotFoundError, ServerNameConflictError)

### ToolRegistry (`laffybot/agent/tools/`)
- **`registry.py`** — added `unregister_group(prefix)` method

### Frontend (`ui/src/`)
- **`lib/api.ts`** — MCP API functions (list/create/update/delete/enable/disable/toggle/test/reconnect)
- **`hooks/use-mcp-servers.ts`** — TanStack Query hooks
- **`pages/McpSettingsPage.tsx`** — Server list with status, toggle, test, delete, edit
- **`components/settings/McpServerForm.tsx`** — Create/edit form dialog with transport type, command/URL, env vars, headers, timeouts
- **`App.tsx`** — Route for `/settings/mcp`
- **`pages/SettingsPage.tsx`** — Tab "MCP 服务" added

## Design doc paths referenced during planning
- `docs/provider-model-design.md` (Provider CRUD pattern)
- `third-party/codex/codex-rs/` (Rust MCP architecture: McpConnectionManager, AsyncManagedClient, ToolFilter, hot_swap)
- `third-party/nanobot/nanobot/agent/tools/mcp.py` (Python MCP wrapper pattern)
- `third-party/hermes-agent/tools/mcp_tool.py` (env filtering, stderr redirect)

## Outstanding items / known gaps
- **Env/headers for startup configs**: env and headers fields are decrypted when building configs via `get_enabled_server_configs()`. However, during lifespan startup these are only loaded once; any subsequent update requires a hot_swap cycle.
- **No automatic reconnection**: Servers that disconnect are marked `disconnected` and require manual reconnect or next app restart.
- **No OAuth 2.1**: Explicitly excluded from scope.
- **No Sampling (server→LLM)**: Explicitly excluded.
- **No dynamic tool discovery**: `tools/list_changed` notifications not handled.
- **No resource/prompt subscriptions**: Explicitly excluded.
- **No concurrency in McpClient**: All requests serialised via asyncio.Lock per JSON-RPC protocol requirement. Long `call_tool` blocks `ping`.

### Changes since initial implementation
- **2026-05-20 — MCP disconnect tool cleanup**: Tools registered by a disconnected MCP server are now automatically cleaned up from ToolRegistry. Three trigger paths cover all disconnect scenarios (transport callback, call_tool exception, shutdown). See `docs/archive/mcp-disconnect-tool-cleanup-2026-05-20.md`.
