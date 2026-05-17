---
archived_from: plan.md
archived_at: 2026-05-17
implements: Multiple design docs (see below)
status: implemented
summary: |
  Full-cycle architecture audit fix across 7 phases: layer violation fixes,
  dependency decoupling, session robustness, agent runner fixes, config
  enhancement, dead code cleanup, route split, frontend fixes, and core tests.
---

# 架构审计修复计划 — 实施记录

## Implementation Record

### Core files changed

#### `laffybot/session/`
- `manager.py` — TOCTOU fix (P2.2), lock scope reduction (P2.3), background task management + shutdown() (P2.4)
- `interfaces.py` — EventPublisher protocol (P1.1)

#### `laffybot/providers/`
- `factory.py` — ProviderFactory interface + DefaultProviderFactory (P1.2)
- `types.py` — LLMResponse split into SuccessLLMResponse | ErrorLLMResponse (P1.3)
- `openai.py` — Role alternation raise (P3.4), _parse_response merge (P3.5)

#### `laffybot/api/`
- `routes.py` → split into `session_routes.py`, `provider_routes.py`, `tool_routes.py`, `health_routes.py` (P5.4)
- `routes.py` — now a 14-line aggregation module
- `app.py` — shutdown() wired into lifespan (P2.4-followup)
- `dependencies.py` — DI wiring for EventPublisher, ProviderFactory (P1.1, P1.2)
- `errors.py` — map_provider_error signature simplified (P5.3)
- `event_bus.py` — EventPublisher protocol adaptation

#### `laffybot/agent/`
- `runner.py` — Empty response threshold (P3.1), Queue timeout (P3.2)
- `heartbeat.py` — HeartbeatManager used in event_stream + _stream_session_events (P5.1)
- `tools/base.py` — Added `kind: Literal["builtin", "mcp"]` field (P5.5)
- `tools/registry.py` — get_definitions uses `tool.kind` instead of `name.startswith("mcp_")` (P5.5)
- `tools/registry.py` — assert → ToolNotFoundError (P3.3)
- `tools/file_state.py` — Renamed `nanobot_file_states` → `laffybot_file_states` (P5.2)
- `tools/shell.py` — Renamed `NANOBOT_PATH_APPEND` → `LAFFYBOT_PATH_APPEND` (P5.2)

#### `laffybot/config.py`
- ApiConfig inherits BaseSettings with LAFFYBOT_ env prefix (P4.1)
- from_json() error handling (P4.2)

#### `pyproject.toml`
- requires-python lowered to >=3.12 (P4.4)
- mypy python_version → 3.12
- uv.lock generated (P4.3)

#### `ui/`
- `src/pages/ChatPage.tsx` — finally block for SSE cleanup (P6.1), boundaryToolCallCounts reset (P6.2), AbortController in useEffect (P6.3)
- `src/lib/api.ts` — getHistory signal param (P6.3)
- `package.json` — devtools moved to devDependencies (P6.4)
- `src/lib/api.ts` — header spread fixed (P1.4)

#### `tests/`
- `providers/test_types.py` — 9 tests for LLMResponse types
- `agent/test_cancellation.py` — 8 tests for CancellationToken
- `agent/test_registry.py` — 11 tests for ToolRegistry
- `session/test_store.py` — 18 tests for SQLiteStore CRUD + optimistic locking

### Design docs referenced
- `docs/session-manager-design.md`
- `docs/session-manager-sqlite-impl.md`
- `docs/heartbeat-design.md`
- `docs/agent-runner-streaming-design.md`
- `docs/context-builder-design.md`
- `docs/api.md`
- `docs/ui/ui-api-interface.md`

### Outstanding items / known gaps
1. **EventBus subscriber access pattern**: `_lock` / `_subscribers` still accessed directly in `event_stream` (row 4 of 废弃说明) — deferred to future phase
2. **SessionModelUpdateRequest missing model_id**: Per the plan's Note 1, `SessionModelUpdateRequest` uses `model_name` instead of `model_id`; schema refinement deferred
3. **shutdown() wiring done**: P2.4-followup now completed (P2.4-followup item in checklist)
4. **docs/api.md stale**: Provider endpoint docs still reference old `providers/active` global selection pattern and use `model` field in examples — pre-existing mismatch from earlier phases
