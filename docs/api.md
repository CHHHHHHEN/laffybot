# Laffybot API 设计文档

## 概述

Laffybot API 提供基于 FastAPI 的 HTTP 接口，支持会话管理、消息发送和 SSE 流式响应。会话数据使用 SQLite 持久化存储。

## 版本控制

所有 API 端点均使用版本前缀 `/api/v1/`，便于未来版本迭代和向后兼容。

## 依赖

```
fastapi>=0.109.0
uvicorn>=0.27.0
aiosqlite>=0.19.0
```

## 会话状态

会话具有以下状态：

| 状态 | 描述 | 允许的操作 |
|------|------|----------|
| `idle` | 空闲，无正在进行的请求 | 发送消息、获取历史、删除 |
| `busy` | 正在处理请求 | 取消请求、获取信息 |
| `error` | 发生错误，需处理 | 获取历史、删除 |
| `inactive` | 已关闭/失效 | 无 |

### 状态转换

```
idle -> busy     (发送消息)
busy -> idle     (请求完成)
busy -> error    (发生错误)
idle -> inactive (删除会话)
error -> inactive (删除会话)
```

## 并发控制

**同一会话不支持并发请求。**

- 当会话状态为 `busy` 时，新的 `/stream` 请求将返回 `409 SESSION_BUSY` 错误
- 客户端应等待当前请求完成后再发送新请求
- 如需取消当前请求，使用取消接口（待实现）

## 日志记录

服务端使用 **loguru** 进行日志记录，应记录以下关键操作：

**会话生命周期日志：**
- 会话创建（session_id, model, created_at）
- 会话删除（session_id, deleted_at）

**请求处理日志：**
- 请求开始（session_id, request_id, timestamp）
- 请求完成（session_id, request_id, stop_reason, duration_ms）
- 请求错误（session_id, request_id, error_code, error_message）

**工具调用日志：**
- 工具调用开始（tool_name, tool_call_id, arguments）
- 工具调用完成（tool_name, tool_call_id, duration_ms, success）
- 工具调用错误（tool_name, tool_call_id, error_type, error_message）

> **注意：** 敏感信息（如用户消息内容、工具参数）不应记录到日志中。

## API 端点

### 1. 创建会话

```
POST /api/v1/sessions
```

**请求体:**
```json
{
    "model": "deepseek-ai/DeepSeek-V3",
    "system_prompt": "You are a helpful assistant.",
    "max_iterations": 10
}
```

**响应:**
```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "model": "deepseek-ai/DeepSeek-V3",
    "status": "idle",
    "created_at": "2024-01-15T10:30:00Z"
}
```

### 2. 获取会话信息

```
GET /api/v1/sessions/{session_id}
```

**响应:**
```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "model": "deepseek-ai/DeepSeek-V3",
    "status": "idle",
    "created_at": "2024-01-15T10:30:00Z",
    "message_count": 5,
    "current_request_id": null
}
```

**字段说明:**
- `current_request_id`: 当前正在进行的请求 ID，若无则为 `null`

### 3. 获取会话历史

```
GET /api/v1/sessions/{session_id}/history
```

**查询参数:**
- `limit` (可选): 返回消息数量限制，默认 50

**响应:**
```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "messages": [
        {
            "role": "user",
            "content": "Hello!",
            "timestamp": "2024-01-15T10:31:00Z"
        },
        {
            "role": "assistant",
            "content": "Hi! How can I help you?",
            "timestamp": "2024-01-15T10:31:05Z"
        }
    ]
}
```

### 4. 发送消息（SSE 流式）

```
POST /api/v1/sessions/{session_id}/messages
```

**请求体:**
```json
{
    "content": "请帮我分析这个项目的结构"
}
```

**响应 (SSE 格式):**
```
event: message
data: {"type": "session_start", "session_id": "550e8400-e29b-41d4-a716-446655440000", "request_id": "req_abc123"}

event: message
data: {"type": "content", "text": "Python is"}

event: message
data: {"type": "content", "text": " a programming"}

event: message
data: {"type": "content", "text": " language."}

event: message
data: {"type": "reasoning", "text": "Let me check the file first..."}

event: message
data: {"type": "tool_call", "tool_call_id": "tc_001", "name": "read_file", "arguments": {"path": "example.py"}}

event: message
data: {"type": "tool_result", "tool_call_id": "tc_001", "name": "read_file", "result": "file content...", "success": true, "duration_ms": 150}

event: message
data: {"type": "content", "text": "Based on the file..."}

event: message
data: {"type": "done", "stop_reason": "completed", "usage": {"prompt_tokens": 150, "completion_tokens": 200}, "tools_used": ["read_file"]}

event: done
data: {}
```

**SSE 事件类型详解:**

| 事件类型 | 描述 | 必需字段 | 可选字段 |
|---------|------|---------|---------|
| `session_start` | 会话开始 | `session_id` | `request_id` |
| `content` | 文本内容片段 | `text` | - |
| `reasoning` | 推理过程（思维链） | `text` | - |
| `tool_call` | 工具调用开始 | `tool_call_id`, `name`, `arguments` | `timeout_ms` |
| `tool_result` | 工具执行结果 | `tool_call_id`, `name`, `result`, `success` | `duration_ms`, `error_message` |
| `done` | 响应完成 | `stop_reason` | `usage`, `tools_used` |
| `error` | 发生错误 | `error` (嵌套对象) | - |
| `cancelled` | 请求被取消 | `reason` | - |
| `ping` | 心跳事件 | `timestamp` | - |

> **注意:** `reasoning` 事件由后端统一处理不同 LLM 提供商的思维链格式差异（如 DeepSeek 的 `reasoning_content` 字段），对外暴露统一的事件格式，客户端无需关心底层实现细节。

**实现说明：**

> **✅ 当前实现状态**
> 
> 当前版本已完整实现流式事件输出：
> 
> 1. **Phase 1 - 基础流式支持** ✅：
>    - `AgentRunner.run_stream()` 方法已实现
>    - 集成 `chat_completion_stream` 实现内容流式输出
>    - 支持 `session_start`、`content`、`reasoning`、`done` 事件
> 
> 2. **Phase 2 - 工具调用流式** ✅：
>    - 实现 `tool_call`、`tool_result` 事件
>    - 支持工具执行计时（`duration_ms`）
>    - 支持工具执行进度反馈
> 
> 3. **Phase 3 - 完整事件流** ✅：
>    - 完善所有事件类型（`error`、`cancelled`、`ping`）
>    - 支持心跳机制（`HeartbeatManager`）
>    - 支持取消机制（`CancellationToken`）

**stop_reason 取值:**
- `completed`: 正常完成
- `max_iterations`: 达到最大迭代次数
- `cancelled`: 用户取消
- `error`: 发生错误

**错误事件示例:**

SSE 错误事件与 HTTP 错误响应使用统一格式:
```
event: message
data: {"type": "error", "error": {"code": "TOOL_TIMEOUT", "message": "Tool 'read_file' timed out after 30s", "details": {"recoverable": true}}}
```

**心跳机制:**

当连接空闲超过 15 秒时，服务端发送心跳事件保持连接：
```
event: message
data: {"type": "ping", "timestamp": "2024-01-15T10:30:15Z"}
```

客户端应忽略 `ping` 事件，无需特殊处理。心跳间隔默认 15 秒，可通过服务端配置调整。

### 5. 取消请求

> **✅ 实现状态：已完成**
> 
> 取消机制已实现以下功能：
> - `CancellationToken` 传递机制已实现
> - 工具调用前的取消检查点已实现
> - 取消后的资源清理逻辑已实现
> - 取消事件（`cancelled`）已实现

```
POST /api/v1/sessions/{session_id}/cancel
```

取消当前正在进行的请求。仅当会话状态为 `busy` 时可用。

**请求体:**
```json
{
    "reason": "User cancelled"  // 可选
}
```

**响应:**
```json
{
    "status": "cancelled",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "request_id": "req_abc123"
}
```

**错误响应:**
- `409 SESSION_NOT_BUSY`: 会话当前没有正在进行的请求

取消后，SSE 连接将收到 `cancelled` 事件并关闭：
```
event: message
data: {"type": "cancelled", "reason": "User cancelled"}

event: done
data: {}
```

### 6. 删除会话

```
DELETE /api/v1/sessions/{session_id}
```

**响应:**
```json
{
    "status": "deleted",
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 7. 列出所有会话

```
GET /api/v1/sessions
```

**查询参数:**
- `limit` (可选): 返回数量限制，默认 20
- `offset` (可选): 分页偏移，默认 0
- `status` (可选): 按状态过滤，可选值: `idle`, `busy`, `error`, `inactive`

**响应:**
```json
{
    "sessions": [
        {
            "session_id": "550e8400-e29b-41d4-a716-446655440000",
            "model": "deepseek-ai/DeepSeek-V3",
            "status": "active",
            "created_at": "2024-01-15T10:30:00Z",
            "message_count": 5
        }
    ],
    "total": 1,
    "limit": 20,
    "offset": 0
}
```

## 错误响应

所有错误遵循统一格式:

```json
{
    "error": {
        "code": "SESSION_NOT_FOUND",
        "message": "Session 550e8400-e29b-41d4-a716-446655440000 not found",
        "details": {}
    }
}
```

### 错误码

| HTTP 状态码 | 错误码 | 描述 |
|------------|--------|------|
| 400 | INVALID_REQUEST | 请求参数无效 |
| 400 | INVALID_REQUEST | 请求参数无效 |
| 404 | SESSION_NOT_FOUND | 会话不存在 |
| 409 | SESSION_INACTIVE | 会话已失效 |
| 409 | SESSION_BUSY | 会话正在处理请求 |
| 409 | SESSION_NOT_BUSY | 会话当前无请求可取消 |
| 500 | INTERNAL_ERROR | 内部服务器错误 |
| 503 | PROVIDER_ERROR | LLM 提供商错误 |

## SSE 事件类型

> 详见上方"发送消息（SSE 流式）"章节中的事件类型详解表。

### 客户端重连机制

SSE 连接断开后，客户端可使用 `Last-Event-ID` 请求头重连。服务端每个事件携带 `id` 字段：

```
id: evt_001
event: message
data: {"type": "content", "text": "Hello"}

id: evt_002
event: message
data: {"type": "content", "text": " world"}
```

重连后服务端从 `Last-Event-ID` 对应事件的下一个事件开始推送。若对应会话已结束，则返回 `done` 事件。

## 健康检查

### 服务健康状态

```
GET /api/v1/health
```

**响应:**
```json
{
    "status": "healthy",
    "version": "0.1.0",
    "timestamp": "2024-01-15T10:30:00Z"
}
```

**状态值:**
- `healthy`: 服务正常
- `degraded`: 服务降级（部分功能不可用）
- `unhealthy`: 服务不可用

### 服务就绪状态

```
GET /api/v1/ready
```

检查服务是否已准备好接收请求（包括数据库连接等）。

**响应 (就绪):**
```json
{
    "status": "ready",
    "checks": {
        "database": "ok"
    }
}
```

**响应 (未就绪):**
```json
{
    "status": "not_ready",
    "checks": {
        "database": "connection failed"
    }
}
```

## 速率限制

> 本 API 为内部服务，**不实施速率限制和配额管理**。调用方应自行控制请求频率，避免对下游 LLM 提供商造成过大压力。

## 监控和可观测性

> **注意：本 API 为内部服务，不实施监控和可观测性机制。** 调用方应自行实现日志记录和性能追踪。