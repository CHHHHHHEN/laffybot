# UI 流式渲染数据模型重构计划

> 解决多 iteration 场景下流式内容不显示的问题

## 问题背景

### 现象

当 Agent 在同一条消息中输出多个 thinking 块或 tool call 块之后，后续的所有内容不再是流式传输显示。

### 根因分析

当前数据模型存在**分裂**：消息内容有两种存储方式，但渲染逻辑只识别一种。

| 场景 | 数据存储位置 | 渲染路径 |
|------|-------------|---------|
| 纯文本回复（无 tool call） | `message.content` / `message.reasoning` | fallback 渲染 |
| 有 tool call 后 | `segments[]` | segments 渲染 |

**事件流程问题**：

1. **iteration 0**：`content`/`reasoning` 事件 → 追加到 `buffer` → 更新 `message.content`/`message.reasoning` → 正常显示
2. **tool call 发生**：`iteration_boundary` 事件 → `flushPendingSegments()` 将 buffer 内容转为 `segments` → 清空 buffer
3. **iteration 1**：新的 `content`/`reasoning` 事件 → 追加到 buffer → 更新 `message.content`/`message.reasoning`
4. **渲染时**：因 `segments.length > 0`，只渲染 segments，**忽略** `message.content`/`message.reasoning`

**核心问题**：`StreamMessage` 组件在有 segments 时，完全忽略 `text` 和 `reasoning` props，但流式数据仍在追加到这些字段。

---

## 设计目标

1. **统一数据模型**：消除 segments 与 text/reasoning 的分裂，建立清晰的"历史 + 当前"模型
2. **正确流式渲染**：无论处于哪个 iteration，当前正在流式输出的内容都能实时显示
3. **保留 iteration 分段信息**：UI 能够区分不同 iteration 的内容，展示完整的思考过程
4. **持久化 reasoning 和 tool_calls**：消除页面刷新数据丢失的技术债务
5. **全面迁移**：不设向后兼容，彻底移除旧数据模型和相关代码

---

## 架构概述

### 新数据模型

```
Message
├── id, role, timestamp, isStreaming, isError
├── content: string                  # User 消息使用
├── iterations?: IterationContent[]  # Assistant 消息：已完成的历史
└── currentIteration?: IterationContent  # Assistant 消息：当前流式
```

```
IterationContent
├── iteration: number           # iteration 序号（0-based）
├── reasoning?: string          # 该 iteration 的推理内容
├── content?: string            # 该 iteration 的输出内容
└── toolCalls?: ToolCall[]      # 该 iteration 的工具调用
```

### 数据流

```
SSE 事件流
    │
    ▼
useSseStream.handleSseEvent()
    │
    ├─ content/reasoning → 更新 currentIteration
    ├─ tool_call → 追加到 currentIteration.toolCalls
    ├─ tool_result → 更新 currentIteration.toolCalls[i].status
    │
    └─ iteration_boundary → 
           ├─ iterations.push(currentIteration)  # 归档到历史
           └─ currentIteration = { iteration: n+1 }  # 开启新 iteration
    │
    ▼
StreamMessage 渲染
    ├─ iterations.map(render)           # 渲染历史
    └─ render(currentIteration)         # 渲染当前流式
```

### 组件职责边界

| 组件 | 职责 | 不负责 |
|------|------|--------|
| `chat-store` | 管理 `iterations` 和 `currentIteration` 状态 | 渲染逻辑 |
| `useSseStream` | 将 SSE 事件映射到 `currentIteration` 更新 | 直接操作 DOM |
| `StreamMessage` | 渲染 `iterations` + `currentIteration` | 状态管理、事件处理 |

---

## 后端改动

### 1. 数据库 Schema 变更

**messages 表新增列**：
- `reasoning_content TEXT` - 推理内容（Assistant 消息）
- `tool_calls_json TEXT` - 工具调用 JSON（Assistant 消息）

**迁移脚本**（添加至 `_run_migrations`，遵循现有 Migration 1/2 模式）：

```python
# Migration 3: Add reasoning_content and tool_calls_json to messages table
async with db.execute("PRAGMA table_info(messages)") as cursor:
    columns = {row["name"] for row in await cursor.fetchall()}

migrated = False
if "reasoning_content" not in columns:
    await db.execute("ALTER TABLE messages ADD COLUMN reasoning_content TEXT")
    migrated = True
if "tool_calls_json" not in columns:
    await db.execute("ALTER TABLE messages ADD COLUMN tool_calls_json TEXT")
    migrated = True
if migrated:
    await db.commit()
    logger.info("Database migration completed: added reasoning_content and tool_calls_json columns")
```

**不设后向兼容**：新列可为 NULL，现有数据自动填充 NULL。前端全面迁移至 `iterations` 模型，不保留旧字段任何兼容逻辑。

### 2. SessionStore 变更

**`save_message` 签名扩展**：
- 新增参数 `reasoning_content: str | None = None`
- 新增参数 `tool_calls: list[dict] | None = None`
- `tool_calls` 序列化为 JSON 存入 `tool_calls_json` 列

**`_row_to_message` 扩展**：
- 读取 `reasoning_content` 列
- 反序列化 `tool_calls_json` 列

**注意**：全面迁移，不保留旧数据格式兼容逻辑。

### 3. SessionManager 变更

**`send_message` 累积逻辑**：
- 新增 `reasoning_chunks: list[str] = []` 累积推理内容
- 新增 `accumulated_tool_calls: list[dict] = []` 累积工具调用
- `reasoning` 事件 → `reasoning_chunks.append(event.text)`
- `tool_call` 事件 → 累积到 `accumulated_tool_calls`
- `tool_result` 事件 → 更新 `accumulated_tool_calls` 中对应项的 status/result
- `done` 时调用 `save_message` 并传入 `reasoning_content` 和 `tool_calls`

### 4. API Schema 变更

**`MessageResponse` 扩展**：
- 新增 `reasoning_content: str | None = None`
- 新增 `tool_calls: list[dict] | None = None`

**`_serialize_message` 扩展**：
- 输出 `reasoning_content` 字段
- 输出 `tool_calls` 字段

### 5. 历史消息 LLM 上下文

**无需改动**：
- `_ALLOWED_MSG_KEYS` 已包含 `reasoning_content` 和 `tool_calls`
- `_sanitize_messages` 会保留这些字段
- LLM 调用时自动传入历史 reasoning 和 tool_calls

**注意**：
- `reasoning_content` 作为消息级字段传递，适用于支持 reasoning/thinking 的模型（如 DeepSeek R1、Claude extended thinking）
- 对于不支持 reasoning 字段的模型，provider 应忽略该字段（OpenAI 兼容 API 通常忽略未知字段）
- `tool_calls` 格式遵循 OpenAI Chat Completions API 标准

---

## 前端改动

### 1. chat-store 数据结构变更

**Message 类型变更**：
- 移除 `reasoning?: string`
- 移除 `tool_calls?: ToolCall[]`
- 移除 `segments?: MessageSegment[]`
- 新增 `iterations?: IterationContent[]`
- 新增 `currentIteration?: IterationContent`
- `content` 仅用于 User 消息

**新增操作**：
- `initCurrentIteration(sessionId, iteration)` - 初始化新的 currentIteration
- `appendCurrentContent(sessionId, text)` - 追加内容到 currentIteration.content
- `appendCurrentReasoning(sessionId, text)` - 追加推理到 currentIteration.reasoning
- `addCurrentToolCall(sessionId, toolCall)` - 添加工具调用到 currentIteration.toolCalls
- `updateCurrentToolCall(sessionId, toolCallId, updates)` - 更新工具调用状态
- `archiveCurrentIteration(sessionId)` - 将 currentIteration 归档到 iterations，清空 currentIteration

**历史消息迁移**：
- `appendSessionMessage` 对 Assistant 消息执行格式迁移：
  - 输入（API 响应）：`{ content, reasoning_content, tool_calls }`
  - 输出（存储）：`{ iterations: [{ iteration: 0, content, reasoning: reasoning_content, toolCalls }] }`
- 迁移后旧字段不保留，确保单一数据源

**渲染统一**：
- `StreamMessage` 仅渲染 `iterations` + `currentIteration`
- 移除 `text`/`reasoning`/`toolCalls`/`segments` props
- 移除旧渲染分支，不保留任何 fallback 逻辑

### 2. useSseStream 事件处理变更

**事件映射**：

| SSE 事件 | 操作 |
|---------|------|
| `session_start` | 记录 `request_id`，设置连接状态为 `connected` |
| `content` | `appendCurrentContent(text)` |
| `reasoning` | `appendCurrentReasoning(text)` |
| `tool_call` | `addCurrentToolCall({ ...toolCall, status: 'pending' })` |
| `tool_result` | `updateCurrentToolCall(toolCallId, { status, result, ... })` |
| `iteration_boundary` | `archiveCurrentIteration()` + `initCurrentIteration(iteration + 1)` |
| `done` | `archiveCurrentIteration()`（跳过空 iteration）+ `setConnectionStatus('disconnected')` + `stopStreaming()` + `setRequestId(null)` + `updateSessionStatus('idle')` + `invalidateQueries(['sessions'])` |
| `error` | `archiveCurrentIteration()` + `setConnectionStatus('error')` + `stopStreaming()` + `setRequestId(null)` + `updateSessionStatus('error')` |
| `cancelled` | `archiveCurrentIteration()` + `setConnectionStatus('disconnected')` + `stopStreaming()` + `setRequestId(null)` + `updateSessionStatus('idle')` |

**废弃逻辑**：
- `flushPendingSegments()` - 不再需要手动 flush
- `boundaryToolCallCounts` - 不再需要追踪边界
- `initSessionStreamBuffer()` - 不再需要 buffer 概念

### 3. StreamMessage 渲染逻辑变更

**渲染逻辑**：
- 渲染 `iterations`（已完成历史）
- 渲染 `currentIteration`（当前流式，带光标）

**渲染细节**：
- 每个 iteration 的 reasoning 使用 `ReasoningBlock` 组件
- 每个 iteration 的 toolCalls 根据 status 选择 `ToolCallCard` 或 `ToolResultBlock`
- 每个 iteration 的 content 使用 markdown 渲染
- 仅 `currentIteration` 显示流式光标
- 无 `iterations` 且无 `currentIteration` 时：不渲染（空消息）

---

## 集成点

### 与现有代码的集成

| 集成点 | 现有代码 | 改动 |
|--------|---------|------|
| 消息历史加载 | `ChatPage` 调用 `getHistory()` | 更新 `HistoryMessage` 类型以包含 `reasoning_content`/`tool_calls`，`appendSessionMessage` 内部执行迁移 |
| 消息列表渲染 | `MessageList` → `MessageBubble` → `StreamMessage` | `MessageBubble` 传递 `iterations`/`currentIteration`，移除旧 props |
| 流式状态判断 | `isStreaming` 来自 `streamingSessions` | 无需改动 |
| 消息追加 | `appendSessionMessage` | 内部执行格式迁移（Assistant 消息） |
| 消息提交 | `useSseStream.submit()` | 移除 `initSessionStreamBuffer` 调用 |
| 消息取消 | `useSseStream.cancel()` | 改为调用 `archiveCurrentIteration()` + 清理操作 |
| 会话清理 | `chat-store.cleanupSession()` | 清理 `iterations`/`currentIteration` 相关状态 |
| SSE 文档 | `docs/ui/ui-api-interface.md` | 更新 SSE 事件处理描述 |
| Message 类型 | `chat-store.ts` | 移除 `reasoning`/`tool_calls`/`segments` 字段 |

### SSE 事件协议

**无变更**：后端 SSE 事件协议保持不变，仅调整前端数据结构和后端持久化逻辑。前端全面迁移至新数据模型，不保留旧字段兼容。

---

## 错误处理

### SSE 连接错误

| 场景 | 行为 |
|------|------|
| 连接断开 | `currentIteration` 已有内容保留，标记 `isError: true` |
| 重连后 | 新消息重新开始，不影响已有 iterations |
| `submit()` 在 `session_start` 之前失败 | `currentIteration` 已在 `submit()` 中预初始化，catch 块需清理（重置为 `null`）；同时将预创建的消息标记为 `isError: true, isStreaming: false` |

### 数据一致性

| 场景 | 行为 |
|------|------|
| `iteration_boundary` 未收到 | `currentIteration` 继续累积，最终在 `done` 时归档 |
| `done` 时 `currentIteration` 为空 | 不归档，避免空 iteration |
| 数据库迁移失败 | 服务启动失败，日志记录具体错误，需手动修复后重启 |

---

## 边界情况

### 空内容

- iteration 无 content/reasoning/toolCalls：不渲染该 iteration
- `currentIteration` 为空对象：显示流式光标（等待 LLM 响应）

### 单 iteration 场景

- 无 tool call 的纯文本回复：`iterations = []`，`currentIteration` 包含全部内容
- `done` 后归档：`iterations = [iteration0]`，`currentIteration = null`

### 多 iteration 场景

- 有 tool call：每次 `iteration_boundary` 归档，开启新 `currentIteration`
- 最终：`iterations = [iteration0, iteration1, ...]`，`currentIteration = null`

### 历史消息迁移

- API 返回 `{ content, reasoning_content, tool_calls }` 格式
- `appendSessionMessage` 迁移为 `{ iterations: [{ iteration: 0, content, reasoning: reasoning_content, toolCalls }] }`
- 迁移后旧字段不保留

---

## 实现顺序

### Phase 0: 后端持久化（前置依赖）

1. 数据库迁移：messages 表添加 `reasoning_content` 和 `tool_calls_json` 列
   - 在 `laffybot/session/store.py` 的 `_run_migrations` 方法中添加 Migration 3
   - 迁移脚本见"数据库 Schema 变更"部分
   - 迁移失败时：记录错误日志，服务启动失败，提示手动修复
2. 修改 `SessionStore.save_message`：支持传入 `reasoning_content` 和 `tool_calls`
3. 修改 `SessionStore._row_to_message`：读取新列
4. 修改 `SessionManager.send_message`：累积 `reasoning` 和 `tool_call`/`tool_result` 事件
5. 修改 `MessageResponse` schema：添加 `reasoning_content` 和 `tool_calls` 字段
6. 修改 `_serialize_message`：输出新字段

**注意**：不设后向兼容，前端全面迁移至新数据模型，旧字段（`reasoning`/`tool_calls`/`segments`）完全移除。

### Phase 1: 前端数据结构准备

1. 在 `chat-store.ts` 中定义 `IterationContent` 类型
2. 修改 `Message` 类型：
   - 移除 `reasoning`、`tool_calls`、`segments` 字段
   - 添加 `iterations` 和 `currentIteration` 字段
3. 添加新操作方法（初始化、追加、归档等）
4. 修改 `appendSessionMessage`：对 Assistant 消息执行格式迁移
5. 更新 `api.ts` 的 `HistoryMessage` 类型：添加 `reasoning_content` 和 `tool_calls` 字段

### Phase 2: 事件处理迁移

1. 修改 `useSseStream.ts` 的 `handleSseEvent`，使用新操作方法
2. 修改 `useSseStream.ts` 的 `submit()`：
   - 初始化 `currentIteration = { iteration: 0 }`（而非等待 `session_start`）
   - 移除 `initSessionStreamBuffer` 调用
3. 修改 `useSseStream.ts` 的 `cancel()`：调用归档操作 + 清理操作
4. 修改 `chat-store.ts` 的 `cleanupSession()`：清理 `iterations`/`currentIteration` 相关状态
5. 移除 `flushPendingSegments`、`boundaryToolCallCounts`、`initSessionStreamBuffer` 相关逻辑
6. 在 `iteration_boundary` 时调用归档 + 初始化新 iteration

### Phase 3: 渲染逻辑适配

1. 修改 `StreamMessage.tsx`：
   - 移除 `text`/`reasoning`/`toolCalls`/`segments` props
   - 移除旧渲染分支
   - 仅保留 `iterations` + `currentIteration` 渲染
2. 修改 `MessageBubble.tsx`：
   - 传递 `iterations` 和 `currentIteration` props
3. 修改 `ChatPage.tsx` 历史加载逻辑：
   - 将 `getHistory()` 的 `.map()` 改为通过 `appendSessionMessage`（或等效的批量加载函数）处理每条历史消息
   - `appendSessionMessage` 内部对 Assistant 消息执行 flat→iterations 迁移
   - 映射时包含 API 返回的 `reasoning_content`/`tool_calls` 字段，而非仅 `role`/`content`/`timestamp`

### Phase 4: 清理废弃代码

1. 移除 `MessageSegment`、`StreamBuffer` 类型及相关 store 状态
2. 移除 `appendSessionContent`/`appendSessionReasoning`/`appendSessionSegment` 等旧操作
3. 移除 `initSessionStreamBuffer`/`flushSessionStreamBuffer` 等旧操作
4. 移除 `boundaryToolCallCounts` ref
5. 更新 `ui-api-interface.md` 以匹配新模型

---

## 交付清单

### 后端持久化

- [ ] `reasoning` 事件内容被累积并持久化到 `reasoning_content` 列
- [ ] `tool_call`/`tool_result` 事件内容被累积并持久化到 `tool_calls_json` 列
- [ ] 历史消息 API 返回 `reasoning_content` 和 `tool_calls` 字段
- [ ] LLM 上下文正确传入历史 `reasoning_content` 和 `tool_calls`
- [ ] 数据库迁移：旧数据 `reasoning_content` 和 `tool_calls_json` 为 NULL

### 前端功能验证

- [ ] 纯文本回复：内容逐字流式显示，光标跟随
- [ ] 单次 tool call：tool call 显示 → tool result 显示 → 最终内容流式显示
- [ ] 多次 tool call：每次 iteration 的内容依次流式显示，无内容丢失
- [ ] 多个 thinking 块：每个 thinking 块正确显示，后续内容流式显示
- [ ] 历史消息加载：历史消息正常显示，无流式光标，`reasoning_content`/`tool_calls` 正确迁移到 `iterations[0]`
- [ ] 历史消息渲染一致性：迁移后的 `iterations[0]` 渲染效果与旧格式渲染效果一致（视觉无差异）
- [ ] `session_start` 事件：记录 `request_id`，设置连接状态
- [ ] `submit()` 流程：创建 assistant 消息时初始化 `currentIteration = { iteration: 0 }`
- [ ] `cancel()` 流程：正确归档 `currentIteration` 并清理状态

### 数据一致性

- [ ] `done` 后 `iterations` 包含所有已完成 iteration
- [ ] `done` 后 `currentIteration` 为 null
- [ ] 流式中断时已有内容保留
- [ ] `cleanupSession()` 正确清理 `iterations`/`currentIteration` 相关状态

### 错误处理

- [ ] 连接断开：`currentIteration` 内容保留，`isError: true`
- [ ] `submit()` 在 `session_start` 之前失败：消息标记 `isError: true`，无 `currentIteration` 泄漏
- [ ] `iteration_boundary` 未收到：`currentIteration` 继续累积，`done` 时正确归档
- [ ] `done` 时 `currentIteration` 为空：不归档，避免空 iteration

### 迁移验证

- [ ] SSE 事件协议无变更
- [ ] User 消息格式不变
- [ ] 历史消息加载后正确迁移为 iterations 格式
- [ ] 旧字段（`reasoning`/`tool_calls`/`segments`）已从 Message 类型完全移除，无残留引用
- [ ] 前端代码中无任何旧字段的条件判断或 fallback 逻辑

---

## 废弃清单

| 组件/字段/函数 | 处理方式 |
|---------------|---------|
| `Message.segments` | 移除 |
| `Message.reasoning` | 移除（迁移至 `iterations[i].reasoning`） |
| `Message.tool_calls` | 移除（迁移至 `iterations[i].toolCalls`） |
| `MessageSegment` 类型 | 移除 |
| `StreamBuffer` 类型及相关状态 | 移除 |
| `flushPendingSegments()` | 移除 |
| 旧的追加/更新操作 | 移除（由新操作替代） |
| `initSessionStreamBuffer()`/`flushSessionStreamBuffer()` | 移除 |
| `boundaryToolCallCounts` | 移除 |
| `StreamMessage` 旧渲染分支 | 移除 |
| `StreamMessage` 的旧 props | 移除 |

---

## Existing Technical Debt

Pre-existing issues in the codebase that are outside this plan's scope. These are recorded for awareness and potential follow-up.

| Category | Location | Description |
|----------|----------|-------------|
| Reliability | `ui/src/lib/api.ts:166-167` | `consecutiveGuardFailures` threshold (10) with no recovery action when exceeded |
| Readability | `ui/src/lib/api.ts:185-186` | Special case `data === '{}' && currentEvent === 'done'` handling unclear |
| Reliability | `ui/src/lib/abort-manager.ts:6` | Module-level Map survives page navigation, could accumulate stale controllers |
| Reliability | `ui/src/pages/ChatPage.tsx:54` | History loading catch block silently swallows errors — no toast or user feedback |

---

## 参考

**前端**：
- `ui/src/stores/chat-store.ts` - 当前数据结构
- `ui/src/hooks/useSseStream.ts` - 当前事件处理
- `ui/src/components/chat/StreamMessage.tsx` - 当前渲染逻辑

**后端**：
- `laffybot/session/store.py` - 消息持久化
- `laffybot/session/manager.py` - SSE 事件累积与消息保存
- `laffybot/api/session_routes.py` - 历史 API 端点
- `laffybot/api/schemas.py` - API 响应 schema
- `laffybot/agent/events.py` - SSE 事件类型定义
- `laffybot/agent/runner.py` - SSE 事件发送逻辑
