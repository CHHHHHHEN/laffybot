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
cryptography>=48.0.0
```

加密密钥通过环境变量 `LAFFYBOT_ENCRYPTION_KEY` 设置，首次启动时必须配置。

## 会话状态与归档

会话具有以下状态：

| 状态 | 描述 | 允许的操作 |
|------|------|----------|
| `idle` | 空闲，无正在进行的请求 | 发送消息、获取历史、删除、归档 |
| `busy` | 正在处理请求 | 取消请求、获取信息 |
| `error` | 发生错误，需处理 | 获取历史、删除、归档 |

### 状态转换

```
idle -> busy     (发送消息)
busy -> idle     (请求完成)
busy -> error    (发生错误)
error -> idle    (重新发送消息)
```

### 归档

会话归档用于标记已完成对话并触发记忆提取。归档后会话仍可继续对话，但记忆提取只会在首次归档时触发一次。已归档会话的 `archived_at` 字段非空。

## 并发控制

**同一会话不支持并发请求。**

- 当会话状态为 `busy` 时，新的 `/stream` 请求将返回 `409 SESSION_BUSY` 错误
- 客户端应等待当前请求完成后再发送新请求
- 如需取消当前请求，使用取消接口（已实现）

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
    "max_iterations": 10
}
```

> 移除了 `model` 字段。模型由当前全局选中决定，创建会话时自动从 ProviderStore 解析 model_name 写入 session 快照。
>
> `system_prompt` 字段已移除。系统提示改为全局设置，可通过 `GET/PUT /api/v1/settings/system-prompt` 管理。

**响应:**
```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "model": "deepseek-ai/DeepSeek-V3",
    "status": "idle",
    "created_at": "2024-01-15T10:30:00Z"
}
```

`model` 字段仍存在于响应中，值为创建时从全局选中解析的快照，不会随后续切换而改变。

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
    "current_request_id": null,
    "archived_at": null
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
```

> `event: done\ndata: {}` 仅在请求异常终止（如会话状态错误）时作为终止信号发送。正常完成流以 `{"type": "done"}` 事件结束，无需额外的终止标记。

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
| `title_update` | 标题更新通知（全局事件） | `session_id`, `title` | - |

> **注意:** `reasoning` 事件由后端统一处理不同 LLM 提供商的思维链格式差异（如 DeepSeek 的 `reasoning_content` 字段），对外暴露统一的事件格式，客户端无需关心底层实现细节。

> **当前代码注记：** `laffybot/agent/heartbeat.py` 已提供 `HeartbeatManager` 和 `ping` 事件定义，但现有 `/sessions/{session_id}/messages` SSE 路径尚未接入自动心跳；`Last-Event-ID` 头也已被路由接收，但当前未用于事件重放。

**实现说明：**

> **当前实现状态**
> 
> 当前版本已实现核心流式链路，但心跳与断线重放仍是预留能力：
> 
> 1. **Phase 1 - 基础流式支持** ✅：
>    - `AgentRunner.run_stream()` 方法已实现
>    - 集成 `chat_completion_stream` 实现内容流式输出
>    - 支持 `session_start`、`content`、`reasoning`、`done` 事件
> 
> 2. **Phase 2 - 工具调用流式** ✅：
>    - 实现 `tool_call`、`tool_result` 事件
>    - 支持工具执行计时（`duration_ms`）
>    - 工具执行失败会以 `tool_result(success=false)` 形式返回
> 
> 3. **Phase 3 - 取消与错误处理** ✅：
>    - 支持 `error` 与 `cancelled` 事件
>    - 支持 `CancellationToken` 取消链路
>    - `ping` / `HeartbeatManager` 已实现为独立模块，但尚未接入当前 SSE 路径

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

> **设计详情**：心跳机制的详细设计参见 `heartbeat-design.md`。

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

取消后，SSE 连接将收到 `cancelled` 事件及 `done` 事件后关闭：
```
event: message
data: {"type": "cancelled", "reason": "User cancelled"}

event: message
data: {"type": "done", "stop_reason": "cancelled"}
```

### 6. 归档会话

```
POST /api/v1/sessions/{session_id}/archive
```

归档会话并触发记忆提取。归档后会话仍可继续对话，但记忆提取最多触发一次。已归档会话再次归档返回 `409 SESSION_ALREADY_ARCHIVED`。

若会话正在流式输出（status=busy），服务端会等待流式输出完成后自动归档，不会返回 `SESSION_BUSY`。

**响应:**
```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "model": "deepseek-ai/DeepSeek-V3",
    "status": "idle",
    "created_at": "2024-01-15T10:30:00Z",
    "message_count": 5,
    "current_request_id": null,
    "archived_at": "2024-01-15T11:00:00Z",
    "title_auto_generated": true
}
```

**错误响应:**
- `409 SESSION_ALREADY_ARCHIVED`: 会话已归档

### 6.5. 取消归档会话

```
POST /api/v1/sessions/{session_id}/unarchive
```

取消归档已归档的会话，将 `archived_at` 设为 `null`。

**响应:**
```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "model": "deepseek-ai/DeepSeek-V3",
    "status": "idle",
    "created_at": "2024-01-15T10:30:00Z",
    "message_count": 5,
    "current_request_id": null,
    "archived_at": null,
    "title_auto_generated": true
}
```

**错误响应:**
- `409 SESSION_BUSY`: 会话正在处理请求，无法取消归档
- `409 SESSION_NOT_ARCHIVED`: 会话未归档，无需取消归档

### 7. 系统提示设置

```
GET /api/v1/settings/system-prompt
```

**响应:**
```json
{
    "system_prompt": "You are a helpful assistant."
}
```

```
PUT /api/v1/settings/system-prompt
```

**请求体:**
```json
{
    "system_prompt": "You are a helpful assistant. Be concise."
}
```

**响应:**
```json
{
    "system_prompt": "You are a helpful assistant. Be concise."
}
```

> 系统提示为全局设置，对所有新会话生效。重启后恢复为默认值。
> 若已配置 `system_prompt_template`（config.json），模板将作为完整提示词，此处设置不生效。

### 8. 删除会话

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

> **注意：** 删除操作会从数据库中永久移除会话及其所有消息。

### 9. 列出所有会话

```
GET /api/v1/sessions
```

**查询参数:**
- `limit` (可选): 返回数量限制，默认 20
- `offset` (可选): 分页偏移，默认 0
- `status` (可选): 按状态过滤，可选值: `idle`, `busy`, `error`
- `archived` (可选): 按归档状态过滤，可选值: `true`, `false`

**响应:**
```json
{
    "sessions": [
        {
            "session_id": "550e8400-e29b-41d4-a716-446655440000",
            "model": "deepseek-ai/DeepSeek-V3",
            "status": "idle",
            "created_at": "2024-01-15T10:30:00Z",
            "message_count": 5,
            "archived_at": null
        }
    ],
    "total": 1,
    "limit": 20,
    "offset": 0
}
```

### 8. 提供商管理

提供商配置存储在数据库中，通过 API 进行管理。所有提供商端点位于 `/api/v1/providers` 下。

**列出所有提供商：**
```
GET /api/v1/providers
```

**响应:**
```json
[
    {
        "id": "siliconflow",
        "name": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "has_api_key": true,
        "created_at": "2024-01-15T10:30:00Z"
    }
]
```

**创建提供商：**
```
POST /api/v1/providers
```

**请求体:**
```json
{
    "name": "SiliconFlow",
    "base_url": "https://api.siliconflow.cn/v1",
    "api_key": "sk-...",
    "extra_headers": {}
}
```

api_key 在后端加密后存储，响应中不返回。

**获取提供商详情：**
```
GET /api/v1/providers/{id}
```

**响应:**
```json
{
    "id": "siliconflow",
    "name": "SiliconFlow",
    "base_url": "https://api.siliconflow.cn/v1",
    "has_api_key": true,
    "extra_headers": {},
    "created_at": "2024-01-15T10:30:00Z"
}
```

**更新提供商：**
```
PUT /api/v1/providers/{id}
```

api_key 为可选字段，不传时保留旧值。

**删除提供商：**
```
DELETE /api/v1/providers/{id}
```

级联删除其所有模型。若该提供商为当前全局选中，同时清除选中状态，响应体附加 `active_cleared: true` 标记。

**模型管理：**
```
GET    /api/v1/providers/{id}/models       # 列出模型
POST   /api/v1/providers/{id}/models       # 添加模型
DELETE /api/v1/providers/{id}/models/{mid}  # 删除模型
```

添加模型请求体：`{"name": "deepseek-ai/DeepSeek-V3"}`。同一提供商下模型名不可重复。

**连通性测试：**
```
POST /api/v1/providers/{id}/test
```

使用该提供商下第一个模型发送测试请求，验证连接是否正常。

**全局选中管理：**
```
GET /api/v1/providers/active    # 获取当前选中（无选中时返回 null）
PUT /api/v1/providers/active    # 设置当前选中
```

设置请求体：
```json
{
    "provider_id": "siliconflow",
    "model_id": "m_siliconflow_deepseek-ai_deepseek-v3"
}
```

全局选中决定新建会话和消息发送时使用的提供商和模型，切换即时生效。

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

### 9. 工具列表

```
GET /api/v1/tools
```

**响应:**
```json
[
    {
        "name": "read_file",
        "description": "Read file contents",
        "read_only": true,
        "enabled": true
    }
]
```

### 10. 全局事件通道

```
GET /api/v1/events
```

**描述:**

全局 SSE 端点，用于推送跨会话的实时事件。与消息流 SSE 分离，生命周期为应用级（页面打开期间持续存在）。

**响应类型:** `text/event-stream`

**事件类型:**

| 事件 | 格式 | 说明 |
|------|------|------|
| `ping` | `event: ping\ndata: {"type":"ping","timestamp":"..."}\n\n` | 心跳保活（每 15 秒） |
| `title_update` | `event: title_update\ndata: {"session_id":"xxx","title":"新标题"}\n\n` | 会话标题更新通知 |

**使用场景:**

- 标题生成完成后立即通知前端，无需轮询
- 用户切换会话后仍能接收任意会话的事件

**前端集成:**

- 应用启动时建立连接（`useGlobalEvents` hook）
- 断线自动重连（指数退避）
- 收到 `title_update` 时刷新 sessions 查询
[
    {
        "name": "read_file",
        "description": "Read a file (text, image, or document)...",
        "read_only": true
    },
    {
        "name": "write_file",
        "description": "Write content to a file...",
        "read_only": false
    }
]
```

返回当前注册的工具信息列表，仅用于展示。工具启停等管理功能待实现。

---

### 错误码

| HTTP 状态码 | 错误码 | 描述 |
|------------|--------|------|
| 400 | INVALID_REQUEST | 请求参数无效 |
| 400 | NO_ACTIVE_PROVIDER | 发送消息或创建会话时未选中全局提供商 |
| 404 | SESSION_NOT_FOUND | 会话不存在 |
| 404 | PROVIDER_NOT_FOUND | 提供商不存在 |
| 404 | MODEL_NOT_FOUND | 模型不存在 |
| 409 | SESSION_BUSY | 会话正在处理请求 |
| 409 | SESSION_NOT_BUSY | 会话当前无请求可取消 |
| 409 | SESSION_ALREADY_ARCHIVED | 会话已归档 |
| 409 | SESSION_NOT_ARCHIVED | 会话未归档 |
| 409 | SESSION_STATE_ERROR | 会话状态转换冲突 |
| 409 | MODEL_NAME_CONFLICT | 同一提供商下模型名重复 |
| 400 | TOOL_VALIDATION_ERROR | 工具参数校验失败 |
| 500 | INTERNAL_ERROR | 内部服务器错误 |
| 500 | PROVIDER_CONFIG_ERROR | 提供商配置错误（API Key 解密失败等） |
| 500 | TOOL_EXECUTION_ERROR | 工具执行异常 |
| 502 | PROVIDER_CONNECTION_ERROR | 连通性测试连接失败 |

## SSE 事件类型

> 详见上方"发送消息（SSE 流式）"章节中的事件类型详解表。

### 客户端重连机制

SSE 连接断开后，协议层保留了 `Last-Event-ID` 请求头和每个事件的 `id` 字段：

```
id: evt_001
event: message
data: {"type": "content", "text": "Hello"}

id: evt_002
event: message
data: {"type": "content", "text": " world"}
```

当前代码尚未实现基于 `Last-Event-ID` 的事件回放，因此断线续传属于设计预留能力，客户端需要按新的请求流程重新建立连接。

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