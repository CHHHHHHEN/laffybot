# UI API 接口文档

> **文档范围说明**：本文档从 UI 角度定义与后端 API 的接口契约，聚焦 API 与 UI 组件/状态之间的映射关系，而非重复定义 API 细节。
>
> **配套文档**：API 端点定义、SSE 事件格式、错误码及会话状态机详见 `api.md`。

## 实现状态

| 模块 | 状态 | 说明 |
|------|------|------|
| API 端点定义 | ✅ 已有定义 | 见 `api.md` |
| UI-API 映射 | ✅ 本文档 | |
| 状态同步契约 | ✅ 本文档 | |
| API 客户端实现 | ✅ 已完成 | 见 `ui/src/lib/api.ts` |

## API 端点与 UI 映射

端点请求/响应格式详见 `api.md`，下表仅列出 UI 侧的调用上下文：

| 端点 | UI 调用时机 | 对应 UI 动作 |
|------|-------------|-------------|
| `POST /api/v1/sessions` | 用户提交新建会话表单 | `NewSessionDialog` 确认 → `session-store` 追加 → 导航到 `/chat/{id}` |
| `GET /api/v1/sessions/{id}` | 进入会话 / 刷新会话状态 | `session-store` 更新当前会话状态 |
| `GET /api/v1/sessions` | 侧边栏加载 / 下拉刷新 | `session-store` 拉取列表 |
| `POST /api/v1/sessions/{id}/messages` | 用户发送消息 | `InputBar` 提交 → `chat-store` 建立 SSE 连接 |
| `POST /api/v1/sessions/{id}/cancel` | 用户取消生成 | `InputBar` 取消按钮 → `chat-store` 关闭流 |
| `DELETE /api/v1/sessions/{id}` | 用户确认删除 | `ConfirmDialog` 确认 → `session-store` 移除 |
| `GET /api/v1/sessions/{id}/history` | 会话切换 / 上滚加载更多 | `chat-store` 加载历史消息 |
| `GET /api/v1/health` | 应用启动 / 降级检测 | `ConnectionStatusBanner` |

### 分页约定

`GET /api/v1/sessions` 和 `GET /api/v1/sessions/{id}/history` 均支持 `limit`/`offset` 分页：

| 场景 | limit | 触发条件 |
|------|-------|----------|
| 会话列表首次加载 | 20 | 组件挂载 |
| 会话列表加载更多 | 20 | 滚动到底部 |
| 历史消息首次加载 | 50 | 进入会话 |
| 历史消息加载更多 | 50 | 滚动到顶部 |

## SSE 事件与 UI Store 映射

事件格式详见 `api.md`「发送消息（SSE 流式）」章节。下表定义 UI 层对每个事件的处理行为：

| SSE 事件 | `chat-store` 处理 | UI 表现 |
|----------|-------------------|---------|
| `session_start` | 记录 `activeRequestId`，`setConnectionStatus('connected')`，标记会话为 busy | 无直接 UI 变化 |
| `content` | `appendToStreamBuffer('text', text)` → `updateLastMessage` 更新最后一条助手消息 | `StreamMessage` 逐 token 渲染 |
| `reasoning` | `appendToStreamBuffer('reasoning', text)` → `updateLastMessage` | `ReasoningBlock` 实时内容追加 |
| `tool_call` | `addToolCallToBuffer(toolCall)` → `updateLastMessage` | `ToolCallCard` 立即出现，展示工具名和参数 |
| `tool_result` | `updateToolCallInBuffer(tool_call_id, updates)` → `updateLastMessage` | `ToolCallCard` 转为完成态（ToolResultBlock），展示结果/耗时 |
| `done` | `flushStreamBuffer()` → 转存为正式 Message，重置 buffer，`setConnectionStatus('disconnected')`，标记会话为 idle | 移除流式光标，渲染完成状态 |
| `error` | `flushStreamBuffer()`，标记 isError=true，`setConnectionStatus('error')`，标记会话为 error | 消息气泡显示"发送失败" |
| `cancelled` | `flushStreamBuffer()`，重置 buffer，`setConnectionStatus('disconnected')`，标记会话为 idle | 消息标记为中断 |
| `ping` | 忽略（无操作） | 无 |

## 状态同步契约

### 会话状态双向同步

UI 维护的会话状态与实际后端状态之间存在延迟，需按以下规则同步：

| 场景 | UI 更新方式 | 依据 |
|------|------------|------|
| 发送消息后 | 乐观标记为 `busy` | 本地发起，状态确定 |
| SSE `done` 到达 | 更新为 `idle` | 服务端事件驱动 |
| SSE `error` 到达 | 更新为 `error` | 服务端事件驱动 |
| 初始加载 | 以服务端返回为准 | `GET /api/v1/sessions` |
| 操作失败（网络错误） | 回滚到操作前状态 | 乐观更新失败回退 |

### 乐观更新规则

| 操作 | 乐观更新 | 失败回滚 |
|------|----------|----------|
| 创建会话 | 立即追加到列表 | 从列表移除 + Toast 提示 |
| 删除会话 | 立即从列表移除 | 恢复到列表原位置 |
| 发送消息 | 立即追加用户消息 | 标记消息为发送失败 |

## 错误处理

API 客户端定义了 `ApiError` 类（位于 `ui/src/lib/api.ts`），携带 `status`、`code`、`message` 三个字段。
UI 层按以下策略处理：

| HTTP 状态码 | UI 处理 |
|-------------|---------|
| 400 | `InputBar` 内联错误提示（参数无效） |
| 404 | 轻提示 + 导航回 `/chat`（会话已被删除） |
| 409 SESSION_BUSY | `InputBar` 禁用态 + 提示「当前会话正在处理中」 |
| 500 / 网络超时 | `ConnectionStatusBanner` 或消息内联重试按钮 |

SSE 连接基于 `fetch` + `ReadableStream` 实现（非 `EventSource`），支持 `AbortController` 取消。
断线后续传：UI 保留已接收内容，提供重新发送入口，不自动重连。

### SSE 连接实现在 `connectSseStream`（api.ts）
- 通过 `POST /api/v1/sessions/{id}/messages` 建立
- 使用 `response.body.getReader()` 逐 chunk 读取
- 手动解析 `event:` / `data:` SSE 文本协议
- 通过 `AbortSignal` 支持取消
