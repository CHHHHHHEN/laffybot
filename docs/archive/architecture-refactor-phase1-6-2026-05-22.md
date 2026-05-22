# Refactoring Plan: Full ARCHITECTURE.md Alignment

> 严格对照 `ARCHITECTURE.md` 全面重构。不设后向兼容。Break things and make them right.

## 架构违规清单

### P0 — 违反单向依赖 (必须立刻修复)

| # | 违规 | 位置 | 后果 |
|---|------|------|------|
| 01 | API 层直接 import Store 具体实现 | `routes/providers.py:21` — `from laffybot.db.provider_store import ProviderRow, ProviderStore` | ARCHITECTURE.md 第 310 行明确禁止 |
| 02 | API 层直接 import Store 具体实现 | `routes/mcp.py:29` — `from laffybot.db.mcp_server_store import McpServerStore, ServerNameConflictError` | 同上 |
| 03 | API 层直接 import Store 具体实现 | `routes/sessions.py:50-53` — 4 个 Store 直接导入 | 同上 |
| 04 | API 层直接 import Store 具体实现 | `routes/health.py:9` — `from laffybot.db.session_store import SessionStore` | 同上 |
| 05 | API 层直接 import Store 具体实现 | `routes/skills.py:20` — `from laffybot.db.app_setting_store import AppSettingStore` | 同上 |
| 06 | API 层直接 import 运行时类型 | `routes/sessions.py:11` — `from laffybot_agent_runtime.events import SSEEvent` | API 层应只通过 SessionManager Protocol |
| 07 | API 层直接 import 运行时类型 | `routes/sessions.py:12` — `from laffybot_agent_runtime.heartbeat import HeartbeatManager` | 同上 |
| 08 | API 层直接 import 运行时类型 | `routes/providers.py:9` — `from laffybot_agent_runtime.providers.errors import ProviderConnectionError` | 同上 |
| 09 | API 层直接 import 运行时类型 | `routes/mcp.py:10-20` — MCP 类型批量导入 | 同上 |
| 10 | API 层直接 import 运行时类型 | `routes/tools.py:6` — `from laffybot_agent_runtime.tools.registry import ToolRegistry` | 同上 |
| 11 | API 层直接 import 运行时类型 | `routes/skills.py:6` — `from laffybot_agent_runtime.skills import SkillRegistry, SkillsLoader` | 同上 |
| 12 | API 层直接 import 运行时类型 | `app.py:14-25` — ProviderError, ToolError, 文件系统工具等 | 同上 |
| 13 | API 层 DI 返回具体类而非 Protocol | `dependencies.py:163` — `get_session_manager→DefaultSessionManager` | 应仅暴露 SessionManager(Protocol) |
| 14 | API 层 DI 直接 import 具体实现 | `dependencies.py:12-22` — 所有 Store 具体实现直接导入 | 组合根允许，但应用仅通过抽象暴露 |
| 15 | API 层持有业务逻辑 | `routes/sessions.py:99-123` — `render_skills_block` 和 `_serialize_*` 序列化 | 序列化应下移到服务层 DTO |
| 16 | API 层直接操作 DB (settings) | `routes/sessions.py:390-525` — settings 路由直接注入 AppSettingStore | 应通过 SessionManager |

### P1 — 架构定义偏离

| # | 违规 | 位置 | 后果 |
|---|------|------|------|
| 17 | 错误映射违反规范 | `app.py:188-193` — ToolError→500/400 而非 502 | ARCHITECTURE.md 要求 502 |
| 18 | 错误映射违反规范 | `app.py:181-185` — ProviderError→404/409/500 而非 502 | ARCHITECTURE.md 要求 502 |
| 19 | 重复的 ContextConfig | `agent-runtime/config.py` vs `service/context/types.py` | 运行时不应持有服务层类型 |
| 20 | 重复的 TitleGenerator | `agent-runtime/title_generator.py` vs `service/title_generator.py` | 同上 |
| 21 | MemoryManager Protocol 未实现 | `service/protocols.py:97-114` 定义 Protocol，但 `memory/manager.py` 无显式 implements | 接口契约不强制 |
| 22 | ProviderFactory 被其他层直接 import | `async_events.py:12` — 直接 import ProviderFactory 具体类 | 应仅通过 Protocol |
| 23 | SessionStateMachine.cancel() 空实现 | `state_machine.py:25` — `def cancel: pass` | 违反「并发与取消规则」 |

### P2 — 代码质量问题

| # | 问题 | 位置 |
|---|------|------|
| 24 | `dependencies.py` 模块 195 行——组合根过大 | 应拆分为按域分组 |
| 25 | `routes/sessions.py` 658 行——单文件过大 | 应按职责拆分：sessions, settings, memories |
| 26 | `app.py` 中直接 new ToolRegistry/文件系统工具 | 应通过 Builder 创建 |
| 27 | `session_manager.py` 中 `_build_messages` 直接调用 MemoryManager 具体类 | 应通过 MemoryManager Protocol |
| 28 | 观察性/health.py 中的 import `laffybot/__version__` | 基础设施依赖业务层版本号（小问题） |
| 29 | SSE 帧构建在 API 层 `_sse_frame()` | 应统一到运行时 SSEEvent.to_sse() |

---

## 重构阶段

### Phase 1: 基础设施层 — 统一数据库连接管理 (Day 1)

**目标**: 消除 6 个独立 Store 各自维护独立 `aiosqlite.Connection` 的问题

```
当前: SQLiteStore._db | SQLiteProviderStore._db | SQLiteMcpServerStore._db | ...
目标: DatabaseManager (单例连接池) → 所有 Store 共享同一 db_path
```

**变更**:
1. 新增 `laffybot/db/manager.py` — `DatabaseManager` 类
   - 管理单一 `aiosqlite.Connection`
   - 提供 `execute()`, `executescript()`, `commit()`, `close()`
   - 支持 `:memory:` 和文件路径
   - connection 懒初始化
2. 所有 `SQLite*Store` 构造函数改为接受 `DatabaseManager` 实例
3. 移除各 Store 的 `_ensure_db()`, 各自 schema 初始化改为由 `DatabaseManager` 统一执行
4. `dependencies.py` 中 `build_*` 函数改为共享同一个 `DatabaseManager`

### Phase 2: API 层 — 断连 Store 直接依赖 (Day 1-2)

**目标**: API 层所有路由不再直接 import 任何 `laffybot.db.*` 模块

**具体操作**:
1. `routes/providers.py`:
   - 创建 `service/provider_routes_service.py` 封装 Provider CRUD 逻辑
   - API 层通过 `SessionManager` Protocol 或新的 `ProviderManager` Protocol 访问
2. `routes/mcp.py`:
   - 创建 `service/mcp_routes_service.py` 封装 MCP 服务器 CRUD + 生命周期
   - API 层通过新 `McpManager` Protocol 访问
3. `routes/tools.py`:
   - 通过 `SessionManager` 暴露 `list_tools`, `enable_tool`, `disable_tool`
4. `routes/skills.py`:
   - 通过 `SessionManager` 暴露 skill 操作
5. `routes/sessions.py`:
   - settings 路由全部通过 `SessionManager` 访问
   - 删除所有 Store 的 DI 注入
6. `routes/health.py`:
   - `SessionStore` 依赖改为通过 `DatabaseManager` 的健康检查
7. 删除 `dependencies.py` 中不再需要的 `get_*` accessor（`get_provider_store`, `get_memory_store`, etc.）

### Phase 3: API 层 — 断连运行时类型直接依赖 (Day 2)

**目标**: API 层路由不再直接 import `laffybot_agent_runtime.*`

**具体操作**:
1. 创建 `api/sse_adapter.py` — 封装 SSE 帧构建逻辑
   - `format_sse_event(event: SSEEvent, event_id: str) -> str`
   - 这样 API 层只需 import 这个 adapter 而非运行时 events
2. 创建 `api/heartbeat_adapter.py` — 封装 HeartbeatManager
   - `SSEKeepAlive` 类
3. SSE 流中的错误事件类型使用 ARCHITECTURE.md 指定的格式：
   ```python
   # SSE error event:
   event: error
   data: {"type": "provider_error", "message": "...", "error_code": "...", "recoverable": true/false, "details": ...}
   ```
4. 删除 `routes/providers.py` 中直接创建 `AsyncOpenAI` client 的 test 逻辑
   - 改为通过 `ProviderFactory` Protocol + `BaseProvider.chat_completion`
5. MCP 测试路由改为通过服务层 `McpService` 调用

### Phase 4: 错误映射对齐 ARCHITECTURE.md (Day 2)

**目标**: 严格按 ARCHITECTURE.md 第 57-61 行映射

```
当前:
  SessionError → 409 (partial match)
  ProviderError → 404/409/500 (wrong — should be 502)
  ToolError → 400/500 (wrong — should be 502)
  未捕获 → 500 (match)

目标:
  SessionError → 409 Conflict
  ProviderError → 502 Bad Gateway
  ToolError → 502 Bad Gateway
  未捕获 → 500 Internal
```

SSE 流中错误事件格式按 ARCHITECTURE.md 第 63-74 行：
```python
{
  "type": "provider_error" | "tool_error" | "session_cancelled" | "internal_error",
  "message": string,
  "error_code": string,
  "recoverable": boolean,
  "details": object | null
}
```

### Phase 5: 重复代码清理 (Day 2-3)

**目标**: 消除重复的 ContextConfig 和 TitleGenerator

**具体操作**:
1. `packages/laffybot-agent-runtime/src/laffybot_agent_runtime/config.py`:
   - 删除整个文件。运行时不再持有 ContextConfig
2. 检查和修复运行时中对 `ContextConfig` 的所有引用（预期为 0）
3. `packages/laffybot-agent-runtime/src/laffybot_agent_runtime/title_generator.py`:
   - 删除整个文件。TitleGenerator 的唯一归属在服务层
4. 检查和修复运行时中对 `title_generator` 的所有引用（预期为 0）

### Phase 6: Protocol 契约强化 (Day 3)

**目标**: 所有跨层接口通过 Protocol 执行

**具体操作**:
1. `memory/manager.py` 添加 `MemoryManager` Protocol 的显式实现声明：
   ```python
   class MemoryManager:
       """Lifecycle container ..."""
       # 方法签名与 service/protocols.py 中 MemoryManager Protocol 一致
   ```
2. `service/provider_factory.py` 中 `DefaultProviderFactory` 显式实现 `ProviderFactory` Protocol
3. `dependencies.py` 中 `get_session_manager` 返回类型改为 `SessionManager` (Protocol)
4. 确保 `SessionManager` Protocol 覆盖所有 API 层需要的操作：
   - `list_tools`, `enable_tool`, `disable_tool`
   - `list_providers`, `create_provider`, `update_provider`, `delete_provider`, `test_provider`
   - `list_mcp_servers`, `create_mcp_server`, `update_mcp_server`, `delete_mcp_server`
   - `list_skills`, `set_skill_enabled`, `set_skills_path`
   - settings 操作（default-session-model, summary-model, extract-model, consolidation-model）
   - memory 操作

### Phase 7: 服务层 — 业务逻辑下沉 (Day 3-4)

**目标**: API 层的业务逻辑下移到服务层

**具体操作**:
1. `render_skills_block` 从 `api/dependencies.py` 移到 `service/skill_service.py`
2. 创建 `service/session_serializer.py` — 封装 `SessionInfo→dict` 序列化
3. `SessionManager.send_message()` 参数规范化：
   - 当前接受 `skills_block: str` — 改为服务层内部处理
4. 创建 `service/mcp_service.py`:
   - 封装 MCP 服务器 CRUD、启用/禁用、热交换、测试连接
   - 依赖：`McpServerStore`, `McpServerManager`
5. 创建 `service/provider_service.py`:
   - 封装 Provider CRUD、模型管理、连接测试
   - 依赖：`ProviderStore`, `ProviderFactory`
6. 创建 `service/settings_service.py`:
   - 封装所有 settings CRUD
   - 依赖：`AppSettingStore`, `ProviderStore`

### Phase 8: dto/ 层创建 — 跨层数据传输 (Day 4)

**目标**: 建立稳定的跨层 DTO

**具体操作**:
1. 创建 `laffybot/dto/` 包
   - `session_dto.py` — `SessionDTO`, `SessionDetailDTO`, `MessageDTO`
   - `provider_dto.py` — `ProviderDTO`, `ModelDTO`, `TestResultDTO`
   - `mcp_dto.py` — `MCPServerDTO`
   - `tool_dto.py` — `ToolDTO`
   - `skill_dto.py` — `SkillDTO`
   - `settings_dto.py` — `SettingsDTO`
   - `memory_dto.py` — `MemoryDTO`, `ConsolidatedMemoryDTO`
2. API `schemas.py` 中的 Pydantic 模型作为 HTTP 边界，DTO 作为服务层边界
   - schemas 从 DTO 继承或转换
3. `api/schemas.py` 不再 import 任何 `laffybot.db.*` 或 `laffybot_agent_runtime.*`

### Phase 9: 并发与取消 — SessionStateMachine 完整实现 (Day 4)

**目标**: 实现 `SessionStateMachine.cancel()` 并通过 `CancellationToken` 传播

**具体操作**:
1. `state_machine.py`:
   - `cancel()` 方法：
     - 通过 `lock_port` 获取锁
     - 设置 `CancellationToken`
     - 释放锁
   - 状态机内部管理 `session_id→CancellationToken` 映射
2. 从 `session_manager.py` 中移除 `self._active_tokens` 字典
   - 改由 `SessionStateMachine` 统一管理 token
3. 看门狗逻辑中通过状态机获取 token

### Phase 10: 组合根重构 (Day 4-5)

**目标**: `api/app.py` 和 `api/dependencies.py` 重构

**具体操作**:
1. `dependencies.py` 拆分为：
   - `dependencies/db.py` — 数据库相关
   - `dependencies/services.py` — 服务层相关
   - `dependencies/runtime.py` — 运行时相关
2. `app.py` 中组件创建流程规范化：
   - 使用 `create_components(config) -> AppComponents` 返回所有依赖
   - 不再在 `create_app` 函数内部直接 new 对象
3. `AppComponents` dataclass 包含所有应用组件

---

## 架构验证清单 (验证条件)

重构完成后，以下断言必须全部为 true:

### 层间依赖
- [ ] `laffybot.api` 不 import 任何 `laffybot.db.*` (除了 `dependencies.py` 组合根)
- [ ] `laffybot.api` 不 import 任何 `laffybot_agent_runtime.*` 除了 events 和 providers 的极少数类型（通过 adapter）
- [ ] `laffybot.api.routes.*` 不 import 任何 `laffybot.db.*`
- [ ] `laffybot.api.routes.*` 不 import 任何 `laffybot_agent_runtime.*`
- [ ] `laffybot.service` 不 import `laffybot.api.*`
- [ ] `laffybot.db` 不 import `laffybot.service.*` (错误类型除外)
- [ ] `laffybot_agent_runtime` 不 import 任何 `laffybot.*`

### 接口边界
- [ ] API 路由仅通过 `SessionManager`(Protocol) 与服务层通信
- [ ] 所有 `get_*` DI accessor 返回 Protocol 类型而非具体类
- [ ] `ProviderFactory` 仅通过 Protocol 使用
- [ ] `MemoryManager` 显式实现 Protocol
- [ ] `DefaultSessionManager` 显式实现 `SessionManager` Protocol

### 错误映射
- [ ] `SessionError` → 409 Conflict (SSE: `session_error` / `session_cancelled`)
- [ ] `ProviderError` → 502 Bad Gateway (SSE: `provider_error`)
- [ ] `ToolError` → 502 Bad Gateway (SSE: `tool_error`)
- [ ] 未捕获异常 → 500 Internal (SSE: `internal_error`)
- [ ] SSE 流中 `recoverable` 字段正确设置

### 重复代码
- [ ] 运行时中没有 `ContextConfig`
- [ ] 运行时中没有 `TitleGenerator`
- [ ] 没有重复的 DTO/数据类

### 并发控制
- [ ] `SessionStateMachine.cancel()` 完整实现
- [ ] `CancellationToken` 仅由状态机统一管理
- [ ] 看门狗通过状态机获取 token

---

## 回滚策略

由于不设后向兼容，每个 Phase 完成后：
1. 运行 `uv run ruff check . && uv run ruff format --check . && uv run mypy laffybot/`
2. 运行 `uv run ruff check packages/laffybot-agent-runtime/ && uv run ruff format --check packages/laffybot-agent-runtime/ && uv run mypy packages/laffybot-agent-runtime/src/laffybot_agent_runtime/`
3. 运行 `pnpm run typecheck` (UI)
4. 运行 `uv run pytest` 确保现有测试通过
5. 手动测试 `python dev.py` 启动 + 发送消息

如果 Phase N 导致不可修复的问题，git revert 该 Phase 并跳过重做。
