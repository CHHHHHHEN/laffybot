# SessionManager 架构设计文档

> **文档范围说明**：本文档专注于 SessionManager 的架构设计、接口定义和核心职责。
> 
> **本文档不包含以下内容**：
> - 测试策略和测试用例（参见测试代码）
> - 性能监控、指标采集和可观测性（**不在本项目范围内**）
> - 具体实现细节（参见源代码实现）
> 
> **部署约束**：本文档仅考虑单实例部署，不支持多实例水平扩展。

## 实现状态总览

| 功能模块 | 实现状态 | 实现文件 |
|---------|---------|----------|
| SessionManager 核心 | ✅ 已实现 | `laffybot/session/manager.py` |
| SessionStore 接口 | ✅ 已实现 | `laffybot/session/store.py` |
| SQLiteStore 实现 | ✅ 已实现 | `laffybot/session/store.py:SQLiteStore` |
| SQLiteStore 取消归档 | ✅ 已实现 | `laffybot/session/store.py:SQLiteStore.unarchive_session` |
| SessionInfo 数据结构 | ✅ 已实现 | `laffybot/session/models.py` |
| ContextBuilder 集成 | ✅ 已实现 | `laffybot/session/manager.py` → `_build_messages` |
| CancellationToken | ✅ 已实现 | `laffybot/agent/cancellation.py` |
| 并发控制 (asyncio.Lock) | ✅ 已实现 | `laffybot/session/manager.py` → `_locks` |
| Token 元数据持久化 | ✅ 已实现 | `laffybot/session/store.py` → `save_message` |
| 异常定义（含 SessionNotArchivedError） | ✅ 已实现 | `laffybot/session/errors.py` |
| 自动归档策略（max_active_sessions） | ✅ 已实现 | `laffybot/session/manager.py:_auto_archive_excess_sessions` |
| ProviderStore 接口 | ✅ 已实现 | `laffybot/session/provider_store.py` |
| SQLiteProviderStore 实现 | ✅ 已实现 | `laffybot/session/provider_store.py:SQLiteProviderStore` |

## 概述

SessionManager 是 Laffybot API 的核心组件，负责管理会话生命周期、状态转换和请求调度。它作为 API 层与 Agent 执行层之间的协调器，确保会话状态一致性和并发安全。

## 架构位置

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Routes                    │
└──────┬──────────────────────────────────┬───────────┘
       │                                  │
       v                                  v
┌──────────────────┐          ┌──────────────────────┐
│  SessionStore     │          │  ProviderStore       │
│  (会话 & 消息)     │          │  (提供商 & 模型 &     │
│                   │          │   活跃选中)           │
└─────────┬─────────┘          └──────────┬───────────┘
          │                               │
          v                               v
┌─────────────────────────────────────────────────────┐
│                  SessionManager                      │  ← 本文档核心（单例）
│  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │ SessionStore    │  │ ProviderStore            │  │
│  │ 注入: 持久化     │  │ 注入: 配置读取+解密      │  │
│  └─────────────────┘  └──────────────────────────┘  │
│  ┌─────────────────┐                                │
│  │ ContextBuilder  │  构建层：上下文组装             │
│  └─────────────────┘  （参见 context-builder-design.md）│
└───────────────────────┬─────────────────────────────┘
                        │
                        v
┌─────────────────────────────────────────────────────┐
│                  AgentRunner                         │  ← 按请求创建
└─────────────────────────────────────────────────────┘
```

**设计决策：**
- **SessionManager 单例**：整个应用只有一个 SessionManager 实例，管理所有会话 ✅
- **AgentRunner 按需创建**：每次请求创建新的 AgentRunner 实例，Provider 运行时从 ProviderStore 获取配置后直接实例化 ✅
- **SessionStore 依赖注入**：SessionStore 作为依赖注入，支持不同存储后端 ✅
- **ProviderStore 依赖注入**：ProviderStore 作为依赖注入，管理提供商配置读取、解密和活跃选中 ✅
- **ContextBuilder 集成**：SessionManager 通过依赖注入使用 ContextBuilder 组件 ✅（已实现，参见 `context-builder-design.md`）

## 核心职责

### 1. 会话生命周期管理
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/session/manager.py`

创建、获取、删除、列出会话 ✅

归档、取消归档、自动归档 ✅

### 2. 状态管理
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/session/manager.py`, `laffybot/session/store.py`

状态转换验证 ✅、并发控制 ✅、状态持久化 ✅

### 3. 请求调度
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/session/manager.py:send_message`

消息发送协调 ✅、取消请求处理 ✅、错误恢复 ✅

### 4. 上下文构建
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/session/manager.py:_build_messages`, `laffybot/context/builder.py`

历史消息查询 ✅、系统提示组装 ✅、完整上下文构建 ✅

**实现说明**：已提取为独立的 `ContextBuilder` 组件，SessionManager 通过依赖注入使用。

### 5. 资源管理
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/session/manager.py`

AgentRunner 实例管理（按需创建）✅、CancellationToken 生命周期 ✅

> **注意**：SSE 连接的心跳机制由独立的 HeartbeatManager 处理（参见 `heartbeat-design.md`），不属于 SessionManager 职责。健康检查端点由 API 层直接处理，也不属于 SessionManager 职责。

## 接口设计

### 核心数据结构

#### SessionInfo
会话元数据，包含会话的基本信息。

**字段：**
- `session_id: str` - 会话唯一标识符
- `model: str` - LLM 模型标识符
- `status: SessionStatus` - 会话状态，类型为 `Literal["idle", "busy", "error"]`
- `created_at: datetime` - 创建时间
- `updated_at: datetime` - 最后更新时间
- `message_count: int` - 消息数量
- `current_request_id: str | None` - 当前请求 ID（可选）
- `error_message: str | None` - 错误信息（可选）
- `system_prompt: str | None` - 系统提示词（可选）
- `max_iterations: int` - Agent 最大迭代次数，默认 50
- `archived_at: datetime | None` - 归档时间（可选），非空表示已归档

> **注意：** 实现使用 `@dataclass(slots=True)` 装饰器，`updated_at`、`system_prompt`、`max_iterations` 字段为设计文档新增。

#### SendMessageResult
> **注意：** 此数据结构在当前实现中不存在。`send_message()` 直接返回 `AsyncGenerator[SSEEvent, None]`，session_id 和 request_id 通过 `session_start` 事件传递。

### SessionStore 接口

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/session/store.py:SessionStore`

SessionStore 是会话持久化存储的抽象接口，支持不同的存储后端实现。

#### create_session
创建新会话记录。✅ 已实现

**签名：**
```python
async def create_session(
    self,
    session_id: str,
    model: str,
    system_prompt: str | None,
    max_iterations: int,
) -> SessionInfo
```

**返回：** 创建的 SessionInfo 实例

**注意：** `session_id` 由 SessionManager 生成（UUID），传入 Store 层持久化

#### get_session
获取会话信息。

**签名：**
```python
async def get_session(self, session_id: str) -> SessionInfo
```

**返回：** SessionInfo 实例

**异常：** `SessionNotFoundError`

#### update_session_status
更新会话状态。

**签名：**
```python
async def update_session_status(
    self,
    session_id: str,
    status: SessionStatus,
    current_request_id: str | None = None,
    error_message: str | None = None,
    expected_status: SessionStatus | None = None,
) -> bool
```

**参数：** `expected_status` - 乐观锁参数，指定期望的当前状态。如果提供，仅在当前状态匹配时才更新

**返回：** 是否更新成功

**异常：** `SessionNotFoundError` - 会话不存在；`SessionStateError` - 乐观锁冲突（expected_status 不匹配当前状态）

使用原子操作确保并发安全，支持乐观锁（检查当前状态后更新）。

#### archive_session
归档会话（设置 `archived_at` 时间戳）。

**签名：**
```python
async def archive_session(self, session_id: str) -> SessionInfo
```

**返回：** 归档后的 SessionInfo 实例（`archived_at` 字段非空）

**异常：** `SessionNotFoundError`

#### unarchive_session
取消归档会话（将 `archived_at` 设为 NULL）。

**签名：**
```python
async def unarchive_session(self, session_id: str) -> SessionInfo
```

**返回：** 取消归档后的 SessionInfo 实例（`archived_at` 为 NULL）

**异常：** `SessionNotFoundError`

#### delete_session
删除会话及其所有消息。

**签名：**
```python
async def delete_session(self, session_id: str) -> None
```

**异常：** `SessionNotFoundError`

#### list_sessions
列出会话。

**签名：**
```python
async def list_sessions(
    self,
    status: SessionStatus | None = None,
    archived: bool | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by_asc: bool = False,
) -> tuple[list[SessionInfo], int]
```

**参数：** `status` - 可选的状态过滤；`archived` - 可选，`True` 仅返回已归档，`False` 仅返回未归档，`None` 返回全部；`order_by_asc` - 可选，按 `updated_at` 升序排序（用于自动归档策略查找最旧会话）

**返回：** (会话列表, 总数) 元组

**排序：** 默认按 `updated_at DESC, session_id DESC` 排序；`order_by_asc=True` 时按 `updated_at ASC, session_id ASC` 排序

#### save_message
保存消息到会话历史。

**签名：**
```python
async def save_message(
    self,
    session_id: str,
    role: MessageRole,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> SessionMessage
```

**类型：** `MessageRole = Literal["user", "assistant", "system", "tool"]`；`SessionMessage = dict[str, Any]`

**返回：** 保存的消息字典（包含 role、content、timestamp，可选 metadata）

**异常：** `SessionNotFoundError` - 会话不存在（外键约束违反）

#### get_messages
获取会话消息历史。

**签名：**
```python
async def get_messages(
    self,
    session_id: str,
    limit: int = 50,
    before: datetime | None = None,
) -> list[SessionMessage]
```

**参数：** `before` - 可选，获取此时间之前的消息（用于分页）

**返回：** 消息字典列表（按时间正序）

**排序：** 按 `timestamp ASC, id ASC` 排序，确保相同时间戳的消息按插入顺序

**异常：** `SessionNotFoundError` - 会话不存在（结果为空时验证）

**消息格式：**
```python
{
    "role": "user" | "assistant" | "system" | "tool",
    "content": "消息内容",
    "timestamp": "2024-01-15T10:30:00Z",  # ISO 8601 格式
    "metadata": {}  # 可选，工具调用信息等
}
```

> **注意：** 实际实现中，metadata 仅在非 None 时包含在返回字典中

#### get_message_count
获取会话消息数量。

**签名：**
```python
async def get_message_count(self, session_id: str) -> int
```

**返回：** 消息总数

### SessionManager 接口

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/session/manager.py:SessionManager`

#### 初始化
```python
def __init__(
    self,
    store: SessionStore,
    provider_store: ProviderStore,
    tool_registry: ToolRegistry,
    context_config: ContextConfig | None = None,
    context_builder: ContextBuilder | None = None,
    memory_manager: MemoryManager | None = None,
    max_active_sessions: int = 3,
) -> None
```

**参数：** `store` - 会话持久化存储；`provider_store` - 提供商配置存储；`tool_registry` - 工具注册表；`context_config` - 上下文构建配置（可选）；`context_builder` - ContextBuilder 实例（可选，支持依赖注入）；`memory_manager` - 记忆管理器（可选）；`max_active_sessions` - 活跃会话数量上限，超限时自动归档最旧的（默认 3）

> 移除了 `provider_factory` 参数。Provider 不再由外部工厂函数创建，改由 SessionManager 运行时从 ProviderStore 获取配置后直接实例化。

#### create_session
创建新会话。创建后异步触发自动归档检查：若活跃会话数超过 `max_active_sessions`，自动归档最旧的会话。

**签名：**
```python
async def create_session(
    self,
    max_iterations: int = 50,
    provider_id: str | None = None,
    model_name: str | None = None,
) -> SessionInfo
```

**参数：** `max_iterations` - Agent 最大迭代次数；`provider_id` / `model_name` - 可选，指定提供商和模型，未指定时从默认配置读取

**返回：** SessionInfo 实例

**异常：** `NoActiveProviderError` - 未配置默认模型

> 移除了 `model` 参数。模型名称由 SessionManager 内部从 ProviderStore.get_active_selection() 解析，作为快照写入 session。

#### get_session_info
获取会话信息。

**签名：**
```python
async def get_session_info(self, session_id: str) -> SessionInfo
```

**参数：** `session_id` - 会话标识符

**返回：** SessionInfo 实例

**异常：** `SessionNotFoundError` - 会话不存在

#### send_message
发送消息并流式返回 Agent 响应。

**签名：**
```python
async def send_message(
    self,
    session_id: str,
    content: str,
) -> AsyncGenerator[SSEEvent, None]
```

**参数：** `session_id` - 会话标识符；`content` - 用户消息内容

**返回：** SSEEvent 异步生成器

**异常：** `SessionNotFoundError` - 会话不存在；`SessionBusyError` - 会话忙碌

**事件序列：** `session_start -> (content | reasoning)* -> [tool_call -> tool_result]+ -> done`

#### cancel_request
取消当前请求。

**签名：**
```python
async def cancel_request(
    self,
    session_id: str,
    reason: str | None = None,
) -> str
```

**参数：** `session_id` - 会话标识符；`reason` - 可选的取消原因

**返回：** 被取消的 request_id

**异常：** `SessionNotFoundError` - 会话不存在；`SessionNotBusyError` - 会话不忙碌

#### get_history
> **注意：** 此方法在当前实现中不存在。历史消息通过 `SessionStore.get_messages()` 直接获取，由 `ContextBuilder.build_messages()` 处理。✅ 已实现

**计划签名：**
```python
async def get_history(
    self,
    session_id: str,
    max_messages: int | None = None,
    max_tokens: int | None = None,
) -> list[dict[str, Any]]
```

**参数：** `session_id` - 会话标识符；`max_messages` - 可选，最大消息数量限制；`max_tokens` - 可选，最大 token 数量限制

**返回：** 消息列表（包含 role、content、timestamp）

**异常：** `SessionNotFoundError` - 会话不存在

**实现说明**：此功能已在 `ContextBuilder` 组件中实现，参见 `context-builder-design.md`。

#### archive_session
归档会话并触发记忆提取。若会话忙碌（流式输出中），等待流式输出完成后再归档。

**签名：**
```python
async def archive_session(self, session_id: str) -> SessionInfo
```

**参数：** `session_id` - 会话标识符

**返回：** 归档后的 SessionInfo 实例

**异常：** `SessionNotFoundError` - 会话不存在；`SessionAlreadyArchivedError` - 会话已归档

> busy 时不再返回 `SessionBusyError`，改用 asyncio.Lock 等待流式完成。

#### unarchive_session
取消归档已归档的会话（将 `archived_at` 设为 NULL）。

**签名：**
```python
async def unarchive_session(self, session_id: str) -> SessionInfo
```

**参数：** `session_id` - 会话标识符

**返回：** 取消归档后的 SessionInfo 实例

**异常：** `SessionNotFoundError` - 会话不存在；`SessionBusyError` - 会话忙碌；`SessionNotArchivedError` - 会话未归档

#### delete_session
删除会话。

**签名：**
```python
async def delete_session(self, session_id: str) -> None
```

**参数：** `session_id` - 会话标识符

**异常：** `SessionNotFoundError` - 会话不存在；`SessionBusyError` - 会话忙碌（无法删除）

#### list_sessions
列出会话。

**签名：**
```python
async def list_sessions(
    self,
    status: SessionStatus | None = None,
    archived: bool | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by_asc: bool = False,
) -> tuple[list[SessionInfo], int]
```

**参数：** `status` - 可选的状态过滤；`archived` - 可选，`True` 仅返回已归档，`False` 仅返回未归档，`None` 返回全部；`limit` - 最大返回会话数；`offset` - 分页偏移；`order_by_asc` - 按 updated_at 升序排序（用于自动归档）

**返回：** (会话列表, 总数) 元组

## 异常定义

### SessionError
所有会话相关异常的基类。

**属性：** `session_id: str` - 相关会话 ID

### SessionNotFoundError
会话不存在。

**继承：** SessionError

### SessionBusyError
会话正在处理请求。

**继承：** SessionError

**属性：** `request_id: str | None` - 当前请求 ID

### SessionNotBusyError
会话不忙碌，无法取消。

**继承：** SessionError

### SessionAlreadyArchivedError
会话已归档，无法再次归档。

**继承：** SessionError

### SessionNotArchivedError
会话未归档，无法取消归档。

**继承：** SessionError

### SessionStateError
会话状态无效。

**继承：** SessionError

**属性：** `current_status: str` - 当前状态

## 与 AgentRunner 协作模式

### 协作关系概述

SessionManager 与 AgentRunner 采用**协调器-执行器**模式：
- **SessionManager（协调器）**：负责会话状态管理、请求调度、资源协调
- **AgentRunner（执行器）**：负责具体的 Agent 执行逻辑和流式事件生成

**协作流程：**
```
SessionManager.send_message()
    ├─ 状态检查 → 更新状态为 busy
    ├─ ProviderStore.get_active_selection()  → 获取全局选中
    ├─ ProviderStore.get_provider_config()   → 获取解密配置
    ├─ 创建 CancellationToken
    ├─ 构造 AgentRunSpec（消息历史 + 配置，model=全局选中.model_name）
    ├─ OpenAIProvider(config) → AgentRunner
    ├─ 调用 AgentRunner.run_stream()
    ├─ 转发 SSE 事件流
    └─ 完成后更新状态为 idle/error
```

### AgentRunner 实例管理

每次请求创建新的 AgentRunner 实例，Provider 由 SessionManager 运行时从 ProviderStore 获取解密配置后直接实例化。AgentRunner 内部状态无共享，支持并发调用。

**设计理由**：
- **配置来源透明**：ProviderStore 封装配置查找和 API Key 解密，AgentRunner 和 ProviderFactory 无需感知
- **运行时即时生效**：每次发送消息时重新读取全局选中和提供配置，切换提供商或模型即时生效
- **资源开销可控**：AgentRunner 本身轻量，主要资源在 Provider 连接层

### 消息格式转换

#### 转换层次
```
API 层消息格式 → SessionManager 转换 → 存储格式（SessionStore） → _build_messages() 构建 → AgentRunner 消息格式（AgentRunSpec）
```

#### 转换职责
- **API → 存储**：添加时间戳、元数据，持久化用户消息
- **存储 → AgentRunner**：_build_messages() 加载历史消息，构造完整的对话上下文（当前实现，未来计划提取为 ContextBuilder）
- **AgentRunner → 存储**：保存助手回复、工具调用记录

#### 设计原则
职责分离（存储层只关心消息增删查改，构建层只关心上下文组装）、可替换性（更换存储后端不影响提示构建逻辑）、可测试性（存储和构建可独立测试）、历史完整性（确保 AgentRunner 获得完整对话上下文）、存储一致性（消息按时间顺序持久化，支持重放）。

### SSE 事件流传递

#### 传递策略
SessionManager 作为透明转发层，直接转发 AgentRunner 生成的事件，不修改事件内容和顺序，在特定事件点执行状态更新。

#### 事件处理职责

| 事件类型 | SessionManager 职责 |
|---------|-------------------|
| `session_start` | 记录 request_id，更新会话状态为 busy |
| `content` | 累积助手回复内容（用于保存历史） |
| `tool_call` | 记录工具调用（可选：审计日志） |
| `tool_result` | 记录工具结果（可选：审计日志） |
| `done` | 保存完整助手消息到历史，更新状态为 idle |
| `error` | 记录错误信息，更新状态为 error |
| `cancelled` | 清理部分完成的消息，更新状态为 idle |

#### 取消后消息处理
取消后丢弃部分生成的助手消息，保留已持久化的用户消息，会话状态恢复为 idle。

**理由**：保持历史完整性，避免不完整对话导致后续请求混乱；简化实现，无需处理部分消息状态标记。详见下文「取消机制设计」章节。

### 执行流程编排

#### 正常执行流程（闭环设计）
```
1. 获取会话信息 → 检查会话是否存在、状态是否为 idle、模型是否有效
2. 构建上下文 → 调用 _build_messages() 内部方法，调用 SessionStore.get_messages() 获取历史，返回完整消息列表（系统提示 + 历史 + 当前消息）
3. 执行 LLM → 生成 request_id、创建 CancellationToken、更新会话状态为 busy、保存用户消息、创建 AgentRunner 实例、调用 AgentRunner.run_stream(request_id=...)（request_id 透传给 run_stream，确保 session_start 事件的 request_id 与会话记录一致）、转发 SSE 事件
4. 保存结果 → 保存助手消息、更新消息计数、更新会话状态为 idle
```

> **注意：** 当前上下文构建在 SessionManager 内部实现，未来计划提取为独立的 ContextBuilder 组件。

严格遵循"存储 → 查询 → 构建 → 执行 → 存储"的处理流程，形成可预测的数据流和生命周期，简化调试，为中间步骤的 Hook 提供明确插入点，便于监控和追踪。

#### 异常处理策略
```
Agent 执行异常
├─ LLM API 错误
│  ├─ 可重试错误（速率限制、临时故障）→ 等待后重试（最多 N 次）
│  └─ 不可重试错误（认证失败、模型不可用）→ 更新状态为 error，返回 error 事件
├─ 工具执行错误 → 由 AgentRunner 处理，返回 tool_result(success=false)
└─ 内部错误 → 记录日志，更新状态为 error，返回 error 事件
```

### 取消机制设计

#### CancellationToken 设计

**数据结构**：`_cancelled: bool`（取消标志，私有字段）、`_reason: str | None`（取消原因，私有字段）

**核心操作**：
- `cancel(reason)`：标记为已取消，记录取消原因
- `check()`：检查是否已取消，如果已取消则抛出 `CancelledError`
- `is_cancelled`（属性）：检查是否已取消，返回 bool
- `reason`（属性）：获取取消原因

**设计要点**：
- 轻量级实现，无异步开销
- 使用 `@dataclass(slots=True)` 优化内存和性能
- 线程安全（单实例部署，无跨线程访问）
- 无回调机制，由调用方主动检查（`check()` 方法）

#### 协调流程
```
用户调用 cancel_request() → SessionManager 获取会话锁 → 验证状态为 busy → 获取 CancellationToken → 调用 token.cancel(reason) → 返回 request_id
AgentRunner 执行中 → 在检查点调用 token.check() → 检测到取消 → 抛出 CancelledError → SessionManager 捕获并生成 cancelled 事件
```

> **注意：** 实际实现中，AgentRunner 调用 `token.check()` 方法（会抛出异常），而不是检查 `token.is_cancelled` 属性。

#### 检查点机制

**AgentRunner 检查点位置**：
- 迭代循环开始（每次迭代前）
- LLM API 调用前（在 `_request_model_stream_with_events` 方法开始时）
- 工具调用前（每个工具执行前）

**检查策略**：每个检查点调用 `token.check()`，如果已取消则立即抛出 `CancelledError`，避免在不可中断操作中检查（如数据库事务）。

#### 信号传播路径
```
SessionManager 持有 _active_tokens: dict[session_id, CancellationToken]
  ↓
send_message() 时创建 token 并存储到 _active_tokens
  ↓
cancel_request() 时从 _active_tokens 获取 token 并调用 token.cancel(reason)
  ↓
AgentRunner 接收 token 作为参数 → 在检查点调用 token.check()
  ↓
如果已取消 → token.check() 抛出 CancelledError
  ↓
SessionManager 捕获 CancelledError → 生成 cancelled 事件 → 更新会话状态为 idle → 清理 token
```

#### 取消后状态恢复
取消后：保留已持久化的用户消息，丢弃未完成的助手消息，状态恢复为 idle，清理 CancellationToken 和会话锁。

#### 超时处理
默认超时时间 5 分钟，使用 asyncio.timeout 设置超时，超时自动触发 CancellationToken.cancel()，更新会话状态为 error。

#### 异常清理保证
使用 try-finally 确保资源清理，无论正常、异常或取消都执行清理逻辑。清理内容：移除 active_tokens 中的 token、更新会话状态为 idle/error、清理会话锁。清理失败记录日志，不阻塞后续操作。

### 资源生命周期协调

#### 资源创建和清理时序
```
请求开始 → SessionManager 创建 CancellationToken，AgentRunner 创建内部资源
请求执行 → AgentRunner 执行，SessionManager 转发事件
请求结束 → AgentRunner 清理内部资源，SessionManager 清理 CancellationToken 并更新会话状态
```

#### 立即持久化策略
每轮对话结束后立即调用 `SessionStore.save_message()` 持久化消息，确保异常恢复能力、数据一致性，简化实现。

## 并发控制设计

### 设计目标
保证会话状态一致性，避免状态竞争导致的数据不一致。单实例部署，使用 asyncio.Lock 保护状态转换，状态转换满足前置条件检查，数据库事务保证消息保存原子性。

### 状态一致性保证

#### 并发控制实现
每个会话有独立的 asyncio.Lock，锁的生命周期与会话绑定，使用 `async with lock` 确保释放。会话级别锁定（同一会话串行执行），不同会话并行执行互不阻塞。

#### 原子性保证
状态更新在 asyncio.Lock 保护下执行，消息保存使用数据库事务保证原子性，前置条件检查在锁保护下验证当前状态。

#### 状态不一致检测与恢复
定期扫描（每分钟）检测 busy 状态超时会话（超过 5 分钟）和孤立会话（无活跃请求但状态为 busy），重置为 idle 并清理相关 CancellationToken。

## 资源生命周期管理

### 设计原则
资源创建与请求生命周期绑定，异常情况下确保资源清理，避免泄漏。

### 管理对象
- **CancellationToken**：请求开始时创建，与请求处理过程绑定，请求结束时清理
- **AgentRunner 实例**：每次请求创建新实例，请求结束后自动销毁
- **asyncio.Lock**：每个会话独立的锁，保护状态转换，生命周期与会话绑定

> **注意**：SSE 连接的心跳保活由独立的 HeartbeatManager 处理（参见 `heartbeat-design.md`），不属于 SessionManager 的资源管理范围。