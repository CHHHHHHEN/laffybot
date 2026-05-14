# Laffybot Bug 排查 & 修改计划

> 撰写日期：2026-05-14 · 状态：📝 计划阶段

---

## Issue 1: 导航按钮显示 "link.label" 文字

### 严重性
🔴 显示 bug，用户可见

### 根因
`ui/src/components/layout/NavLinks.tsx:26` — JSX 缺少花括号，`link.label` 被当作纯文本渲染而非变量插值。

```tsx
{/* 当前 (line 26) */}
<span>link.label</span>

{/* 修复 */}
<span>{link.label}</span>
```

### 修改文件
| 文件 | 改动 |
|------|------|
| `ui/src/components/layout/NavLinks.tsx` | line 26: 加 `{}` 花括号 |

### 验证
- 启动 UI 后左上角两个按钮显示 "聊天" 和 "设置" 而非 "link.label"

---

## Issue 2: 消息非流式渲染

### 严重性
🔴 核心体验缺陷

### 根因
前端采用两层缓冲区机制。SSE 的 `content`/`reasoning`/`tool_call` 事件通过 `appendToStreamBuffer()` 等写入独立的 `streamBuffer` 状态，但 `messages[]` 未更新 → React 不触发重渲染。直到 `done`/`error`/`cancelled` 事件到达后 `flushStreamBuffer()` 才把累积内容一次性写入最后一条 `assistant` 消息。

**关键文件**:
- `ui/src/stores/chat-store.ts` — `streamBuffer` 状态 + `appendToStreamBuffer`/`flushStreamBuffer`
- `ui/src/pages/ChatPage.tsx:69-73` — SSE 事件写入 buffer 而非 message
- `ui/src/components/chat/ReasoningBlock.tsx` — 默认折叠 (`useState(false)`)

### 当前行为
```
SSE content/reasoning 事件 → streamBuffer (独立于 messages[])
                                         → 用户只看到闪烁光标
SSE done 事件 → flushStreamBuffer() → 一次性填入 message → React 渲染全文
```

### 目标行为
1. 思考过程: 默认展开，内容逐 token 流入
2. 思考结束后: 自动折叠
3. 消息正文: 逐 token 流式渲染
4. 工具调用: 状态实时更新

### 修复方案

#### 2a. 重构 chat-store — 保持 buffer 积累，但流期间渲染纯文本

⚠️ **注意**: 不能简单移除 buffer 直接更新 `messages[]`。每次 `appendContent` 触发 ReactMarkdown 重解析会使 UI 严重卡顿（2000 token = 2000 次 markdown 编译）。

**核心设计**: 流期间渲染 `white-space: pre-wrap` 纯文本，流结束后切换为 ReactMarkdown。

```ts
// 新增状态: 流期间内容用纯文本存储
contentBuffer = ''       // 累积纯文本，流期间赋值给 message.content
reasoningBuffer = ''     // 同理

// 新增/修改的方法
appendContent(text: string)    → contentBuffer += text; updateLastMessage({ content: contentBuffer })
appendReasoning(text: string)  → reasoningBuffer += text; updateLastMessage({ reasoning: reasoningBuffer })
addToolCall(tc: ToolCall)      → updateLastMessage 追加 tool_calls
updateToolCall(...)            → updateLastMessage 更新 tool_calls 中的项
flushStreamBuffer()            → 仅清除 streaming 标记 (isStreaming: false)
```

修改 `chat-store.ts`:
- 保留 `text`/`reasoning` 内部积累，但每次 chunk 到达时也同步到 `messages[last].content` / `messages[last].reasoning`（纯文本拼接）
- `flushStreamBuffer` → `updateLastMessage({ isStreaming: false })` — 不做 content 搬运
- 由于 `messages[]` 发生变更 → React 重渲染，但此时内容是纯文本，不走 markdown
- `StreamMessage` 根据 `isStreaming` 判断：true → 纯文本渲染；false → ReactMarkdown 渲染

#### 2b. 修改 ChatPage 事件分发

`ChatPage.tsx` `handleSseEvent`:
- `content` → `chat.appendContent(event.text)`
- `reasoning` → `chat.appendReasoning(event.text)`
- `tool_call` → `chat.addToolCall({...})`
- `tool_result` → `chat.updateToolCallStatus(tool_call_id, {...})`
- `done` / `error` / `cancelled` → `chat.flushStreamBuffer()`

#### 2c. ReasoningBlock 改造

`ui/src/components/chat/ReasoningBlock.tsx`:
- 默认展开: `useState(true)`（而非 `false`）
- 折叠信号: **`done` SSE 事件到达时自动折叠**（比 `hasContent` 更简单，ChatPage 无需额外追踪状态）
- 用 `useEffect` 监听: 当 `isStreaming` 从 `true` → `false` 且有 reasoning 内容时，自动折叠（`setOpen(false)`）
- 保留手动折叠/展开交互

#### 2d. 无思考模式的正确行为

**场景**: 模型不支持 reasoning（如普通 GPT-4o，从无 `reasoning_content`）。

**路径**:
```
SSE 流全程无 reasoning 事件 → message.reasoning 始终为 undefined/falsy
  → StreamMessage 中 {reasoning && <ReasoningBlock ...>} 条件为 false
  → ReasoningBlock 从未渲染 ✓
```

所以无思考模式下 ThinkingBlock 不会误显示。

#### 2e. 只有思考 + 工具调用、无正文的特殊场景

**场景**: 模型产出了 reasoning 内容 → 决定调用工具 → 无 content 输出。

**路径**:
```
reasoning 事件到达 → ReasoningBlock 渲染并展开
content 事件 → 从未到达（模型直接切到 tool_call）
tool_call 事件到达 → 工具调用开始
done 事件到达 → flushStreamBuffer() 设置 isStreaming=false
→ isStreaming 从 true→false，若有 reasoning 内容则会自动折叠
```

**处理**: 模型已完成思考并做出决策（调用工具），思考阶段已结束，自动折叠合理。用户可通过点击 ReasoningBlock 重新展开。

#### 2f. MessageBubble 调整

`MessageBubble.tsx` 将 `isStreaming` 透传给 `ReasoningBlock` 的 `autoCollapse`。

### 修改文件清单

| 文件 | 改动 |
|------|------|
| `ui/src/stores/chat-store.ts` | 移除 buffer 机制，改为直接修改 messages[] |
| `ui/src/pages/ChatPage.tsx` | handleSseEvent 改用新 API |
| `ui/src/components/chat/ReasoningBlock.tsx` | 默认展开 + 自动折叠 |
| `ui/src/components/chat/MessageBubble.tsx` | 透传 autoCollapse |

### 验证
- 发送消息后立即看到思考内容逐 token 出现
- 思考结束后自动折叠，消息正文逐 token 渲染

---

## Issue 3: 会话卡在 busy 状态

### 严重性
🔴 功能阻塞，用户无法继续操作

### 根因
当客户端断连、网络错误或任务被取消时，`SessionManager.send_message()` 生成器被提前关闭。`GeneratorExit`/`asyncio.CancelledError` 继承自 `BaseException`，`send_message()` 中的 `except CancelledError`（自定义类）和 `except Exception` 都不捕获它。`finally` 块只清理了 `_active_tokens`，没有重置 session 状态。Session 永远卡在 `busy`。

**关键文件**:
- `laffybot/session/manager.py:217-246` — try/except/finally
- `laffybot/api/routes.py:100-150` — `_stream_session_events` 外层循环

### 错误传播路径

```
客户端断连
  → ASGI uvicorn 取消 StreamingResponse 任务
    → 任务收到 asyncio.CancelledError
      → _stream_session_events 生成器被关闭
        → send_message() 生成器收到 GeneratorExit
          → except CancelledError? 不匹配
          → except Exception? 不匹配 (GeneratorExit 是 BaseException)
          → finally: 仅 _active_tokens.pop()
          → ❌ 状态仍为 busy !!
```

### 修复方案

#### 3a. send_message() finally 块增加状态保护

在 `laffybot/session/manager.py` 的 `send_message()` 中,`finally` 块增加状态重置逻辑:

```python
finally:
    self._active_tokens.pop(session_id, None)
    # 保护：防止异常关闭导致 session 卡在 busy
    try:
        current = await self.store.get_session(session_id)
        if current.status == "busy":
            await self.store.update_session_status(
                session_id, "idle",
                current_request_id=None,
                error_message="Session interrupted unexpectedly",
            )
    except Exception:
        logger.exception("Failed to reset stuck busy session")
```

### 修改文件清单

| 文件 | 改动 |
|------|------|
| `laffybot/session/manager.py` | `send_message()` `finally` 块增加状态保护 |

### 验证
1. 发送消息后立即断开网络 / 关闭浏览器 Tab
2. 重新打开 → 该会话可正常发送消息（不再显示 "busy"）
3. 后端日志显示 "Failed to reset stuck busy session"（如果触发了）

---

## Issue 4: UI 无法管理 Agent 工具

### 严重性
🟡 功能缺失

### 当前状态
- `ToolRegistry` 在 `app.py:42` 创建为空，没有任何工具被注册
- `GET /api/v1/tools` 返回空列表
- `ToolSettingsPage.tsx` 只读显示空列表，配置按钮无事件
- `AgentRunner` 传递整个注册表，无过滤

### 修复方案

#### A1. 在 create_app() 中注册文件系统工具

`laffybot/api/app.py`:
```python
from laffybot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool

tool_registry_obj = tool_registry or ToolRegistry()
tool_registry_obj.register(ReadFileTool(workspace=Path.cwd()))
tool_registry_obj.register(WriteFileTool(workspace=Path.cwd()))
tool_registry_obj.register(EditFileTool(workspace=Path.cwd()))
tool_registry_obj.register(ListDirTool(workspace=Path.cwd()))
```

#### A2. ToolRegistry 支持 enable/disable + 过滤

`laffybot/agent/tools/registry.py`:
- 新增 `disabled: set[str]` 字段（持久化待后续迭代）
- `get_definitions()` 过滤掉 disabled 的工具
- 新增 `disable(name)` / `enable(name)` 方法

#### A3. 新增全局 toggle API 端点

`laffybot/api/routes.py`:
- `POST /api/v1/tools/{name}/disable` — 禁用工具
- `POST /api/v1/tools/{name}/enable` — 启用工具
- 修改 `GET /api/v1/tools` 响应增加 `enabled` 字段

#### A4. Tool 设置页改为可交互

`ui/src/pages/ToolSettingsPage.tsx`:
- 每项工具加 toggle switch
- 切换时调用 `POST /api/v1/tools/{name}/enable|disable`
- 显示启用/禁用状态（红色 badge 表示已禁用）

#### A5. AgentRunner 使用过滤后的 definitions

`laffybot/agent/runner.py`:
- `AgentRunSpec.tools` 保持为 `ToolRegistry`
- `_request_model_stream_with_events` 调用 `spec.tools.get_definitions()`（已内置过滤）
- LLM 未收到 disabled 工具的 definition，不会调用它们

### 修改文件清单

| 文件 | 改动 |
|------|------|
| `laffybot/api/app.py` | 注册文件系统工具到 ToolRegistry |
| `laffybot/agent/tools/registry.py` | `disabled` 集合 + `disable`/`enable` + `get_definitions` 过滤 |
| `laffybot/agent/runner.py` | `get_definitions()` 已包含过滤，无需额外改动 |
| `laffybot/api/routes.py` | `list_tools` 返回 `enabled` 状态 + 新增 `enable`/`disable` 端点 |
| `ui/src/lib/api.ts` | 新增 `ToolInfoWithStatus`、`enableTool`/`disableTool` |
| `ui/src/pages/ToolSettingsPage.tsx` | toggle switch + API 交互 |

### 验证
1. `GET /api/v1/tools` 返回所有工具，每个带 `enabled: bool`
2. 禁用 read_file → `POST /api/v1/tools/read_file/disable` → `GET /api/v1/tools` 显示 `false`
3. 发送消息 → LLM 不再收到 read_file 的 tool definition
4. UI 中可切换工具的启用/禁用

---

## 补充建议（不在当前计划内，供后续参考）

### S1. 文件系统工具 workspace 不应硬编码

`ReadFileTool(workspace=Path.cwd())` 在 `app.py` 注册时需从配置读取。建议:
- `ApiConfig` 新增 `workspace` 字段，或从环境变量 `LAFFYBOT_WORKSPACE` 读取
- 默认值 `Path.cwd()` 保持向后兼容

### S2. Session 删除时同步清除活跃 token

`SessionManager.delete_session()` 应同步取消 `_active_tokens` 中的对应 token，避免资源泄漏。

---

## 执行优先级

| 优先级 | Issue | 依赖 | 预估工时 |
|--------|-------|------|----------|
| P0 | Issue 1 (link.label) | 无 | 5 分钟 |
| P0 | Issue 3 (stuck busy) | 无 | 30 分钟 |
| P0 | Issue 2 (流式渲染) | Issue 1 可先做 | 2-3 小时 |
| P1 | Issue 4 (工具管理) | 无（独立功能） | 2-3 小时 |

## 总修改文件数

| Issue | 修改文件数 |
|-------|-----------|
| 1 | 1 |
| 2 | 4 |
| 3 | 1 |
| 4 | 6 |
| **合计** | **~12** |
