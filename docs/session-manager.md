# Session Manager 设计与实现

## 1. 概述

SessionManager 是 Laffybot API 的核心组件，负责管理会话生命周期、状态转换和请求调度。它作为 API 层与 Agent 执行层之间的协调器，确保会话状态一致性和并发安全。

本文档整合了三方面的设计：SessionManager 架构设计、SQLite 存储层实现、以及 Provider/Model 绑定解耦设计。

### 实现状态总览

| 功能模块 | 实现状态 | 实现文件 |
|---------|---------|----------|
| SessionManager 核心 | ✅ 已实现 | `laffybot/service/session_manager.py` |
| SessionStore 接口 | ✅ 已实现 | `laffybot/db/session_store.py` |
| SQLiteStore 实现 | ✅ 已实现 | `laffybot/db/session_store.py:SQLiteStore` |
| SessionInfo 数据结构 | ✅ 已实现 | `laffybot/service/models.py` |
| ContextBuilder 集成 | ✅ 已实现 | `laffybot/service/session_manager.py` |
| CancellationToken | ✅ 已实现 | `laffybot/agent_runtime/cancellation.py` |
| SessionStateMachine | ✅ 已实现 | `laffybot/service/state_machine.py` |
| SessionLockPort | ✅ 已实现 | `laffybot/service/lock_port.py` |
| MessageAccumulator | ✅ 已实现 | `laffybot/service/message_accumulator.py` |
| Token 元数据持久化 | ✅ 已实现 | `laffybot/db/session_store.py:SQLiteStore.save_message` |
| 异常定义（含 SessionNotArchivedError） | ✅ 已实现 | `laffybot/service/errors.py` |
| 异步事件处理 | ✅ 已实现 | `laffybot/service/async_events.py` |
| ProviderStore 接口 | ✅ 已实现 | `laffybot/db/provider_store.py` |
| SQLiteProviderStore 实现 | ✅ 已实现 | `laffybot/db/provider_store.py:SQLiteProviderStore` |
| AppSettingStore | ✅ 已实现 | `laffybot/db/app_setting_store.py` |
| SQLiteAppSettingStore | ✅ 已实现 | `laffybot/db/app_setting_store.py:SQLiteAppSettingStore` |

> **部署约束**：本文档仅考虑单实例部署，不支持多实例水平扩展。

---

## 2. 架构位置

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
│                  SessionManager                      │  ← 单例
│  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │ SessionStore    │  │ ProviderStore            │  │
│  │ 注入: 持久化     │  │ 注入: 配置读取+解密      │  │
│  └─────────────────┘  └──────────────────────────┘  │
│  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │ AppSettingStore │  │ ContextBuilder           │  │
│  │ 注入: 全局配置   │  │ 构建层：上下文组装        │  │
│  └─────────────────┘  └──────────────────────────┘  │
└───────────────────────┬─────────────────────────────┘
                        │
                        v
┌─────────────────────────────────────────────────────┐
│                  AgentRunner                         │  ← 按请求创建
└─────────────────────────────────────────────────────┘
```

**设计决策：**
- **SessionManager 单例**：整个应用只有一个 SessionManager 实例，管理所有会话
- **AgentRunner 按需创建**：每次请求创建新的 AgentRunner 实例，Provider 运行时从 ProviderStore 获取配置后直接实例化
- **SessionStore 依赖注入**：SessionStore 作为依赖注入，支持不同存储后端（当前为 SQLiteStore）
- **ProviderStore 依赖注入**：ProviderStore 作为依赖注入，管理提供商配置读取、解密
- **AppSettingStore 依赖注入**：管理全局键值对配置（默认会话模型、总结模型等）
- **ContextBuilder 集成**：已提取为独立的 ContextBuilder 组件，SessionManager 通过依赖注入使用

---

## 3. 核心职责

### 3.1 会话生命周期管理

创建、获取、删除、列出会话。归档、取消归档、自动归档（超限时自动归档最旧会话）。

### 3.2 状态管理

状态转换验证、并发控制（asyncio.Lock + 数据库乐观锁）、状态持久化。

### 3.3 请求调度

消息发送协调、取消请求处理、错误恢复。

### 3.4 上下文构建

历史消息查询、系统提示组装、完整上下文构建。已提取为独立的 `ContextBuilder` 组件，SessionManager 通过依赖注入使用。

### 3.5 资源管理

AgentRunner 实例管理（按需创建）、CancellationToken 生命周期。

> **注意**：SSE 连接的心跳机制由独立的 HeartbeatManager 处理（参见 `heartbeat-design.md`），不属于 SessionManager 职责。健康检查端点由 API 层直接处理，也不属于 SessionManager 职责。

---

## 4. 接口定义

### 4.1 SessionManager Protocol

**参考**：`laffybot/service/session_manager.py:SessionManager`

#### __init__

```python
def __init__(
    self,
    store: SessionStore,
    provider_store: ProviderStore,
    app_setting_store: AppSettingStore,
    tool_registry: ToolRegistry,
    context_config: ContextConfig | None = None,
    context_builder: ContextBuilder | None = None,
    memory_manager: MemoryManager | None = None,
    max_active_sessions: int = 3,
) -> None
```

**参数说明：**
- `store` - 会话持久化存储
- `provider_store` - 提供商配置存储
- `app_setting_store` - 全局键值对配置存储（默认会话模型、总结模型等）
- `tool_registry` - 工具注册表
- `context_config` / `context_builder` - 上下文构建配置和实例（支持依赖注入）
- `memory_manager` - 记忆管理器（可选）
- `max_active_sessions` - 活跃会话数量上限，超限时自动归档最旧的（默认 3）

> Provider 不再由外部工厂函数创建，改由 SessionManager 运行时从 ProviderStore 获取配置后直接实例化。

#### create_session

创建新会话。创建后异步触发自动归档检查：若活跃会话数超过 `max_active_sessions`，自动归档最旧的会话。

```python
async def create_session(
    self,
    max_iterations: int = 50,
    provider_id: str | None = None,
    model_name: str | None = None,
) -> SessionInfo
```

- `max_iterations` - Agent 最大迭代次数（默认 50）
- `provider_id` / `model_name` - 可选，指定提供商和模型，未指定时从 `AppSettingStore.get_default_session_config()` 读取默认配置
- 返回：SessionInfo 实例
- 异常：`NoActiveProviderError` - 未配置默认模型

> 模型名称不再由调用方传入，改为由 SessionManager 内部解析——优先使用传入的 `provider_id`/`model_name`，否则从 `AppSettingStore` 读取默认配置，作为快照写入 session。

#### get_session_info

```python
async def get_session_info(self, session_id: str) -> SessionInfo
```

- 异常：`SessionNotFoundError`

#### send_message

发送消息并流式返回 Agent 响应。

```python
async def send_message(
    self,
    session_id: str,
    content: str,
) -> AsyncGenerator[SSEEvent, None]
```

- 返回：SSEEvent 异步生成器
- 异常：`SessionNotFoundError`、`SessionBusyError`

**事件序列：** `session_start -> (content | reasoning)* -> [tool_call -> tool_result]+ -> done`

#### cancel_request

```python
async def cancel_request(
    self,
    session_id: str,
    reason: str | None = None,
) -> str
```

- 返回：被取消的 request_id
- 异常：`SessionNotFoundError`、`SessionNotBusyError`

#### archive_session

归档会话并触发记忆提取。若会话忙碌（流式输出中），等待流式输出完成后再归档。

```python
async def archive_session(self, session_id: str) -> SessionInfo
```

- 异常：`SessionNotFoundError`、`SessionAlreadyArchivedError`

> busy 时不再返回 `SessionBusyError`，改用 asyncio.Lock 等待流式完成。

#### unarchive_session

取消归档已归档的会话（将 `archived_at` 设为 NULL）。

```python
async def unarchive_session(self, session_id: str) -> SessionInfo
```

- 异常：`SessionNotFoundError`、`SessionBusyError`、`SessionNotArchivedError`

#### delete_session

```python
async def delete_session(self, session_id: str) -> None
```

- 异常：`SessionNotFoundError`、`SessionBusyError`（忙碌中无法删除）

#### list_sessions

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

- `archived`：`True` 仅返回已归档，`False` 仅返回未归档，`None` 返回全部
- `order_by_asc`：按 `updated_at` 升序排序（用于自动归档策略查找最旧会话）
- 返回：(会话列表, 总数) 元组
- 默认排序：`updated_at DESC, session_id DESC`

### 4.2 SessionStore 接口

**参考**：`laffybot/db/session_store.py:SessionStore`

SessionStore 是会话持久化存储的抽象接口，支持不同的存储后端实现。

#### 核心数据结构：SessionInfo

```python
@dataclass(slots=True)
class SessionInfo:
    session_id: str                   # 会话唯一标识符
    provider_id: str                  # 会话绑定的提供商 ID
    model_name: str                   # 会话绑定的模型名
    status: SessionStatus             # Literal["idle", "busy", "error"]
    created_at: datetime              # 创建时间
    updated_at: datetime              # 最后更新时间
    message_count: int                # 消息数量
    current_request_id: str | None    # 当前请求 ID（可选）
    error_message: str | None         # 错误信息（可选）
    system_prompt: str | None         # 系统提示词（可选）
    max_iterations: int               # Agent 最大迭代次数，默认 50
    archived_at: datetime | None      # 归档时间（可选），非空表示已归档
```

> **变更说明**：`model: str` 已替换为 `provider_id: str` + `model_name: str`，语义更清晰。

#### create_session

```python
async def create_session(
    self,
    session_id: str,
    provider_id: str,
    model_name: str,
    system_prompt: str | None,
    max_iterations: int,
) -> SessionInfo
```

- `session_id` 由 SessionManager 生成（UUID），传入 Store 层持久化

#### get_session

```python
async def get_session(self, session_id: str) -> SessionInfo
```

- 异常：`SessionNotFoundError`

#### update_session_status

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

- `expected_status` - 乐观锁参数，指定期望的当前状态。如果提供，仅在当前状态匹配时才更新
- 返回：是否更新成功
- 异常：`SessionNotFoundError`、`SessionStateError`（乐观锁冲突）

使用原子操作确保并发安全，支持乐观锁（检查当前状态后更新）。

#### update_session_model

```python
async def update_session_model(
    self,
    session_id: str,
    provider_id: str,
    model_name: str,
    expected_status: SessionStatus | tuple[SessionStatus, ...] | None = ("idle", "error"),
) -> SessionInfo
```

- 更新绑定的 provider 和 model
- `expected_status` 默认 `("idle", "error")`，内部通过 SQL 条件更新保证并发安全
- 单值用 `WHERE status = ?`，元组用 `WHERE status IN (...?)`，`None` 无条件更新
- 默认接受 idle 或 error，拒绝 busy 状态，防止执行消息时被并发修改配置

#### archive_session

```python
async def archive_session(self, session_id: str) -> SessionInfo
```

- 设置 `archived_at` 时间戳
- 异常：`SessionNotFoundError`

#### unarchive_session

```python
async def unarchive_session(self, session_id: str) -> SessionInfo
```

- 将 `archived_at` 设为 NULL
- 异常：`SessionNotFoundError`

#### delete_session

```python
async def delete_session(self, session_id: str) -> None
```

- 删除会话及其所有消息（外键级联）
- 异常：`SessionNotFoundError`

#### list_sessions

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

- 排序：默认 `updated_at DESC, session_id DESC`；`order_by_asc=True` 时 `updated_at ASC, session_id ASC`

#### save_message

```python
async def save_message(
    self,
    session_id: str,
    role: MessageRole,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> SessionMessage
```

- `MessageRole = Literal["user", "assistant", "system", "tool"]`
- 异常：`SessionNotFoundError`（外键约束违反）

#### get_messages

```python
async def get_messages(
    self,
    session_id: str,
    limit: int = 50,
    before: datetime | None = None,
) -> list[SessionMessage]
```

- 按 `timestamp ASC, id ASC` 排序
- 异常：`SessionNotFoundError`

#### get_message_count

```python
async def get_message_count(self, session_id: str) -> int
```

- 返回消息总数

### 4.3 消息存储

#### 消息格式

```python
{
    "role": "user" | "assistant" | "system" | "tool",
    "content": "消息内容",
    "timestamp": "2024-01-15T10:30:00Z",  # ISO 8601 格式
    "metadata": {}  # 可选，工具调用信息等
}
```

> metadata 仅在非 None 时包含在返回字典中。

#### 消息表结构

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT,  -- JSON 格式
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
```

#### 存储策略

- **立即持久化**：每轮对话结束后立即调用 `save_message()` 持久化消息，确保异常恢复能力和数据一致性
- **事务保证**：消息保存、计数更新和 `updated_at` 更新在同一事务中完成
- **消息计数**：使用冗余的 `message_count` 字段，避免频繁 COUNT 查询
- **分页**：通过 `before` 参数实现基于时间戳的分页（`WHERE timestamp < ?`）

---

## 5. 数据库实现

### 5.1 Schema

**技术选型**：SQLite（轻量级、零配置、单文件存储）+ aiosqlite（异步驱动）

#### sessions 表

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    current_request_id TEXT,
    error_message TEXT,
    system_prompt TEXT,
    max_iterations INTEGER NOT NULL DEFAULT 50,
    archived_at TEXT
);

CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);
```

**字段说明：**
- `session_id`: UUID 格式，主键
- `provider_id` / `model_name`: 会话绑定的提供商 ID 和模型名（替代原单一 `model` 字段）
- `status`: 枚举值（idle/busy/error），应用层验证
- `created_at`, `updated_at`: ISO 8601 格式时间戳
- `message_count`: 冗余字段，避免频繁 COUNT 查询
- `current_request_id`: 当前活跃请求 ID，用于取消操作
- `system_prompt`: 会话级系统提示词（已从 per-session 参数移除，改为全局 UI 设置）
- `max_iterations`: Agent 最大迭代次数，控制每轮消息的 Agent 循环上限
- `archived_at`: ISO 8601 格式时间戳，非空表示已归档

> `provider_id` 不设外键约束。删除 provider 后已有会话会出现悬浮引用，由应用层在 `send_message()` 和模型切换时检测并返回 404 提示。不设外键是为了避免删除 provider 时级联删除会话。

#### messages 表

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT,  -- JSON 格式
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
```

#### 数据完整性约束

- **外键约束**：`PRAGMA foreign_keys = ON`，删除会话时级联删除所有消息
- **状态约束**：应用层验证 status 为 `idle`/`busy`/`error`
- **WAL 模式**：`PRAGMA journal_mode = WAL` + `PRAGMA synchronous = NORMAL`，提高读写并发性能

### 5.2 SQLiteStore

**参考**：`laffybot/db/session_store.py:SQLiteStore`

#### 初始化

```python
class SQLiteStore(SessionStore):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
```

- 延迟初始化数据库连接（首次使用时建立）
- 单连接实例复用，避免频繁打开关闭
- 连接生命周期与应用一致

#### 连接管理

```python
async def _ensure_db(self) -> aiosqlite.Connection:
    if self._db is None:
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._create_tables()
    return self._db

async def close(self) -> None:
    if self._db is not None:
        await self._db.close()
        self._db = None
```

- 启用外键约束
- 自动创建表结构
- 应用关闭时通过 FastAPI shutdown event 关闭

#### 核心接口实现策略

| 方法 | 实现要点 | 并发安全 |
|------|---------|---------|
| `create_session` | 生成 UUID，INSERT，返回 SessionInfo | 数据库唯一约束 |
| `get_session` | SELECT 查询，未找到抛出 SessionNotFoundError | 读操作无锁 |
| `update_session_status` | 带乐观锁的条件 UPDATE（WHERE status=?），检查 rowcount | 乐观锁 |
| `update_session_model` | 带 expected_status 的条件 UPDATE，WHERE status IN (...?) | 乐观锁 |
| `archive_session` | 设置 archived_at 和 updated_at，UPDATE 后检查 rowcount | 行级 |
| `delete_session` | DELETE，外键级联删除消息 | 事务保证 |
| `list_sessions` | 动态 SQL（状态/归档过滤），LIMIT/OFFSET 分页，COUNT 总数 | 读操作无锁 |
| `save_message` | INSERT + 更新 message_count + updated_at，同一事务 | 事务原子性 |
| `get_messages` | 动态 SQL（before 过滤），ORDER BY timestamp, id，JSON 反序列化 | 读操作无锁 |
| `get_message_count` | 读取 sessions.message_count 冗余字段 | 读操作无锁 |

#### 事务处理

**使用事务的场景：**
- `save_message`: 消息保存 + 计数更新 + updated_at 更新
- `delete_session`: 会话删除 + 消息级联删除（外键约束自动处理）

```python
await db.execute("BEGIN")
try:
    await db.execute(...)
    await db.execute(...)
    await db.commit()
except Exception:
    await db.rollback()
    raise
```

**异常处理**：`aiosqlite.IntegrityError`（外键约束违反）转换为 `SessionNotFoundError`

#### updated_at 更新机制

| 操作 | 是否更新 updated_at | 说明 |
|------|-------------------|------|
| `create_session` | ✅ | 设置为创建时间 |
| `update_session_status` | ✅ | 状态变更时更新 |
| `save_message` | ✅ | 保存新消息时更新 |
| `archive_session` | ✅ | 归档时同步更新时间戳 |
| `get_session` | ❌ | 只读操作 |
| `get_messages` | ❌ | 只读操作 |
| `list_sessions` | ❌ | 只读操作 |
| `delete_session` | ❌ | 删除操作 |

### 5.3 乐观锁与并发

#### 乐观锁实现

`update_session_status` 使用 SQL 条件更新实现乐观锁：

```sql
UPDATE sessions 
SET status = ?, 
    current_request_id = ?, 
    error_message = ?,
    updated_at = ?
WHERE session_id = ? 
  AND status = ?  -- 前置状态检查（乐观锁）
```

**工作流程：**
1. 查询会话的当前状态
2. 在 UPDATE 的 WHERE 子句中添加 `status = 当前状态` 条件
3. 通过 `cursor.rowcount` 判断是否成功
4. 如果受影响行数为 0，说明状态已被其他请求修改，抛出 `SessionStateError`

**如果提供了 `expected_status`：**
```python
if expected_status is not None:
    sql += " AND status = ?"
    params.append(expected_status)
```

**乐观锁优势：**
- 无锁等待，不需要获取数据库锁，减少阻塞
- 自动检测冲突，通过 WHERE 条件检测状态变化
- 适合读多写少场景（会话状态更新频率较低）
- 配合 SessionManager 的 asyncio.Lock 提供双重保护

#### SQLite 并发特性

- **多读单写**：SQLite 支持多个读取者同时访问
- **写串行化**：写入操作通过数据库锁串行化
- **WAL 模式**：读写不阻塞，适合读多写少场景

#### 应用层并发控制

每个会话独立的 asyncio.Lock，保护状态转换的原子性，避免同一会话的并发请求冲突。数据库锁粒度太粗（整个数据库），应用层锁提供更细粒度的控制。

---

## 6. Provider/Model 解耦

### 6.1 现状与问题

原设计中所有会话共用全局选中的 provider + model：

- `SessionInfo.model`（仅存模型名，不存 provider）在创建时做一次快照存储
- `send_message()` 每次执行时从 `ProviderStore.get_active_selection()` 重新解析（含 provider）
- 切换全局选中会即时影响所有会话的下一次消息执行

**带来的问题：**
1. **切换风险**：用户切换全局模型后，旧会话下一轮回复可能用了不兼容的模型
2. **标题生成依赖不明**：Auto-Title 需要调用 LLM 生成标题，但不知道用哪个模型
3. **会话隔离不足**：不同会话无法绑定不同的模型

### 6.2 设计目标

1. 每个会话独立绑定 provider + model，互不干扰
2. 创建会话时默认继承 `default_session_config`（由用户在设置中配置）
3. 支持在会话内切换 provider + model

### 6.3 SessionInfo 字段变更

| 变更 | 字段 | 类型 | 说明 |
|------|------|------|------|
| 删除 | `model` | — | 语义模糊，被 `provider_id` + `model_name` 取代 |
| 新增 | `provider_id` | str | 会话绑定的提供商 ID |
| 新增 | `model_name` | str | 会话绑定的模型名 |

### 6.4 Store 接口变更

**SessionStore 变更：**
- `create_session()` 参数：`model: str` → `provider_id: str, model_name: str`
- 新增 `update_session_model()`：支持会话内切换模型，使用 `expected_status` 做乐观锁
- `_row_to_session()` 读取 `provider_id` + `model_name` 两列

**ProviderStore 变更：**
- 移除全局选中概念，删除 `get_active_selection()`、`set_active_selection()`、`clear_active_selection()`
- `delete_provider()` 返回从 `bool` 简化为 `None`（移除 active selection 检查和清除逻辑）

### 6.5 AppSettingStore

新增独立的 `AppSettingStore`（`laffybot/db/app_setting_store.py`），负责管理全局键值对配置，与 provider/model 管理解耦。SQLite 实现拥有 `app_settings` 表的所有权。

提供类型化方法：

| 方法 | 签名 | 说明 |
|------|------|------|
| `get_default_session_config` | `() → ProviderModelPair \| None` | 读取新建会话默认模型配置 |
| `set_default_session_config` | `(provider_id: str, model_name: str) → None` | 写入默认模型配置 |
| `delete_default_session_config` | `() → None` | 清除默认模型配置 |
| `get_summary_model` | `() → ProviderModelPair \| None` | 读取总结模型配置 |
| `set_summary_model` | `(provider_id: str, model_name: str) → None` | 写入总结模型配置 |
| `delete_summary_model` | `() → None` | 清除总结模型配置 |

`ProviderModelPair` 包含 `provider_id: str` 和 `model_name: str` 两个字段。内部存储为 `app_settings` 表的 JSON 值。

### 6.6 创建会话流程

`SessionManager.create_session()` 新增可选参数 `provider_id` 和 `model_name`：

| 传入情况 | 行为 |
|----------|------|
| 同时传入 `provider_id` + `model_name` | 校验 provider 存在且 model 属于该 provider，通过后写入 session |
| 均不传 | 从 `AppSettingStore.get_default_session_config()` 读取默认配置 |

- `provider_id` 和 `model_name` 必须同时传入或同时不传（违反则 422）
- 传入时校验失败返回 404（provider 不存在 / model 不属于 provider）
- `default_session_config` 未配置时返回 400，提示用户先在设置中配置默认模型

### 6.7 执行消息流程

`send_message()` 不再调用全局选中，改为从 session 读取：

1. `session = await self.store.get_session(session_id)`
2. `provider_config = await self.provider_store.get_provider_config(session.provider_id)`
3. 校验 `session.model_name` 仍属于该 provider 的 model list
4. `AgentRunSpec.model = session.model_name`
5. `_build_messages()` 使用 `session.model_name`

**Provider 或 Model 被删除后的行为**（不降级）：

| 场景 | 检测时机 | 异常 | 响应 |
|------|----------|------|------|
| Provider 被删除 | 步骤 2：`get_provider_config()` | `ProviderNotFoundError` | 4xx，提示"会话绑定的提供商已被删除，请切换模型" |
| Model 被删除 | 步骤 3：校验 model 属于 provider | `ModelNotFoundError` | 4xx，提示"会话绑定的模型已被删除，请切换模型" |

> `ModelNotFoundError` 的构造函数已从接收 `model_id: str`（数据库自增主键）迁移为接收 `model_name: str`（用户可理解的名称）。

### 6.8 会话内切换模型

`PUT /api/v1/sessions/{session_id}/model`

请求体：`{ "provider_id": "deepseek", "model_name": "deepseek-chat" }`

| 条件 | 状态码 |
|------|--------|
| 成功 | 200，返回 `SessionResponse` |
| provider_id + model_name 未同时提供 | 422 |
| provider 不存在 / model 不属于 provider | 404 |
| 会话不存在 | 404 |
| 会话状态为 busy | 409 |

处理流程：
1. 校验 provider 存在且 model 属于该 provider
2. 调用 `store.update_session_model(session_id, provider_id, model_name, expected_status=("idle", "error"))`
3. 受影响行数为 0 → 会话为 busy → 抛 `SessionBusyError` → 409

切换即时生效，下一条消息使用新配置。使用 `expected_status` 做条件更新，与 `send_message()` 的状态变更机制一致，无需额外锁排队。

### 6.9 新建会话流程简化

解耦后，模型选择由聊天内的模型切换控件完成，不再需要创建会话时选择模型。

| 触发位置 | 旧行为 | 新行为 |
|----------|--------|--------|
| Sidebar "新建会话" 按钮 | 弹出新建会话对话框 | 直接创建会话并跳转到聊天页 |
| ChatPage 空状态 "新建会话" 按钮 | 弹出新建会话对话框 | 同上，直接创建并跳转 |
| ChatPage 有会话时的新建 | 弹出新建会话对话框 | 输入框右侧添加 `+` 按钮，直接创建并跳转 |

> **关于 `max_iterations`**：它控制的是每次 `send_message()` 调用中 Agent 的最大 LLM 迭代次数（默认 50），不是整个会话的总次数。达到上限后 `done` 事件的 `stop_reason` 为 `"max_iterations"`。
>
> **关于 `system_prompt`**：已从 per-session 参数移除，改为全局 UI 设置。可通过 `GET/PUT /api/v1/settings/system-prompt` 管理，对所有新会话生效。

### 6.10 默认会话模型配置

`default_session_config` 决定新建会话时默认使用哪个 provider + model，替代原全局选中概念。

**API 端点：**

| 方法 | 路径 | 说明 | 响应 |
|------|------|------|------|
| GET | `/api/v1/settings/default-session-model` | 获取默认会话模型 | `{ provider_id, model_name }` 或 204 |
| PUT | `/api/v1/settings/default-session-model` | 设置默认会话模型 | 200 `{ provider_id, model_name }` |
| DELETE | `/api/v1/settings/default-session-model` | 清除配置 | 200 `{ status: "cleared" }` |

PUT 校验：`provider_id` + `model_name` 必须同时提供，provider 必须存在且 model 属于该 provider。

### 6.11 全局总结专用模型

> 与会话-模型绑定是正交的：会话绑定解决"用哪个模型对话"，全局总结模型解决"用哪个轻量模型做标题生成"。两者独立配置，互不依赖。

**API 端点：**

| 方法 | 路径 | 说明 | 响应 |
|------|------|------|------|
| GET | `/api/v1/settings/summary-model` | 获取总结模型配置 | `{ provider_id, model_name }` 或 204 |
| PUT | `/api/v1/settings/summary-model` | 设置总结模型配置 | 200 `{ provider_id, model_name }` |
| DELETE | `/api/v1/settings/summary-model` | 清除总结模型配置 | 200 `{ status: "cleared" }` |

**回退逻辑：**

```
Auto-Title 选择模型:
  1. AppSettingStore.get_summary_model() 返回非空 ProviderModelPair
     → 得到 provider_id + model_name
     → get_provider_config(provider_id) 解析配置
     → 用 model_name 作为模型
  2. 未配置（key 不存在或 JSON 不完整）
     → 用 session.provider_id → get_provider_config() 解析配置
     → 用 session.model_name 作为模型
```

> 退回到 `session.model_name` 意味着标题生成使用与对话相同的模型。如果对话模型成本较高（如 reasoning 模型），建议设置 `summary_model` 使用更廉价的模型。
>
> **容错处理**：若对应的 provider 已被删除，Auto-Title 应捕获 `ProviderNotFoundError` 并跳过标题生成（记录 warn 日志），而非向上传播导致 500 错误。

### 6.12 数据库连接

`SessionStore`、`ProviderStore`、`AppSettingStore` 各自持有独立的 SQLite 连接（三个 `aiosqlite.Connection`），通过 WAL 模式 + 忙重试处理并发。

- 每个 Store 接受 `db_path: str`，内部创建独立连接
- 各连接执行 `PRAGMA journal_mode=WAL`，允许读-写并发
- 各连接设置 `aiosqlite.Row` 作为 row factory
- 各连接执行 `PRAGMA foreign_keys = ON`
- 写入操作对 `SQLITE_BUSY` 做最多 3 次重试（指数退避）

**事务边界**：调用方自行管理 `BEGIN` / `COMMIT` / `ROLLBACK`，Store 不自动包装事务。

---

## 7. 编排流程

### 7.1 send_message 事务边界

`send_message()` 的执行遵循"存储 → 查询 → 构建 → 执行 → 存储"的处理流程，形成可预测的数据流和生命周期：

```
SessionManager.send_message()
    ├─ 获取会话锁 (asyncio.Lock)
    ├─ 检查状态是否为 idle
    ├─ ProviderStore.get_provider_config(session.provider_id)  → 获取解密配置
    ├─ 校验 model_name 属于该 provider
    ├─ 创建 CancellationToken
    ├─ 更新状态为 busy（数据库 UPDATE，带乐观锁，expected_status="idle"）
    ├─ 保存用户消息（数据库 INSERT + 更新 message_count）
    ├─ ContextBuilder.build_messages()  → 构建完整上下文（系统提示 + 历史 + 当前消息）
    ├─ 创建 AgentRunner 实例（Provider 由 Manager 实例化）
    ├─ 调用 AgentRunner.run_stream()
    ├─ 转发 SSE 事件流
    │   ├─ session_start → 记录 request_id
    │   ├─ content/reasoning → 累积助手回复
    │   ├─ tool_call → 记录工具调用
    │   ├─ tool_result → 记录工具结果
    │   └─ done → 保存完整助手消息，更新状态为 idle
    └─ 释放会话锁和 CancellationToken
```

**关键设计：**
- 严格遵循闭环流程，简化调试，为中间步骤的 Hook 提供明确插入点
- 状态更新在 asyncio.Lock 保护下执行，前置条件检查在锁保护下验证当前状态
- 消息保存使用数据库事务保证原子性
- Provider 运行时从 ProviderStore 获取解密配置后直接实例化，配置来源透明，切换即时生效

### 7.2 异常处理

```
Agent 执行异常
├─ LLM API 错误
│  ├─ 可重试错误（速率限制、临时故障）→ 等待后重试（最多 N 次）
│  └─ 不可重试错误（认证失败、模型不可用）→ 更新状态为 error，返回 error 事件
├─ 工具执行错误 → 由 AgentRunner 处理，返回 tool_result(success=false)
├─ 领域异常（ProviderNotFoundError / ModelNotFoundError）
│  → SessionManager 捕获，转换为 SSE error event
└─ 内部错误 → 记录日志，更新状态为 error，返回 error 事件
```

**异常清理保证：** 使用 try-finally 确保资源清理，无论正常、异常或取消都执行清理逻辑。清理内容：移除 active_tokens 中的 token、更新会话状态为 idle/error、清理会话锁。清理失败记录日志，不阻塞后续操作。

**SSE 错误映射：**

| 异常类型 | SSE error code | 处理层 |
|----------|---------------|--------|
| `ProviderNotFoundError` | `PROVIDER_NOT_FOUND` | `SessionManager.send_message()` |
| `ModelNotFoundError` | `MODEL_NOT_FOUND` | `SessionManager.send_message()` |
| `CancelledError` | `CANCELLED` | `SessionManager.send_message()` |
| `SessionError` 子类 | `SESSION_ERROR` | `SessionManager.send_message()` |
| 未预期异常 | 500 Internal Error | FastAPI 全局 exception handler |

> `_stream_session_events()` 只做事件格式化和流控制，不处理领域异常。由 `SessionManager.send_message()` 统一捕获并转换。

---

## 8. 状态机与并发控制

### 8.1 状态定义

会话状态为 `Literal["idle", "busy", "error"]`：

| 状态 | 含义 | 可接受操作 |
|------|------|-----------|
| `idle` | 空闲，可接受新请求 | send_message, archive, delete, cancel(→SessionNotBusyError) |
| `busy` | 忙碌，正在处理请求 | cancel, archive(等待), delete(→SessionBusyError) |
| `error` | 错误状态 | send_message(重试), archive, delete, update_session_model |

### 8.2 状态转换

```
idle ──send_message──→ busy ──done──→ idle
                        ├──cancel──→ idle
                        └──error──→ error
error ──send_message──→ busy
       ──force_update──→ idle
```

### 8.3 并发控制设计

#### 设计目标
保证会话状态一致性，避免状态竞争导致的数据不一致。单实例部署，使用三层防护：
1. **应用层锁**：每个会话独立的 asyncio.Lock
2. **乐观锁**：数据库条件更新（WHERE status=?）
3. **事务原子性**：SQLite 事务保证消息保存的原子性

#### 应用层锁
- 每个会话有独立的 asyncio.Lock
- 锁的生命周期与会话绑定
- `async with lock` 确保释放
- 同一会话串行执行，不同会话互不阻塞

#### 乐观锁
- `update_session_status` 使用 `expected_status` 参数做 WHERE 条件更新
- 更新失败时抛出 `SessionStateError`
- 与 asyncio.Lock 配合提供双重保护

#### 原子性保证
- 状态更新在 asyncio.Lock 保护下执行
- 消息保存使用数据库事务保证原子性
- 前置条件检查在锁保护下验证当前状态

#### 超时与恢复
- 默认超时时间 5 分钟，使用 `asyncio.timeout` 设置
- 超时自动触发 `CancellationToken.cancel()`，更新会话状态为 error
- 定期扫描（每分钟）检测 busy 状态超时会话和孤立会话，重置为 idle 并清理相关 CancellationToken

---

## 9. 资源生命周期

### 9.1 设计原则

资源创建与请求生命周期绑定，异常情况下确保资源清理，避免泄漏。

### 9.2 管理对象

| 资源 | 创建时机 | 销毁时机 | 生命周期 |
|------|---------|---------|---------|
| CancellationToken | send_message 开始 | send_message 结束 | 请求级别 |
| AgentRunner | send_message 中按需创建 | send_message 结束后自动销毁 | 请求级别 |
| asyncio.Lock | 会话首次被访问 | 与会话绑定，持续存在 | 会话级别 |
| SQLite 连接 | 应用启动时延迟创建 | 应用关闭时通过 shutdown event 关闭 | 应用级别 |

### 9.3 资源创建和清理时序

```
请求开始 → SessionManager 创建 CancellationToken，AgentRunner 创建内部资源
请求执行 → AgentRunner 执行，SessionManager 转发事件
请求结束 → AgentRunner 清理内部资源，SessionManager 清理 CancellationToken 并更新会话状态
```

### 9.4 取消后消息处理

取消后丢弃部分生成的助手消息，保留已持久化的用户消息，会话状态恢复为 idle。保持历史完整性，避免不完整对话导致后续请求混乱；简化实现，无需处理部分消息状态标记。

### 9.5 立即持久化策略

每轮对话结束后立即调用 `SessionStore.save_message()` 持久化消息，确保异常恢复能力、数据一致性，简化实现。

---

## 10. SessionModel 绑定变更清单

以下为 Provider/Model 解耦后各层需移除或替换的代码，按文件组织。适用于开发阶段删库重建策略。

### 10.1 后端

| `laffybot/db/provider_store.py` | |
|--|--|
| 移除 | `ActiveSelection` dataclass |
| 移除 | 常量 `_ACTIVE_PROVIDER_KEY`、`_ACTIVE_MODEL_KEY` |
| 移除 | ABC 中的 `get_active_selection()`、`set_active_selection()`、`clear_active_selection()` |
| 移除 | `SQLiteProviderStore` 中的上述三个方法实现 |
| 移除 | `_PROVIDER_SCHEMA_SQL` 中的 `app_settings` 表 DDL（由 `SQLiteAppSettingStore` 接管） |
| 修改 | `delete_provider()`：移除 active selection 检查和清除逻辑，返回值从 `bool` 简化为 `None` |
| 修改 | `delete_model()`：移除 active selection 检查和清除逻辑 |

| `laffybot/service/models.py` | |
|--|--|
| 替换 | `SessionInfo.model: str` → `SessionInfo.provider_id: str` + `SessionInfo.model_name: str` |

| `laffybot/db/session_store.py` | |
|--|--|
| 修改 | `_SCHEMA_SQL`：sessions 表 `model TEXT NOT NULL` → `provider_id TEXT NOT NULL, model_name TEXT NOT NULL` |
| 修改 | `create_session()` 参数：`model: str` → `provider_id: str, model_name: str` |
| 修改 | `_row_to_session()`：读 `model` 列改为读 `provider_id` + `model_name` 两列 |
| 新增 | `update_session_model()` 方法 |

| `laffybot/service/session_manager.py` | |
|--|--|
| 移除 | import `NoActiveProviderError` |
| 新增 | `__init__` 参数 `app_setting_store: AppSettingStore` |
| 修改 | `create_session()`：移除 `get_active_selection()` 调用，新增可选参数 `provider_id`/`model_name`，回调 `AppSettingStore.get_default_session_config()` |
| 修改 | `send_message()`：移除 `get_active_selection()` 调用，改为从 `session.provider_id` 获取 provider、`session.model_name` 获取 model。将 provider resolution 移入 `try` 块以正确捕获 `ProviderNotFoundError`/`ModelNotFoundError` |
| 修改 | `_build_messages()`：`model or session.model` → `model or session.model_name` |

| `laffybot/service/errors.py` | |
|--|--|
| 无变更 | `NoActiveProviderError` 保留不动（移除引用即可，类定义无需删除） |

| `laffybot/api/schemas.py` | |
|--|--|
| 移除 | `ActiveSelectionResponse` |
| 移除 | `ActiveSelectionUpdateRequest` |
| 修改 | `SessionCreateRequest`：新增可选字段 `provider_id: str \| None = None`、`model_name: str \| None = None`；已移除 `system_prompt` 字段 |
| 修改 | `SessionBase`：`model: str` → `provider_id: str`、`model_name: str` |
| 新增 | `SessionModelUpdateRequest`：字段 `provider_id: str`、`model_name: str` |

| `laffybot/api/session_routes.py` | |
|--|--|
| 移除 | import `ActiveSelectionResponse`、`ActiveSelectionUpdateRequest` |
| 移除 | GET `/providers/active` 路由处理函数 |
| 移除 | PUT `/providers/active` 路由处理函数 |
| 修改 | `_serialize_session()`：`session.model` → `session.provider_id`、`session.model_name` |
| 修改 | `delete_provider` 路由响应：移除 `active_cleared` 字段 |
| 新增 | PUT `/sessions/{session_id}/model` 路由 |
| 新增 | GET/PUT/DELETE `/settings/default-session-model` 路由 |
| 新增 | GET/PUT/DELETE `/settings/summary-model` 路由 |
| 修改 | `_stream_session_events()`：移除领域异常捕获，统一由 `SessionManager.send_message()` 处理 |

| `laffybot/api/dependencies.py` | |
|--|--|
| 新增 | `build_app_setting_store(config) → AppSettingStore` |
| 新增 | `get_app_setting_store(request) → AppSettingStore` FastAPI dependency |
| 修改 | `build_session_manager()`：新增 `app_setting_store` 参数 |

| `laffybot/service/__init__.py` | |
|--|--|
| 无变更 | 不 export `AppSettingStore`（由调用方直接 import） |

### 10.2 前端

| `ui/src/lib/api.ts` | |
|--|--|
| 移除 | `ActiveSelectionResponse` 接口 |
| 移除 | `ActiveSelectionUpdateRequest` 接口 |
| 移除 | `getActiveSelection()` 函数 |
| 移除 | `setActiveSelection()` 函数 |
| 修改 | `CreateSessionRequest`：新增可选字段 `provider_id?: string`、`model_name?: string` |
| 修改 | `SessionResponse`：`model: string` → `provider_id: string`、`model_name: string` |
| 新增 | `UpdateSessionModelRequest` 接口：`{ provider_id: string; model_name: string }` |
| 新增 | `updateSessionModel(sessionId, data)` 函数：`PUT /sessions/{session_id}/model` |

| `ui/src/hooks/use-providers.ts` | |
|--|--|
| 移除 | `useActiveSelection()` hook |
| 移除 | `useSetActiveSelection()` hook |
| 修改 | `useDeleteProvider()`：移除 `invalidateQueries(['active-selection'])` |

| `ui/src/hooks/use-sessions.ts` | |
|--|--|
| 新增 | `useUpdateSessionModel()`：mutation 调用 `api.updateSessionModel()`，成功后 invalidate `['sessions']` |

| `ui/src/components/ui/NewSessionDialog.tsx` | |
|--|--|
| 移除 | 整个文件及所有引用 |

| `ui/src/components/layout/GlobalModelSelector.tsx` | |
|--|--|
| 移除 | 整个文件及所有引用 |

| `ui/src/components/layout/Sidebar.tsx` | |
|--|--|
| 修改 | 移除 `NewSessionDialog` 的 import、state、render；"新建会话"按钮直接调用 `useCreateSession().mutateAsync({})` 并导航 |
| 修改 | 会话列表项：`session.model` → `${session.provider_id}/${session.model_name}` 或 `session.model_name` |
| 移除 | 移除 `useActiveSelection()` 相关逻辑 |

| `ui/src/components/chat/ChatHeader.tsx` | |
|--|--|
| 修改 | `session.model` → 展示 `provider_id / model_name` |

| `ui/src/components/chat/InputBar.tsx` | |
|--|--|
| 修改 | 新增 props：`sessionProviderId: string`、`sessionModelName: string`、`sessionId: string` |
| 新增 | 输入框左侧渲染两级模型下拉选择器 |
| 新增 | 模型切换调用 `updateSessionModel()`，失败时 Toast 提示（5 秒自动消失），控件回退旧值 |

| `ui/src/pages/ChatPage.tsx` | |
|--|--|
| 移除 | `NewSessionDialog` 的 import、state、render |
| 修改 | 空状态"新建会话"按钮 → 直接调用 `useCreateSession().mutateAsync({})` |
| 新增 | 有会话时输入框右侧添加 `+` 按钮 → 调用 `useCreateSession().mutateAsync({})` |
| 修改 | 传递 session provider/model 给 InputBar |

| `ui/src/pages/ProviderSettingsPage.tsx` | |
|--|--|
| 新增 | "默认会话模型"配置区：provider 下拉 + model 下拉 + 保存/清除 |
| 新增 | "总结模型"配置区：provider 下拉 + model 下拉 + 保存/清除 |

### 10.3 UI 交互 — 模型切换控件

**位置**：模型切换控件置于消息输入框（`InputBar`）左侧，与发送按钮对称。

**数据源**：来自 `use-providers` hook 返回的 providers 列表及各自 models。

**InputBar 接口变更**：

| Prop | 类型 | 来源 |
|------|------|------|
| `sessionId` | `string` | 从 ChatPage 的 URL param 获取 |
| `providerId` | `string` | 当前 session 的 `provider_id` |
| `modelName` | `string` | 当前 session 的 `model_name` |

ChatPage 从 `useSessionById(sessionId)` 获取 session 信息，提取 `providerId`/`modelName` 传给 InputBar。InputBar 内部使用 `useProviders()`/`useModels()` 获取可选列表，调用 `api.updateSessionModel()` 进行切换。

**禁用条件**：
- 会话状态为 `busy`（`isStreaming === true`）时禁用
- API 调用中禁用

### 10.4 依赖关系

```
会话-模型绑定
  ├── 解决：用哪个模型对话
  ├── 依赖：SessionStore 接口变更 + AppSettingStore（default_session_config）
  └── 被 Auto-Title 依赖（需要 SessionInfo.provider_id + model_name 字段）

默认会话模型配置
  ├── 解决：新建会话默认用哪个模型
  ├── 依赖：AppSettingStore.get_default_session_config()
  └── 被会话-模型绑定依赖（create_session 需要读取默认值）

全局总结模型配置
  ├── 解决：用哪个轻量模型做标题生成
  ├── 依赖：AppSettingStore.get_summary_model()
  └── 与会话-模型绑定正交，独立配置
      └── Auto-Title 选择逻辑：先查 summary_model，
           有（JSON 完整）则用总结专用模型，无则退回到 session.provider_id + session.model_name
```

### 10.5 实现顺序

```
会话-模型绑定：
  1. 数据库：sessions 表加 provider_id + model_name 列，删 model 列
  2. SessionStore：create_session 签名变更 + update_session_model（含 expected_status）
  3. AppSettingStore：实现独立 Store（类型化方法），接管 app_settings 表
  4. Manager：send_message() 改为从 session 读取 provider + model
  5. API：新增 PUT /sessions/{session_id}/model 端点
  6. UI：模型切换控件 + 移除新建会话对话框

默认会话模型配置（与会话-模型绑定同步上线）：
  1. AppSettingStore：已在上一步实现
  2. API：新增 GET/PUT/DELETE /api/v1/settings/default-session-model
  3. UI：设置页面"默认模型"配置区

全局总结模型配置（与会话-模型绑定无依赖关系，可独立安排）：
  1. AppSettingStore：已在上一步实现
  2. API：GET/PUT/DELETE /api/v1/settings/summary-model
  3. UI：设置页面"总结模型"配置区
```
