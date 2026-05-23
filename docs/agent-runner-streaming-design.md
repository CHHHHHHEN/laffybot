# AgentRunner 流式支持实现计划

> **✅ 实现状态：核心链路、心跳均已完成，断线重放仍为预留能力**
> 
> 本文档描述的核心流式链路已实现。实现代码位于：
> - `laffybot/agent_runtime/runner.py` - `AgentRunner.run_stream()` 方法
> - `laffybot/agent_runtime/events.py` - SSE 事件类型定义
> - `laffybot/agent_runtime/cancellation.py` - 取消机制
> - `laffybot/agent_runtime/heartbeat.py` - 心跳机制
> - `laffybot/agent_runtime/providers/types.py` - `StreamChunk` 和 `ToolCallDelta` 类型
> - `laffybot/agent_runtime/providers/base.py` - 流式回调接口
> - `laffybot/agent_runtime/providers/openai.py` - OpenAI Provider 流式实现

## 概述

本文档定义将 `AgentRunner` 修改为支持流式事件输出的规范和实现途径，以符合 `api.md` 中定义的 SSE 流式响应规范。

---

## 文档范围与性质

**本文档仅讨论高层设计和架构决策，不包含具体实现细节。**

实现细节将在后续的详细设计文档或代码注释中补充。本文档旨在为开发团队提供清晰的设计方向和决策依据。

### 包含内容

**设计层面**：
- 设计目标与架构决策
- 接口规范与数据流设计
- 错误处理策略与恢复机制

**功能范围**：
- `AgentRunner` 核心逻辑的流式改造
- 流式事件生成机制
- 工具调用流式支持
- 取消机制设计

### 不包含内容

**实现层面**：
- 具体代码实现
- 数据结构定义
- 算法细节
- 性能优化方案

**工程范围**：
- API 层实现（FastAPI 端点、SSE 响应封装、会话状态管理）
- 测试策略和测试用例设计
- 性能优化和资源管理（内存限制、超时设置）

---

## 规范定义

### 事件类型规范

根据 `api.md` 要求，`AgentRunner` 流式输出必须产生以下事件类型：

| 事件类型 | 触发时机 | 必需字段 | 可选字段 |
|---------|---------|---------|---------|
| `session_start` | 迭代开始 | `session_id` | `request_id` |
| `content` | LLM 输出文本片段 | `text` | - |
| `reasoning` | LLM 推理过程片段 | `text` | - |
| `tool_call` | 工具调用开始 | `tool_call_id`, `name`, `arguments` | `timeout_ms` |
| `tool_result` | 工具执行完成 | `tool_call_id`, `name`, `result`, `success` | `duration_ms`, `error_message` |
| `done` | 迭代结束 | `stop_reason` | `usage`, `tools_used` |
| `error` | 发生异常 | `error` (嵌套对象) | - |
| `cancelled` | 请求被取消 | `reason` | - |
| `ping` | 心跳事件 | `timestamp` | - |

### 事件顺序规范

**正常流程**：
```
session_start -> (content | reasoning)* -> [tool_call -> tool_result]+ -> done
```

**错误流程**：
```
session_start -> (content | reasoning)* -> error -> done
```

**取消流程**：
```
session_start -> (content | reasoning)* -> cancelled -> done
```

**多轮工具调用**：
```
session_start 
  -> content* 
  -> tool_call 
  -> tool_result 
  -> content* 
  -> tool_call 
  -> tool_result 
  -> ... 
  -> done
```

### stop_reason 规范

| 值 | 触发条件 |
|----|---------|
| `completed` | LLM 返回最终响应，无工具调用 |
| `max_iterations` | 达到 `max_iterations` 限制 |
| `error` | 发生异常 |
| `cancelled` | 用户取消请求 |

---

## 架构分析（实现后状态）

### 已完成组件

| 组件 | 位置 | 实现状态 |
|------|------|---------|
| `AgentRunner` | `laffybot/agent_runtime/runner.py` | ✅ 支持流式执行，`run_stream()` 方法 |
| `BaseProvider` | `laffybot/agent_runtime/providers/base.py` | ✅ 已定义 `chat_completion_stream()` 抽象方法 |
| `OpenAIProvider` | `laffybot/agent_runtime/providers/openai.py` | ✅ 已实现流式支持，支持 `reasoning_content` |
| `SSEEvent` | `laffybot/agent_runtime/events.py` | ✅ 完整事件类型定义 |
| `CancellationToken` | `laffybot/agent_runtime/cancellation.py` | ✅ 取消机制 |
| `HeartbeatManager` | `laffybot/agent_runtime/heartbeat.py` | ✅ 已实现并接入 SSE 路由 `_stream_session_events()` |
| `StreamChunk` | `laffybot/agent_runtime/providers/types.py` | ✅ 流式增量数据结构 |
| `ToolCallDelta` | `laffybot/agent_runtime/providers/types.py` | ✅ 工具调用增量结构 |

### 已实现流式能力

`OpenAIProvider.chat_completion_stream()` 已实现：
- ✅ 流式 chunk 收集和解析（`_parse_chunks()` 方法）
- ✅ `reasoning_content` 提取（支持 DeepSeek 等模型）
- ✅ 空闲超时保护（默认 90 秒，可通过 `LAFFYBOT_STREAM_IDLE_TIMEOUT_S` 配置）
- ✅ 工具调用流式解析
- ✅ 实时回调机制（通过 `on_chunk` 回调）

### 已解决的关键差距

1. **执行模式**：`AgentRunner.run_stream()` 是异步生成器 ✅
2. **事件输出**：完整的事件输出机制 ✅
3. **流式集成**：`chat_completion_stream()` 已在 `AgentRunner` 中使用 ✅
4. **工具追踪**：工具执行计时和状态追踪已实现 ✅
5. **取消机制**：请求取消和资源清理机制已实现 ✅
6. **心跳保活**：`HeartbeatManager` 已实现，并通过 `_stream_session_events()` 中的 `asyncio.wait_for` 集成到 SSE 路由

---

## 实现途径

### 核心接口变更

**新增方法**：
- `AgentRunner.run_stream()` - 流式执行 agent，产生 SSE 事件流 ✅

**新增数据结构**：
- `SSEEvent`：SSE 事件数据结构 ✅
- `StreamChunk`：流式增量数据 ✅
- `ToolCallDelta`：工具调用增量 ✅
- `CancellationToken`：取消令牌 ✅

**注意**：`ToolExecutionContext` 和 `ToolExecutionResult` 未单独实现，工具执行结果直接在 `run_stream()` 方法中处理。

### 实现阶段

#### Phase 1: 基础流式支持 ✅

**目标**：实现 `content` 和 `reasoning` 事件输出

**变更范围**：
- 新增 `laffybot/agent_runtime/events.py` - 事件类型定义 ✅
- 修改 `AgentRunner` - 添加 `run_stream()` 方法 ✅
- 集成 `provider.chat_completion_stream()` ✅

**规范要求**：
- 必须在迭代开始时产生 `session_start` 事件 ✅
- 必须将 LLM 流式输出转换为 `content` 事件 ✅
- 必须将 `reasoning_content` 转换为 `reasoning` 事件 ✅
- 必须在结束时产生 `done` 事件 ✅

#### Phase 2: 工具调用流式支持 ✅

**目标**：实现 `tool_call` 和 `tool_result` 事件输出

**变更范围**：
- 扩展 `run_stream()` 处理工具调用 ✅
- 添加工具执行追踪（直接在 `run_stream()` 中实现）✅

**规范要求**：
- 必须在工具执行前产生 `tool_call` 事件 ✅
- 必须在工具执行后产生 `tool_result` 事件 ✅
- `tool_result` 必须包含 `success` 状态和 `duration_ms` ✅
- 多工具调用必须顺序产生事件 ✅

#### Phase 3: 完整事件流 ✅

**目标**：实现错误处理和心跳机制

**变更范围**：
- 异常处理和 `error` 事件 ✅
- `ping` 事件和心跳组件已实现并接入 SSE 主流程 ✅
- 取消机制和 `cancelled` 事件 ✅

**错误分类与处理**：

| 错误类型 | 错误代码 | 处理策略 | 恢复行为 | 示例 |
|---------|---------|---------|---------|------|
| LLM 错误 | `LLM_ERROR` | 产生 error 事件 | 终止当前请求，返回 done 事件 | API 超时、速率限制 |
| 工具错误 | `TOOL_ERROR` | 产生 tool_result(success=false) | 将错误结果返回 LLM，继续下一轮迭代 | 文件未找到、路径越权 |
| 工具异常 | `TOOL_EXECUTION_ERROR` | raise ToolError → 被 AgentRunner 捕获 | 返回 tool_result(success=false, error_message)，继续迭代 | PermissionError, ValueError |
| 流式错误 | `STREAM_ERROR` | 关闭连接 | 立即终止，清理资源，不产生 done 事件 | 连接中断 |
| 内部错误 | `INTERNAL_ERROR` | 记录日志 | 终止当前请求，返回通用错误消息 | 代码 bug |
| 取消错误 | `CANCELLED` | 清理资源 | 产生 cancelled 事件，正常结束 | 用户取消 |

> **当前代码注记：** `AgentRunner.run_stream()` 直接发出的运行时 `error.code` 主要是 `LLM_ERROR` 和 `INTERNAL_ERROR`；工具执行异常会以 `tool_result(success=false)` 返回。`ToolError` 领域异常已定义并在 `ToolRegistry.execute()` 和 `app.py` 的 FastAPI 异常处理器中注册。

**错误恢复策略详解**：

1. **LLM 错误（`LLM_ERROR`）**
   - **恢复策略**：终止当前请求，不重试
   - **理由**：LLM 错误通常需要用户干预（如调整参数、检查 API 配置）
   - **事件流**：`error` -> `done` (stop_reason="error")
   - **资源清理**：无需特殊清理

2. **工具错误（`TOOL_ERROR`）**
   - **恢复策略**：将错误信息作为工具结果返回给 LLM，继续迭代
   - **理由**：LLM 可以根据错误信息调整策略或尝试其他工具
   - **事件流**：`tool_result` (success=false, error_message) -> 继续迭代
   - **示例**：
     ```
     tool_call -> [工具执行失败] -> tool_result(success=false, error_message="File not found")
     -> LLM 根据错误调整 -> content("Let me try a different approach...")
     ```

3. **流式错误（`STREAM_ERROR`）**
   - **恢复策略**：立即终止连接，不产生 `done` 事件
   - **理由**：连接已断开，无法发送后续事件
   - **资源清理**：取消所有进行中的任务，释放资源
   - **客户端处理**：客户端通过连接断开检测错误，应实现重连机制

4. **内部错误（`INTERNAL_ERROR`）**
   - **恢复策略**：终止请求，返回通用错误消息
   - **理由**：内部错误可能影响系统稳定性，不应继续
   - **日志记录**：记录完整堆栈信息，便于调试
   - **事件流**：`error` (code=INTERNAL_ERROR, message="Internal server error") -> `done`

5. **取消错误（`CANCELLED`）**
   - **恢复策略**：正常结束流程，产生 `cancelled` 事件
   - **理由**：用户主动取消，属于正常流程
   - **资源清理**：取消正在执行的工具，清理临时资源
   - **事件流**：`cancelled` -> `done` (stop_reason="cancelled")

**错误事件格式**：
```json
{
    "type": "error",
    "error": {
        "code": "TOOL_ERROR",
        "message": "Tool 'read_file' failed: FileNotFoundError",
        "details": {
            "tool_name": "read_file",
            "error_type": "FileNotFoundError",
            "recoverable": true
        }
    }
}
```

**心跳机制**：
- 默认间隔 15 秒（可通过环境变量 `LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S` 配置）
- 每次发送事件后重置心跳计时器
- 详细设计见「心跳机制设计」章节

**规范要求**：
- 异常必须转换为 `error` 事件，不应中断事件流
- `error` 事件后必须产生 `done` 事件（`stop_reason="error"`）
- 连接空闲超过 15 秒必须产生 `ping` 事件（通过 `_stream_session_events()` 中的 `asyncio.wait_for` 实现）

---

---

## 流式回调机制改造

### 概述

当前 `BaseProvider.chat_completion_stream()` 的 `on_chunk` 回调仅接收 `str` 类型，无法传递 `reasoning_content` 和工具调用增量信息。需要改造回调协议以支持完整的事件流。

### 当前接口

```python
async def chat_completion_stream(
    self,
    messages: list[dict[str, Any]],
    model: str,
    on_chunk: Callable[[str], Awaitable[None]],  # 仅接收 str
    ...
) -> LLMResponse:
```

### 改造方案

**新增数据结构**：

| 结构 | 用途 | 关键字段 |
|------|------|----------|
| `StreamChunk` | 流式增量数据 | `content`, `reasoning`, `tool_call_delta` |
| `ToolCallDelta` | 工具调用增量 | `index`, `id`, `name`, `arguments_delta` |

**新回调签名**：

```python
async def on_chunk(chunk: StreamChunk) -> None:
    # chunk.content: str | None - 文本增量
    # chunk.reasoning: str | None - 推理增量
    # chunk.tool_call_delta: ToolCallDelta | None - 工具调用增量
```

### 改造范围

| 组件 | 改造内容 | 状态 |
|------|----------|------|
| `BaseProvider` | 更新 `chat_completion_stream()` 抽象方法签名 | ✅ |
| `OpenAIProvider` | 实现新回调协议，解析增量数据并调用回调 | ✅ |
| `AgentRunner` | 实现 `on_chunk` 回调，生成 `content`/`reasoning` 事件 | ✅ |

### 兼容性策略

- **不保留向后兼容**：直接修改接口签名 ✅
- 所有调用方必须适配新回调协议 ✅

---

## 取消机制设计

### 概述

取消机制允许客户端中断正在进行的请求，需要实现以下能力：
- 立即停止事件流输出
- 中断正在执行的工具调用
- 清理临时资源（文件、网络连接等）
- 产生 `cancelled` 事件通知客户端

### 核心组件

| 组件 | 职责 | 状态 |
|------|------|------|
| `CancellationToken` | 取消状态管理，支持检查和触发取消 | ✅ |
| `CancelledError` | 取消异常类 | ✅ |

**注意**：`CancellableContext` 和 `CancellationScope` 未单独实现，取消逻辑直接在 `run_stream()` 方法中处理。

### 取消传播路径

```
API 层 (收到取消请求)
    ↓
CancellationToken.cancel(reason)
    ↓
AgentRunner.run_stream() (检查取消状态)
    ↓
工具执行 (传递 CancellableContext)
    ↓
资源清理 (CancellationScope)
```

### 取消检查点

| 检查点位置 | 检查时机 | 处理方式 |
|-----------|---------|----------|
| 迭代开始 | 每轮迭代前 | 抛出 `CancelledError` |
| LLM 请求前 | 调用 Provider 前 | 抛出 `CancelledError` |
| 工具执行前 | 每个工具调用前 | 抛出 `CancelledError` |
| 工具执行中 | 长时间操作中 | 工具自行检查并中断 |

### 资源清理策略

**清理时机**：
- 取消触发后立即执行清理
- 清理完成后才产生 `cancelled` 事件

**清理职责**：
- `AgentRunner`：清理消息历史中的临时数据
- `Tool`：清理工具创建的临时资源（文件、连接等）
- `CancellationScope`：确保清理逻辑即使异常也会执行

### 与 asyncio 的集成

- 使用 `asyncio.CancelledError` 作为取消信号
- `CancellationToken.check()` 在取消时抛出 `CancelledError`
- 捕获 `CancelledError` 后执行清理，再产生 `cancelled` 事件

---

## 心跳机制设计

### 概述

心跳机制用于在连接空闲时保持 SSE 连接活跃，防止中间代理（如 Nginx、负载均衡器）因超时断开连接。

### 配置参数

| 参数 | 默认值 | 环境变量 |
|------|--------|----------|
| 心跳间隔 | 15 秒 | `LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S` |
| 最小间隔 | 5 秒 | - |

### 核心组件

| 组件 | 职责 | 状态 |
|------|------|------|
| `HeartbeatManager` | 管理心跳计时器，生成 `ping` 事件 | ✅ 已实现，已通过 SSE 路由 `_stream_session_events()` 接入 |

**注意**：`EventEmitter` 未单独实现，心跳重置逻辑通过 `HeartbeatManager.reset()` 方法调用。

### 工作流程

```
[事件发送] → 重置计时器 → [空闲等待]
                ↑              ↓
                └── [超时?] ← ──┘
                      ↓ 是
                [发送 ping 事件]
```

### 心跳与事件流的协调

**原则**：
- 心跳事件不应与内容事件竞争
- 有内容事件时，心跳计时器自动重置
- 仅在真正空闲时发送心跳

**实现方式**：
- 使用 `asyncio.Event` 作为计时器重置信号
- 每次发送事件后设置事件，重置等待
- 等待超时则发送 `ping` 事件

### 心跳事件格式

```json
{
    "type": "ping",
    "timestamp": "2024-01-15T10:30:15Z"
}
```

### 与流式输出的集成

- `HeartbeatManager` 作为独立组件已实现 ✅
- SSE 路由 `_stream_session_events()` 中使用 `asyncio.wait_for()` 在每次事件后等待 15s 空闲超时，超时则发送 `ping` 事件 ✅
- 流结束时通过 `finally` 块调用 `heartbeat.stop()` 清理 ✅

---

## Usage 统计的流式累积机制

### 概述

在多轮迭代场景下，`done` 事件的 `usage` 字段需要累积所有迭代的 token 使用量，以反映整个请求的资源消耗。

### 累积规则

**累积字段**：
- `prompt_tokens`: 所有迭代的输入 token 总和
- `completion_tokens`: 所有迭代的输出 token 总和
- `total_tokens`: `prompt_tokens + completion_tokens`
- `cached_tokens`: 缓存命中 token 总和（如果 Provider 支持）

**累积时机**：
- 每次 LLM 响应后立即累积到当前请求的 `usage` 统计中
- 在 `done` 事件中返回累积后的总值

### Provider 支持差异

不同 LLM Provider 对 usage 统计的支持程度不同：

| Provider | 流式 Usage 支持 | 特殊处理 |
|----------|----------------|----------|
| OpenAI | ✅ 完全支持 | 需要 `stream_options={"include_usage": true}` |
| DeepSeek | ✅ 完全支持 | - |
| Anthropic | ⚠️ 部分支持 | 流式响应可能不包含 usage |
| 本地模型 | ❌ 不支持 | 无法获取 token 统计 |

**降级策略**：
- 如果 Provider 不返回 usage 信息，`done` 事件的 `usage` 字段应为空或省略
- 不应伪造或估算 usage 数据
- 客户端应能够处理缺失的 usage 字段

### Reasoning Content 处理

**设计决策**：
- **不统计 `reasoning_tokens`**：仅按照 OpenAI 标准统计 `prompt_tokens`、`completion_tokens`、`total_tokens`
- Provider 返回的 `reasoning_tokens` 字段（如 DeepSeek）将被忽略
- `reasoning_content` 的 token 已包含在 `completion_tokens` 中，无需额外处理
- 客户端无需关心 reasoning 的 token 计数细节

### 缓存 Token 的处理

**缓存命中场景**：
- 如果 Provider 支持 prompt caching（如 Anthropic），会返回 `cached_tokens`
- `cached_tokens` 应累加到总缓存统计中
- `cached_tokens` 不应从 `prompt_tokens` 中扣除（两者是独立统计）

### 其他 Provider 特殊字段

**忽略策略**：
- Provider 返回的非 OpenAI 标准字段（如 `reasoning_tokens`、`prompt_tokens_details` 等）将被忽略
- 仅保留标准字段：`prompt_tokens`、`completion_tokens`、`total_tokens`、`cached_tokens`
- 这样可以确保不同 Provider 的 usage 统计格式一致，便于客户端处理

### 设计约束

1. **准确性优先**：只报告 Provider 实际返回的 usage 数据，不估算
2. **实时累积**：每次 LLM 响应后立即累积，避免丢失数据
3. **容错处理**：如果某次迭代缺少 usage，继续累积其他迭代的数据
4. **字段可选**：`usage` 字段在 `done` 事件中是可选的，客户端必须处理缺失情况

---

## 日志记录

### 日志策略

使用 **loguru** 记录关键操作日志，遵循以下原则：
- **不记录敏感信息**：用户消息内容、工具参数等敏感数据不应记录
- **结构化日志**：使用 `logger.bind()` 添加上下文信息
- **异常日志**：使用 `logger.exception()` 记录异常堆栈

### 日志事件

**会话生命周期**：
- 会话创建（session_id, model, created_at）
- 会话删除（session_id, deleted_at）

**请求处理**：
- 请求开始（session_id, request_id, timestamp）
- 请求完成（session_id, request_id, stop_reason, duration_ms）
- 请求错误（session_id, request_id, error_code, error_message）

**工具调用**：
- 工具调用开始（tool_name, tool_call_id）
- 工具调用完成（tool_name, tool_call_id, duration_ms, success）
- 工具调用错误（tool_name, tool_call_id, error_type, error_message）

**取消操作**：
- 请求被取消（session_id, request_id, reason）

---

## 迁移策略

### 彻底迁移 ✅

本计划采用彻底迁移策略，不保留向后兼容：

1. **删除同步接口**：移除 `AgentRunner.run()` 方法 ✅
2. **统一使用流式接口**：所有调用方必须使用 `run_stream()` ✅
3. **API 层调整**：所有端点必须适配流式响应 ✅
4. **一次性迁移**：不提供过渡期，直接切换到新接口 ✅

**迁移影响**：
- 现有调用方需要修改为异步流式处理 ✅
- 需要更新所有测试用例 ✅
- API 响应格式统一为 SSE 流式 ✅

**优势**：
- 避免维护两套接口的复杂性 ✅
- 统一代码风格和错误处理 ✅
- 减少技术债务 ✅
