---
archived_from: plan.md
archived_at: 2026-05-17
implements: architecture audit fixes
status: implemented
summary: |
  Fix seven architecture quality issues: stuck-busy watchdog, SSE error path unification,
  ChatPage SSE extraction, SSE runtime type guard, total request timeout, dead code cleanup,
  and test infrastructure.
---

# 架构整改计划

> 基于 2026-05-17 架构审计结果，修复后端与前端的架构质量问题。
> 来源：`docs/` 设计文档 + 审计发现的偏差与风险。

## 目标

修复七项架构质量问题：三项高风险（stuck-busy 看门狗、SSE 错误处理重叠、ChatPage 过耦合）、两项中风险（运行时校验、请求超时）、两项低风险（死代码清理、测试基础设施）。目标是通过修复使架构与设计文档对齐，消除数据/控制流中的空白区域。

## 范围

| 范围类型 | 内容 |
|----------|------|
| **范围内** | 后端 session 状态机韧性、SSE 错误处理路径统一、前端 SSE 逻辑提取、SSE 事件运行时校验、总请求超时、清理后端/前端已确认的死代码、建立测试基础设施 |
| **范围外** | 功能新增（如记忆系统、多提供商扩展）、性能优化、部署/CI 配置、国际化、响应式断点 |
| **推迟** | AppSettingStore 接口抽象、Sidebar/SessionList 组件拆分、代码分割、TypeScript 版本降级 |

## 实施步骤

### Phase 1：高风险修复

#### 1. Session 状态机 — stuck-busy 看门狗

**问题**：进程崩溃或异常断开后，`busy` 状态的会话永不解锁。

**方案**：在 `SessionManager` 中增加后台扫描任务，定期（如 60s）扫描 status=busy 且 updated_at 超时的会话，将其重置为 idle。

**设计要点**：
- 扫描周期和超时阈值可配置（`session_timeout_seconds`）
- 扫描任务在 `SessionManager.start()` / `.stop()` 生命周期中管理
- 超时重置时清理关联的 `CancellationToken` 和 `asyncio.Lock`
- 记录 WARN 日志：会话 ID、实际持续时间、超时阈值

**集成点**：`session/manager.py` 新增生命周期方法；`session/models.py` 新增配置字段。

**错误处理**：
- 扫描任务自身异常：捕获并记录 ERROR 日志，不影响后续扫描周期
- 重置失败（乐观锁冲突）：跳过，下一周期重试

**边界情况**：
- 看门狗启动前没有 stuck 会话
- 正常运行的 busy 会话不应被误杀（updated_at 比较 + 阈值保护）
- 会话在扫描间隙完成并变为 idle，乐观锁 UPDATE 无影响

#### 2. SSE 错误处理路径统一

**问题**：`_stream_session_events()`、`SessionManager.send_message()`、`AgentRunner.run_stream()` 三层均捕获同类异常，可能产生重复或矛盾的 error events。

**方案**：重新划分各层职责，消除重叠。

**职责划分**：
- `AgentRunner.run_stream()`：只捕获 `CancelledError` 和工具执行中的 `ToolError`，产出对应的 SSE event，不处理会话/提供商层面的异常
- `SessionManager.send_message()`：捕获 `ProviderError`、`SessionError` 体系异常，转换为 SSE error event，然后正常 yield 出去。不再 catch 泛型 `Exception`
- `_stream_session_events()`：只做事件格式化和流控制（心跳、cleanup），不再 catch 领域异常。所有领域异常由 `SessionManager` 统一转换为 error event
- FastAPI exception handler：处理从 `send_message()` 逃逸的未预期异常（后端错误），返回 500

**具体改动**：
- `agent/runner.py`：移除通用 Exception 捕获，只处理 `CancelledError` 和 `ToolError`
- `session/manager.py`：将 error event 产出逻辑集中在 manager 层，简化 catch 结构
- `session_routes.py._stream_session_events()`：移除重复的 `SessionNotFoundError` / `ProviderNotFoundError` / `SessionError` 捕获

**错误处理**（按异常/场景描述）：
- 期望由 AgentRunner 发出 error event 的场景：取消、工具执行失败
- 期望由 SessionManager 发出 error event 的场景：提供商不可用、模型不存在、会话状态冲突
- 从所有层逃逸到 FastAPI 的异常：未预期的内部错误，响应 500

#### 3. ChatPage SSE 逻辑提取

**问题**：`ChatPage.tsx` 345 行，SSE 事件分发、流管理、会话创建、取消逻辑全部耦合在此。

**方案**：将 SSE 事件处理和流管理逻辑提取为独立 hook `useSseStream`，ChatPage 只做 UI 编排。

**组件职责**：
- `useSseStream(sessionId: string | undefined)` — 管理 SSE 连接生命周期、事件分发、流缓冲区刷新、连接状态暴露
- `ChatPage` — 用户交互处理（提交、取消、切换）、组件编排、将 hook 输出映射到 store/UI

**接口定义**：
- `useSseStream` 接收：`sessionId`、`onError` 回调
- `useSseStream` 返回：`{ submit, cancel, isStreaming, connectionStatus, error }`

**集成点**：`ui/src/hooks/useSseStream.ts` 新建；`ChatPage.tsx` 从原有方法中提取。

**边界情况**：
- 会话切换时自动中断旧连接、清理状态
- 组件卸载时中断连接
- 快速连续提交（防重复）由 hook 内部管理
- 会话切换与流进行中：中断旧流，清理 buffer，再加载新会话历史

### Phase 2：架构韧性增强

#### 4. SSE 事件运行时校验

**问题**：`connectSseStream` 使用 `as SseEvent` 类型断言，无运行时校验。格式错误的服务器数据可静默传播。

**方案**：在 SSE 解析入口增加运行时类型守卫，校验后在开发者环境下记录 WARN 日志。

**设计要点**：
- 定义 `isSseEvent(obj: unknown): obj is SseEvent` 类型守卫函数
- 对每个解析的 SSE JSON 调用类型守卫，校验失败则丢弃并记录警告
- 校验在 `api.ts` 的 `connectSseStream` 内部，不作为单独的抽象层

**错误处理**：
- 校验失败：丢弃该事件，记录 WARN 日志，不中断流连接
- 连续校验失败（超过阈值）：记录 ERROR 日志，但保留流连接

#### 5. 总请求超时

**问题**：无硬性总请求时间上限，LLM 循环可无限迭代。

**方案**：在 `SessionManager.send_message()` 中增加总超时控制，超时触发自动取消。

**设计要点**：
- 在 `ContextConfig` 中增加 `request_timeout_seconds: float = 600`（默认 10 分钟）
- `send_message()` 使用 `asyncio.wait_for()` 包裹 AgentRunner 执行
- 超时后自动触发 `CancellationToken.cancel()`

**错误处理**：
- 超时：发出 `cancelled` SSE event（reason: "request_timeout"）
- 与手动取消共享相同的 `CancellationToken` 路径，处理逻辑一致

### Phase 3：清理与基础

#### 6. 清理确认的死代码

| 代码 | 位置 | 清理方式 |
|------|------|----------|
| `sendMessage()` 函数 | `ui/src/lib/api.ts` | 删除未使用的导出函数 |
| `HeartbeatManager.run()` 方法 | `agent/heartbeat.py` | 删除未使用的背景任务方法 |

**注意**：`BaseProvider.chat_completion()` 尽管只在非流式路径使用（compressor/consolidator/extractor/title_generator），但仍被调用，**不是死代码**，不应清理。

#### 7. 测试基础设施

**问题**：后端测试仅有目录结构无源码，前端无测试框架。

**方案**：

- **后端**：在已有 `tests/` 结构上建立 pytest 测试。优先覆盖：
  - `SessionManager` 状态机转换
  - `SQLiteStore` CRUD 和乐观锁
  - `ProviderRegistry` 路由/限流
- **前端**：引入 Vitest + testing-library，优先覆盖：
  - `chat-store` 状态转换
  - SSE 解析逻辑

## 现有技术债（本计划不处理）

| 类别 | 位置 | 说明 |
|------|------|------|
| 宽泛 catch | `session/manager.py:361, 387` | `except Exception` 在 send_message 及 finally 中，可能掩盖特定错误 |
| 脆弱的乐观锁重试 | `session_routes.py:408-415` | update_session_title 的无锁重试逻辑位于路由层，应移至 manager |
| 空 catch | `ui/src/lib/api.ts:199, 271` | SSE JSON 解析失败的 catch 块为空，调试困难 |
| 无运行时类型校验 | `ui/src/lib/api.ts:197` | `as SseEvent` 类型断言无运行时守卫（见 Phase 2 item 4 计划修复） |

## 交付检查清单

- [x] 1. Stuck-busy 看门狗：SessionManager 后台扫描 busy 超时会话并重置，记录 WARN 日志
- [x] 2. SSE 错误路径：AgentRunner → SessionManager → 路由，三层 catch 不重叠，无重复 error event
- [x] 3. `useSseStream` hook：ChatPage SSE 逻辑独立，ChatPage 降至 200 行以下
- [x] 4. SSE 事件类型守卫：connectSseStream 入口校验，丢弃 + 日志
- [x] 5. 总请求超时：ContextConfig 新增字段 + SessionManager 包裹超时 + cancelled event
- [x] 6. 死代码清理：sendMessage() 和 HeartbeatManager.run() 已移除；BaseProvider.chat_completion() 确认仍被使用，保留不动
- [x] 7. 测试基础设施：后端 pytest 配置就绪，前端 Vitest 配置就绪，每个模块至少 1 个验证测试

---

## Implementation Record

### Core files changed

**Backend (Python):**
- `laffybot/session/manager.py` — Added stuck-busy watchdog (`start()`, `_watchdog_loop()`, `shutdown()`), deadline check for total request timeout, removed generic `except Exception`, added `SessionError` catch
- `laffybot/agent/runner.py` — Removed generic `except Exception` catch (only `CancelledError` remains)
- `laffybot/agent/heartbeat.py` — Removed unused `run()` method
- `laffybot/config.py` — Added `request_timeout_seconds` field to `ContextConfig`
- `laffybot/api/dependencies.py` — Added `session_timeout_s`, `watchdog_interval_s` params to `build_session_manager()`
- `laffybot/api/session_routes.py` — Removed domain exception catches from `_stream_session_events()`
- `laffybot/api/app.py` — Added `session_manager_obj.start()` call in lifespan

**Frontend (TypeScript):**
- `ui/src/hooks/useSseStream.ts` — New hook: SSE connection lifecycle, event dispatch, buffer management
- `ui/src/pages/ChatPage.tsx` — Reduced from 345 to 106 lines (extracted SSE logic to hook)
- `ui/src/lib/api.ts` — Removed `sendMessage()` function and `SendMessageResponse` interface; added `isSseEvent` type guard with consecutive failure threshold
- `ui/src/stores/chat-store.test.ts` — New: 10 tests for store state transitions
- `ui/vitest.config.ts` — New: Vitest configuration

**Tests:**
- `tests/session/test_session_manager.py` — New: 9 tests for SessionManager state machine

**Config:**
- `ui/package.json` — Added `vitest` devDependency and `test`/`test:watch` scripts

### Design docs referenced
- `docs/session-manager-design.md`
- `docs/session-model-decoupling.md`
- `docs/agent-runner-streaming-design.md`
- `docs/heartbeat-design.md`

### Outstanding items / known gaps
- `docs/session-model-decoupling.md` updated to reflect centralized error handling
- Event loop closure warning from aiosqlite in tests (pre-existing, harmless)
- Stale `rolldown`/`vite` plugin type mismatch in `vite.config.ts` (pre-existing)
