# 架构审计修复计划

**日期**: 2026-05-17 | **来源**: 全量架构审计（后端 `laffybot/` + 前端 `ui/`）

---

## 一、修复目标

1. 消除层架构违规和循环依赖风险
2. 解除 SessionManager 与 OpenAIProvider 的硬编码耦合
3. 修复 `LLMResponse` 成功/错误状态合并的设计缺陷
4. 修复前端 API 客户端 header 展开 bug
5. 解决 session 层竞争条件与资源泄漏
6. 消除死代码和旧项目名称残留
7. 建立可持续的工程基盘（测试、CI、版本锁定）

---

## 二、范围定义

| 范围类型 | 内容 |
|----------|------|
| **范围内** | 架构修复、依赖解耦、错误处理设计、死代码清理、配置增强、测试框架搭建、前端状态修正 |
| **范围外** | 新功能开发、UI 重设计、性能优化、部署配置、CI/CD 配置 |
| **推迟** | 响应式适配（tablet/mobile）、Tauri 深度集成 |

---

## 三、废弃说明

以下现有代码在对应修复完成后将被移除或替换：

| 废弃项 | 对应修复 | 清理方式 |
|--------|----------|----------|
| `api/routes.py` 中 `event_stream` 的内联心跳逻辑（line 364-392 的心跳部分） | P5.1 | 移除，改用 `HeartbeatManager` |
| `providers/openai.py:268-287` 中 `_enforce_role_alternation` 的注入空消息逻辑 | P3.4 | 移除，改为 `raise` |
| `api/routes.py` 中 `_stream_session_events` 的内联 `asyncio.wait_for` 心跳等待逻辑（line 136-145） | P5.1 | 替换为 `HeartbeatManager.wait_for_ping()` |
| `api/event_bus.py` 中 `_lock` / `_subscribers` 的直接外部访问模式 | P5.1 | 新增公共 `subscribe()` / `unsubscribe()` 方法替代 |

---

## 四、组件分解与修复方案

### P1 — 架构违规与安全性（高优先级）

#### 1.1 层违规：Session → API 反向依赖

**问题**: `session/manager.py` 中 `_trigger_auto_title` 在方法体内运行时导入 `laffybot.api.event_bus`。

**方案**: 定义事件发布接口（`EventPublisher` 协议类）位于 `session/` 层，`SessionManager.__init__` 通过依赖注入接收该接口。`api/dependencies.py` 中传入 `EventBus` 适配器实现。

**涉及文件**:
- 新增: `session/interfaces.py`（`EventPublisher` 协议）
- 修改: `session/manager.py`（构造签名），`api/event_bus.py`（适配协议），`api/dependencies.py`（注入）

**已决策**: 使用单一 `publish(event_type, data)` 方法。

---

#### 1.2 SessionManager 与 OpenAIProvider 硬耦合

**问题**: `session/manager.py` 三处直接 `OpenAIProvider(provider_config)`，`api/routes.py` 中 `trigger_consolidation` 同理。

**方案**: 定义 `ProviderFactory` 接口，接收 provider 类型/名称，返回 `BaseProvider` 实例。`SessionManager` 和路由层通过 DI 接收 factory。

**涉及文件**:
- 新增: `providers/factory.py`（`ProviderFactory` 实现，含注册/查找逻辑）
- 修改: `session/manager.py`（构造签名），`api/routes.py`，`api/dependencies.py`

---

#### 1.3 LLMResponse 成功/错误状态合并

**问题**: `providers/types.py:20-29` 同一 dataclass 包含 `content` 和 `error_kind`。`providers/openai.py` 将所有异常静默捕获并嵌入该对象，所有调用方必须检查 `error_kind`。

**方案**: 改为 `@dataclass` 继承体系或 Union 类型：
- `SuccessLLMResponse`（`content`, `tool_calls`, `usage`）
- `ErrorLLMResponse`（`error_kind`, `error_status_code`, `error_should_retry`, `error_message`）
- `LLMResponse = SuccessLLMResponse | ErrorLLMResponse`

**涉及文件**:
- 修改: `providers/types.py`，`providers/openai.py`，`session/manager.py`，`agent/title_generator.py`，`context/compressor.py`

**已决策**: 使用 `@dataclass` 继承体系（`SuccessLLMResponse(LLMResponse)` / `ErrorLLMResponse(LLMResponse)`）。

---

#### 1.4 `apiRequest` header 展开 bug

**问题**: `ui/src/lib/api.ts:8-13` 中 `...options` 在 `headers` 之后展开，导致 `options.headers` 覆盖整个 headers 对象。

**方案**: 调整展开顺序为 `...options` 在前，`headers` 在后。

**涉及文件**:
- 修改: `ui/src/lib/api.ts`

---

### P2 — Session 层稳健性

#### 2.1 无界锁字典——内存泄漏

**问题**: `session/manager.py:57-71` `_locks` 字典随会话增长，`delete_session()` 未清理。

**方案**: 在 `delete_session()` 中 `self._locks.pop(session_id, None)`。可扩展方案：使用 `weakref.WeakValueDictionary`。

**涉及文件**:
- 修改: `session/manager.py`

---

#### 2.2 `cancel_request` TOCTOU 竞争

**问题**: 先读 DB 状态，后查内存 token，二者之间状态可能变化。

**方案**: 在 `cancel_request` 中先获取 per-session lock，然后在锁内完成所有检查。

**涉及文件**:
- 修改: `session/manager.py`

---

#### 2.3 锁在流式持续期间一直持有

**问题**: `send_message` 中 `async with lock` 包裹整个 streaming 方法，而 `cancel_request` 不获取该锁。

**方案**: 缩减锁范围为仅状态转换部分（idle→busy、busy→idle）。streaming 本身不持有 session lock，通过 CancellationToken 协调取消。

**涉及文件**:
- 修改: `session/manager.py`

---

#### 2.4 Fire-and-forget 任务无背压

**问题**: 4 处 `asyncio.create_task` 无上限追踪。

**方案**: 引入 `_background_tasks: set[asyncio.Task]`，每个任务完成后 `task.add_done_callback(_background_tasks.discard)`。`shutdown()` 方法等待所有后台任务完成。

**涉及文件**:
- 修改: `session/manager.py`

---

### P3 — Agent Runner & Provider

#### 3.1 空 LLM 响应导致无限循环

**问题**: `agent/runner.py:220-228` 空响应时 `continue` 不追加消息，下次发送相同请求。

**方案**: 记录连续空响应计数，达到阈值（如 3 次）后终止并产出 error 事件。

**涉及文件**:
- 修改: `agent/runner.py`

---

#### 3.2 `asyncio.Queue.get()` 无超时

**问题**: `agent/runner.py:116-120` `await event_queue.get()` 无超时，若 producer 崩溃 consumer 将永久挂起。

**方案**: 添加 `asyncio.wait_for(event_queue.get(), timeout=XXX)`。

**涉及文件**:
- 修改: `agent/runner.py`

---

#### 3.3 `assert` 在 production 代码中

**问题**: `agent/tools/registry.py:145` `assert tool is not None` 在 `-O` 模式下失效。

**方案**: 替换为 `if tool is None: raise ToolNotFoundError(name)`。

**涉及文件**:
- 修改: `agent/tools/registry.py`

---

#### 3.4 `_enforce_role_alternation` 注入虚假消息

**问题**: `providers/openai.py:268-287` 向消息列表注入空消息。

**方案**: 改为 `raise ValueError("Consecutive same-role messages")` 或 `log.warning + merge`。

**已决策**: 连续相同角色时 `raise ValueError("Consecutive same-role messages")`。

**涉及文件**:
- 修改: `providers/openai.py`

---

#### 3.5 `_parse_response` 两条代码路径

**问题**: `providers/openai.py:419-541` dict 路径和 SDK 路径重复 120 行。

**方案**: 将两种原始响应统一为中间表示（`RawResponse` dataclass），再由此构建 `LLMResponse`。

**涉及文件**:
- 修改: `providers/openai.py`

---

### P4 — 配置 & 工程基盘

#### 4.1 无环境变量配置覆盖

**问题**: `config.py` 中 `ApiConfig` 继承 `BaseModel` 而非 `BaseSettings`，`pydantic-settings` 在 pyproject.toml 中但未使用。

**方案**: 改为继承 `BaseSettings`，添加 `model_config = SettingsConfigDict(env_prefix="LAFFYBOT_")`。

**涉及文件**:
- 修改: `config.py`

---

#### 4.2 `from_json()` 无错误处理

**问题**: `config.py:124-128` 裸 `open` 无 try/except。

**方案**: 捕获 `FileNotFoundError` → 友好提示退出，`JSONDecodeError` → 格式错误提示。

**涉及文件**:
- 修改: `config.py`、`__main__.py`

---

#### 4.3 依赖未锁定

**问题**: `pyproject.toml` 中 11 个运行时依赖全无版本号。

**方案**: 使用 `uv lock` 生成锁定文件，或为每个依赖添加最低版本约束。

**涉及文件**:
- 修改: `pyproject.toml`，新增 `uv.lock`

---

#### 4.4 `python >= 3.13` 过于激进

**问题**: 当前 Python 稳定版为 3.12，3.13 尚未发布。

**方案**: 降低至 `>=3.12`。

**涉及文件**:
- 修改: `pyproject.toml`

---

### P5 — 死代码 & 遗留清理

#### 5.1 心跳 SDK 未接入使用

**问题**: `agent/heartbeat.py:74-117` `run()` 和 `wait_for_ping()` 已实现但未调用。`api/routes.py` 中有两处独立的心跳逻辑：
1. `_stream_session_events`（line 128-142）：部分使用 `HeartbeatManager`（`interval_s`, `reset()`, `stop()`），但 `asyncio.wait_for` 逻辑内联实现，未使用 `wait_for_ping()`
2. `event_stream`（line 364-392）：完全独立的心跳实现，硬编码 15s，未使用 `HeartbeatManager`；同时直接访问 `bus._lock`/`bus._subscribers` 违反封装

**方案**: 
- `_stream_session_events`：将内联 `asyncio.wait_for` 替换为 `HeartbeatManager.wait_for_ping()`
- `event_stream`：改为使用 `HeartbeatManager` 实例（或 `subscribe()` 方法+外部心跳），消除硬编码常量和内部字段直接访问

**涉及文件**:
- 修改: `api/routes.py`（两处心跳均接入 `HeartbeatManager` API）

---

#### 5.2 旧项目名称残留

**问题**: `file_state.py:158` ContextVar 名 `"nanobot_file_states"`，`shell.py:151` 环境变量 `"NANOBOT_PATH_APPEND"`。

**方案**: 重命名为 `"laffybot_file_states"`、`"LAFFYBOT_PATH_APPEND"`。

**涉及文件**:
- 修改: `agent/tools/file_state.py`，`agent/tools/shell.py`

---

#### 5.3 `map_provider_error` 类型注解不匹配

**问题**: `api/errors.py:103-109` 签名列了具体子类型但调用方传入 `ProviderError` 基类，需要 `# type: ignore`。

**方案**: 改为接受 `ProviderError`，内部用 `isinstance` 分发。

**涉及文件**:
- 修改: `api/errors.py`

---

#### 5.4 Route 文件过大

**问题**: `api/routes.py` 1027 行，session / provider / tools / health 混杂。

**方案**: 拆分为 `session_routes.py`、`provider_routes.py`、`tool_routes.py`、`health_routes.py`。

**涉及文件**:
- 拆分: `api/routes.py` → 多个模块

---

#### 5.5 MCP 工具命名分类脆弱

**问题**: `agent/tools/registry.py:87-98` `get_definitions()` 通过 `name.startswith("mcp_")` 区分 MCP 和内置工具，内置工具若以 `mcp_` 开头会被错误分类。

**方案**: 改为显式标记（如 `Tool.kind: Literal["builtin", "mcp"]` 字段），替换字符串前缀判断。

**涉及文件**:
- 修改: `agent/tools/base.py`（`Tool` 基类增加 `kind` 属性），`agent/tools/registry.py`（`get_definitions` 改用 `kind` 判断）

---

### P6 — 前端修复

#### 6.1 SSE 流提前关闭时 UI 卡死

**问题**: 无 `done`/`error` 事件的流关闭时 `isStreaming` 永不清零。

**方案**: 在 `handleSubmit` 中添加 `finally` 块，检查并清理流状态。

**涉及文件**:
- 修改: `ui/src/pages/ChatPage.tsx`

---

#### 6.2 `boundaryToolCallCounts` 跨会话泄漏

**问题**: `ChatPage.tsx:29` `useRef` 保留旧会话的工具调用计数。

**方案**: 在 `useEffect` 的 sessionId 变更时重置 ref。

**涉及文件**:
- 修改: `ui/src/pages/ChatPage.tsx`

---

#### 6.3 React 19 Strict Mode 下历史请求重复

**问题**: `ChatPage.tsx:44-75` useEffect 无 cleanup，开发模式下请求两次。

**方案**: 添加 `AbortController` 并在 cleanup 中 abort。

**涉及文件**:
- 修改: `ui/src/pages/ChatPage.tsx`

---

#### 6.4 `@tanstack/react-query-devtools` 在 `dependencies`

**问题**: 应放在 `devDependencies`。

**方案**: 移入 `devDependencies`，import 加 `import.meta.env.DEV` 守卫。

**涉及文件**:
- 修改: `ui/package.json`、相关 import

---

### P7 — 测试

#### 7.1 测试覆盖率为 0%

**问题**: `tests/` 目录无真实测试代码。

**方案**: 按以下优先级搭建测试框架：
1. `providers/types.py` — `LLMResponse` 反序列化/构建
2. `agent/tools/registry.py` — 注册/执行/错误路径
3. `session/store.py` — CRUD + 乐观锁
4. `agent/cancellation.py` — 取消机制
5. `agent/heartbeat.py` — 心跳生成
6. `context/tokens.py` — token 计数
7. API route handler 集成测试（用 httpx.AsyncClient + FastAPI TestClient）

**涉及文件**:
- 新增: `tests/providers/`、`tests/agent/`、`tests/session/`、`tests/api/`

---

## 四、实现顺序

```
Phase 1 ── P4.3 (依赖锁定, 先锁再改)
         ── P1.4 (header bug, 一行修复)
         ── P3.3 (assert 修复)
         ── P3.1 (空响应无限循环)
         ── P2.1 (内存泄漏)
         │
Phase 2 ── P1.1 (层违规, 接口定义 + 注入改造)
         ── P1.2 (ProviderFactory)
         ── P1.3 (LLMResponse 分裂)
         │
Phase 3 ── P2.2 (TOCTOU 修复)
          ── P2.3 (锁范围缩减)
          ── P2.4 (后台任务管理)
          ── P5.1 (心跳 SDK 接入路由)
          │
Phase 4 ── P4.1 (BaseSettings)
          ── P4.2 (config 错误处理)
          ── P4.4 (python 版本)
          │
Phase 5 ── P5.2 (旧名称重命名)
          ── P5.4 (route 拆分)
          ── P6.x (前端修复)
          │
Phase 6 ── P7 (测试)
```

不出独立 Phase 的项（随对应模块改动一起修）：
- P3.2 (queue 超时) → Phase 2
- P3.4 (role alternation raise) → Phase 2
- P3.5 (parse 合并) → Phase 2
- P5.3 (type ignore) → Phase 4
- P5.5 (MCP 工具分类) → Phase 5（随 route 拆分一起，属于存量清理）

---

## 五、交付检查清单

- [ ] P1.1: `session/` 层无 API 层 import，EventPublisher 接口注入
- [ ] P1.2: SessionManager 不直接引用任何 Provider 具体类型
- [ ] P1.3: `LLMResponse = SuccessLLMResponse | ErrorLLMResponse`，无歧义状态
- [ ] P1.4: `apiRequest` 中 `Content-Type` 不会被 `options.headers` 覆盖
- [ ] P2.1: `delete_session()` 清理 `_locks`
- [ ] P2.2: `cancel_request` 在锁内完成状态检查
- [ ] P2.3: streaming 期间不持有 session lock
- [ ] P2.4: 后台任务可追踪、可等待
- [ ] P3.1: 连续空响应达到阈值后终止
- [ ] P3.2: Queue.get() 有超时
- [ ] P3.3: 无 `assert` 出现在 production 路径
- [ ] P3.4: 连续相同角色消息时 `raise ValueError("Consecutive same-role messages")`
- [ ] P3.5: 单条 `_parse_response` 路径
- [ ] P4.1: `ApiConfig` 继承 `BaseSettings`，支持 `LAFFYBOT_*` 环境变量
- [ ] P4.2: 配置缺失/格式错误有用户友好提示
- [ ] P4.3: `uv.lock` 已生成且 CI 可复现；`pydantic-settings` 已确认是否仍为运行时依赖（若 `BaseSettings` 已使用则保留，否则移入 dev）
- [ ] P4.4: `python >= 3.12` 可安装
- [ ] P5.1: 心跳无死代码
- [ ] P5.2: 无 `nanobot` 字符串残留
- [ ] P5.3: `map_provider_error` 无 `type: ignore`
- [ ] P5.4: `api/routes.py` 拆分为 `session_routes.py`、`provider_routes.py`、`tool_routes.py`、`health_routes.py`，每个模块 ≤ 400 行
- [ ] P5.5: `Tool` 基类有 `kind: Literal["builtin", "mcp"]` 字段，`get_definitions()` 不再依赖前缀判断
- [ ] P6.1: SSE 流提前关闭后 UI 恢复
- [ ] P6.2: `boundaryToolCallCounts` 跨会话正确隔离
- [ ] P6.3: useEffect 有 cleanup
- [ ] P6.4: devtools 在 devDependencies 中
- [ ] P7: 至少核心路径有测试（provider types、registry、store、cancellation）

---

## 参考文件

- `docs/api.md` — API 端点规范
- `docs/agent-runner-streaming-design.md` — AgentRunner 流式架构
- `docs/context-builder-design.md` — ContextBuilder 架构
- `docs/heartbeat-design.md` — 心跳机制设计
- `docs/session-manager-design.md` — SessionManager 架构
- `docs/session-manager-sqlite-impl.md` — SQLite 存储设计
- `docs/ui/ui-api-interface.md` — UI-API 接口契约
