# SessionManager SQLite 实现设计文档

> **✅ 实现状态：已完成**
> 
> 实现位置：`laffybot/session/store.py:SQLiteStore`

> **文档范围说明**：本文档专注于 SessionManager 使用 SQLite 数据库的实现设计，包括数据库 schema、SessionStore 实现策略和关键技术决策。
> 
> **本文档不包含以下内容**：
> - 测试策略和测试用例（参见测试代码）
> - 性能监控和指标采集（**不在本项目范围内**）
> - 具体代码实现（参见源代码实现）
> - API 层实现细节（参见 api.md）
> 
> **部署约束**：本文档仅考虑单实例部署，SQLite 数据库文件位于本地文件系统。

## 实现状态总览

| 功能模块 | 实现状态 | 实现文件 |
|---------|---------|----------|
| SQLiteStore 类 | ✅ 已实现 | `laffybot/session/store.py:SQLiteStore` |
| sessions 表 | ✅ 已实现 | 包含所有设计字段（含 archived_at） |
| messages 表 | ✅ 已实现 | 包含 token 字段（迁移已实现） |
| 外键约束 | ✅ 已实现 | `PRAGMA foreign_keys = ON` |
| WAL 模式 | ✅ 已实现 | `PRAGMA journal_mode = WAL` |
| 乐观锁更新 | ✅ 已实现 | `update_session_status` 支持乐观锁 |
| Token 元数据字段 | ✅ 已实现 | `input_tokens`, `output_tokens` 列 |
| 会话归档 | ✅ 已实现 | `archive_session()` 设置 `archived_at` |

## 概述

本文档描述 SessionManager 的 SQLite 存储层实现，包括数据库 schema 设计、SessionStore 接口实现、并发控制策略和资源管理。

## 架构位置

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Routes                    │
└────────────────────┬────────────────────────────────┘
                     │
                     v
         ┌───────────────────────┐
         │   SessionManager      │  ← 单例
         │  ┌─────────────────┐  │
         │  │ SQLiteStore     │  │  ← 本文档核心
         │  └─────────────────┘  │     实现 SessionStore 接口
         │  ┌─────────────────┐  │
         │  │ ContextBuilder  │  │  构建层：上下文组装
         │  └─────────────────┘  │
         └───────────┬───────────┘
                     │
                     v
         ┌───────────────────────┐
         │    AgentRunner        │  ← 单例（所有会话共享）
         └───────────────────────┘
```

**技术选型理由：**
- **SQLite**：轻量级、零配置、单文件存储、适合单实例部署
- **aiosqlite**：异步 SQLite 驱动，与 FastAPI 异步架构一致
- **单文件数据库**：简化备份和迁移

## 数据库 Schema 设计

### 表结构

#### sessions 表

存储会话元数据。

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
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
- `status`: 枚举值（idle/busy/error）
- `created_at`, `updated_at`: ISO 8601 格式时间戳
- `message_count`: 冗余字段，避免频繁 COUNT 查询
- `current_request_id`: 当前活跃请求 ID，用于取消操作
- `system_prompt`: 会话级系统提示词，在创建会话时存储，用于每次对话的上下文构建
- `max_iterations`: Agent 最大迭代次数，在创建会话时存储，控制 Agent 执行的最大循环次数
- `archived_at`: ISO 8601 格式时间戳，非空表示会话已归档

**system_prompt 和 max_iterations 存储机制：**
- **创建时存储**：`create_session()` 接收这两个参数并持久化到数据库
- **读取时使用**：`get_session()` 返回的 SessionInfo 包含这两个字段
- **不可变性**：这两个字段在会话创建后不可修改（如需修改应创建新会话）
- **默认值**：`system_prompt` 默认为 NULL（可选），`max_iterations` 默认为 50

#### messages 表

存储会话消息历史。

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

**字段说明：**
- `id`: 自增主键，用于分页
- `role`: 消息角色（user/assistant/system/tool）
- `metadata`: JSON 字符串，存储工具调用信息等扩展数据
- `timestamp`: ISO 8601 格式时间戳，用于时间范围查询

### 数据完整性约束

#### 外键约束
启用 SQLite 外键约束（`PRAGMA foreign_keys = ON`），确保：
- 删除会话时级联删除所有消息
- 无法为不存在的会话创建消息

#### 状态约束
在应用层验证 `status` 字段值，确保为以下枚举之一：
- `idle`: 空闲，可接受新请求
- `busy`: 忙碌，正在处理请求
- `error`: 错误状态，需要人工干预或自动恢复

## SQLiteStore 实现设计

### 初始化

```python
class SQLiteStore(SessionStore):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
```

**设计决策：**
- 延迟初始化数据库连接（首次使用时建立）
- 单连接实例复用，避免频繁打开关闭
- 连接生命周期与应用一致

### 连接管理

#### 初始化数据库
```python
async def _ensure_db(self) -> aiosqlite.Connection:
    if self._db is None:
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._create_tables()
    return self._db
```

**关键配置：**
- 启用外键约束
- 创建表结构（如果不存在）

#### 关闭连接
```python
async def close(self) -> None:
    if self._db is not None:
        await self._db.close()
        self._db = None
```

**调用时机：** 应用关闭时调用（通过 FastAPI shutdown event）

### 核心接口实现

#### create_session

**实现策略：**
1. 生成 UUID 作为 session_id
2. 获取当前时间戳（ISO 8601）
3. 执行 INSERT 语句
4. 返回 SessionInfo 实例

**并发安全：** 使用数据库唯一约束保证 session_id 不重复

#### get_session

**实现策略：**
1. 执行 SELECT 查询
2. 如果未找到，抛出 SessionNotFoundError
3. 返回 SessionInfo 实例

#### update_session_status

**实现策略：**
1. 使用乐观锁进行状态更新，确保并发安全
2. 同时更新 `updated_at` 时间戳
3. 检查受影响行数判断更新是否成功

**乐观锁实现方案：**

```sql
-- 带前置状态检查的更新
UPDATE sessions 
SET status = ?, 
    current_request_id = ?, 
    error_message = ?,
    updated_at = ?
WHERE session_id = ? 
  AND status = ?  -- 前置状态检查（乐观锁）
```

**乐观锁工作流程：**
1. **读取当前状态**：先查询会话的当前状态
2. **条件更新**：在 UPDATE 的 WHERE 子句中添加 `status = 当前状态` 条件
3. **检查结果**：通过 `changes()` 或受影响行数判断是否成功
4. **冲突处理**：如果受影响行数为 0，说明状态已被其他请求修改，抛出 `SessionStateError`

**示例代码：**
```python
async def update_session_status(
    self,
    session_id: str,
    status: SessionStatus,
    current_request_id: str | None = None,
    error_message: str | None = None,
    expected_status: SessionStatus | None = None,  # 乐观锁：期望的当前状态
) -> bool:
    db = await self._ensure_db()
    now = self._format_dt(self._now())  # 使用 UTC 时间
    
    # 构建带乐观锁的 UPDATE
    sql = """
        UPDATE sessions 
        SET status = ?, current_request_id = ?, error_message = ?, updated_at = ?
        WHERE session_id = ?
    """
    params: list[Any] = [status, current_request_id, error_message, now, session_id]
    
    # 如果提供了期望状态，添加乐观锁条件
    if expected_status is not None:
        sql += " AND status = ?"
        params.append(expected_status)
    
    cursor = await db.execute(sql, params)
    await db.commit()
    
    # 检查是否更新成功
    if cursor.rowcount and cursor.rowcount > 0:
        return True
    
    # 更新失败，判断原因
    try:
        current = await self.get_session(session_id)
    except SessionNotFoundError:
        raise  # 会话不存在
    
    if expected_status is not None:
        # 乐观锁冲突
        raise SessionStateError(session_id, current.status)
    
    # 其他情况（理论上不会到达这里）
    raise SessionNotFoundError(session_id)
```

**乐观锁优势：**
- **无锁等待**：不需要获取数据库锁，减少阻塞
- **自动检测冲突**：通过 WHERE 条件自动检测状态变化
- **适合读多写少**：会话状态更新频率较低，冲突概率小
- **配合应用层锁**：与 SessionManager 的 asyncio.Lock 配合使用，提供双重保护

#### archive_session

**实现策略：**
1. 设置 `archived_at` 和 `updated_at` 为当前时间
2. 执行 UPDATE 语句
3. 检查受影响行数判断操作是否成功
4. 返回归档后的 SessionInfo 实例

**异常处理：** 如果会话不存在（受影响行数为 0），抛出 SessionNotFoundError

#### delete_session

**实现策略：**
1. 执行 DELETE 语句
2. 外键约束自动级联删除消息
3. 检查受影响行数判断是否删除成功

**异常处理：** 如果会话不存在（受影响行数为 0），抛出 SessionNotFoundError

**注意：** busy 状态检查在 SessionManager 层执行，不在 SQLiteStore 层

#### list_sessions

**实现策略：**
1. 构建动态 SQL（支持状态和归档过滤）
2. 支持状态过滤（可选），支持归档过滤（`archived=True` → `archived_at IS NOT NULL`；`archived=False` → `archived_at IS NULL`）
3. 使用 LIMIT 和 OFFSET 分页
4. 执行 COUNT 查询获取总数
5. 返回 (会话列表, 总数) 元组

**排序规则：** 按 `updated_at DESC, session_id DESC` 排序，确保最近活动的会话在前，相同更新时间的会话按 ID 降序

**性能优化：** 使用索引加速状态过滤和时间排序

#### save_message

**实现策略：**
1. 获取当前时间戳
2. 序列化 metadata 为 JSON
3. 执行 INSERT 语句
4. 更新 sessions 表的 message_count 和 updated_at
5. 返回消息字典

**事务处理：** 使用数据库事务保证消息保存、计数更新和时间戳更新的原子性

**updated_at 更新：** 每次保存消息时同步更新会话的 `updated_at` 时间戳，反映会话的最后活动时间

#### get_messages

**实现策略：**
1. 构建动态 SQL（支持 before 时间过滤）
2. 使用 ORDER BY timestamp ASC, id ASC 保证时间正序，相同时间戳的消息按插入顺序
3. 使用 LIMIT 限制返回数量
4. 反序列化 metadata JSON
5. 如果结果为空，验证会话是否存在（避免返回空列表给不存在的会话）

**分页支持：** 通过 `before` 参数实现基于时间戳的分页

**会话验证：** 当查询结果为空时，会调用 `get_session()` 验证会话是否存在，如果不存在则抛出 `SessionNotFoundError`

#### get_message_count

**实现策略：**
1. 直接读取 sessions 表的 message_count 字段
2. 避免频繁 COUNT 查询

**一致性保证：** message_count 在 save_message 时同步更新

### updated_at 更新机制

`updated_at` 字段记录会话的最后修改时间，在以下场景自动更新：

| 操作 | 是否更新 updated_at | 说明 |
|------|-------------------|------|
| `create_session` | ✅ 是 | 设置为创建时间 |
| `update_session_status` | ✅ 是 | 状态变更时更新 |
| `save_message` | ✅ 是 | 保存新消息时更新 |
| `archive_session` | ✅ 是 | 归档时同步更新时间戳 |
| `get_session` | ❌ 否 | 只读操作，不更新 |
| `get_messages` | ❌ 否 | 只读操作，不更新 |
| `list_sessions` | ❌ 否 | 只读操作，不更新 |
| `delete_session` | ❌ 否 | 删除操作，无需更新 |

**设计理由：**
- **反映活动时间**：`updated_at` 作为会话最后活动时间的指标
- **排序依据**：用于按最近活动时间排序会话列表
- **清理依据**：作为过期会话清理的判断依据
- **监控指标**：便于追踪会话活跃度

### 事务处理

#### 事务范围
SQLite 默认自动提交模式，需要显式事务保证原子性。

**使用事务的场景：**
- `save_message`: 消息保存 + 计数更新 + updated_at 更新
- `delete_session`: 会话删除 + 消息级联删除（由外键约束自动处理）

**事务实现：**
```python
await db.execute("BEGIN")
try:
    # 执行多个操作
    await db.execute(...)
    await db.execute(...)
    await db.commit()
except Exception:
    await db.rollback()
    raise
```

**异常处理：** 使用 try-except 确保异常时回滚事务，特别是 `aiosqlite.IntegrityError`（外键约束违反）转换为 `SessionNotFoundError`

#### 隔离级别
使用 SQLite 默认隔离级别（SERIALIZABLE），保证：
- 读操作看到一致的数据快照
- 写操作串行执行

## 并发控制设计

### SQLite 并发特性

#### 读写并发
- **多读单写**：SQLite 支持多个读取者同时访问
- **写串行化**：写入操作通过数据库锁串行化
- **WAL 模式**：启用 Write-Ahead Logging 提高并发性能

**WAL 模式配置：**
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

**优势：**
- 读写不阻塞
- 更好的并发性能
- 适合读多写少场景

### 应用层并发控制

#### SessionManager 锁策略
- 每个会话独立的 asyncio.Lock
- 保护状态转换的原子性
- 避免同一会话的并发请求冲突

**设计理由：**
- 数据库锁粒度太粗（整个数据库）
- 应用层锁提供更细粒度的控制
- 单实例部署无需分布式锁

#### 状态一致性保证
```
SessionManager.send_message()
    ├─ 获取会话锁
    ├─ 检查状态是否为 idle/error/busy
    ├─ 更新状态为 busy（数据库 UPDATE，带乐观锁）
    ├─ 保存用户消息
    ├─ 构建上下文
    ├─ 创建 AgentRunner 实例
    ├─ 执行 Agent
    ├─ 保存助手消息（如果成功）
    ├─ 更新状态为 idle/error（数据库 UPDATE，带乐观锁）
    └─ 释放会话锁和 CancellationToken
```

**异常情况处理：**
- 使用 try-finally 确保锁释放和资源清理
- 数据库操作失败时回滚状态
- 取消时恢复状态为 idle
- 错误时更新状态为 error 并记录错误信息

## 资源管理

### 数据库连接生命周期

#### 连接创建
- 应用启动时延迟创建
- 首次访问时初始化
- 创建表结构和索引

#### 连接复用
- 单连接实例全局复用
- 避免频繁打开关闭的开销
- SQLite 单文件数据库支持并发读取

#### 连接关闭
- FastAPI shutdown event 时关闭
- 确保所有事务完成
- 释放文件句柄

### 错误处理策略

#### 数据库错误分类
- **连接错误**：文件权限、磁盘空间不足 → 抛出 DatabaseError
- **约束错误**：外键违反、唯一约束 → 抛出 ValidationError
- **查询错误**：SQL 语法错误 → 抛出 InternalError

#### 重试策略
- **不重试**：SQLite 本地数据库，无网络问题
- **立即失败**：快速暴露问题

#### 错误传播
- 捕获 aiosqlite 异常
- 转换为领域异常（SessionError 子类）
- 保留原始异常信息用于调试

## 数据迁移策略

### Schema 版本管理

#### 版本表
```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

#### 迁移脚本
- 按版本号命名（`001_initial.sql`, `002_add_column.sql`）
- 应用启动时检查并执行未应用的迁移
- 每个迁移在事务中执行

**设计原则：**
- 向后兼容：新增字段提供默认值
- 幂等性：迁移脚本可重复执行
- 原子性：单个迁移失败时回滚

### 备份策略

#### 在线备份
- SQLite 支持在线备份（`.backup` 命令）
- 不阻塞读写操作
- 适合定时备份

#### 文件复制
- 停止应用后直接复制数据库文件
- 简单可靠
- 适合迁移和灾难恢复

## 性能考虑

### 索引策略

#### 已创建索引
- `idx_sessions_status`: 加速状态过滤查询
- `idx_sessions_created_at`: 加速时间排序
- `idx_messages_session_id`: 加速会话消息查询
- `idx_messages_timestamp`: 加速时间范围查询

#### 索引维护
- SQLite 自动维护索引
- 写入时有轻微性能开销
- 查询性能显著提升

### 查询优化

#### 避免 SELECT *
- 只查询需要的字段
- 减少内存占用

#### 分页查询
- 使用 LIMIT 和 OFFSET
- 避免一次性加载大量数据

#### COUNT 优化
- 使用冗余的 message_count 字段
- 避免频繁 COUNT 查询

### 数据清理

#### 过期会话清理
- 删除超过保留期的会话和消息
- 使用事务保证原子性

**清理策略：**（可选功能，不在核心范围内）
- 保留最近 N 天的会话
- 或保留最近 N 个会话

## 安全考虑

### SQL 注入防护

#### 参数化查询
- 所有查询使用参数化（`?` 占位符）
- 不拼接 SQL 字符串
- aiosqlite 自动转义参数

### 数据验证

#### 输入验证
- session_id 验证 UUID 格式
- status 验证枚举值
- role 验证枚举值

#### 输出编码
- metadata JSON 序列化
- 防止存储恶意数据

### 文件权限

#### 数据库文件
- 限制文件权限（600）
- 只有应用用户可读写
- 防止未授权访问

## 测试策略

### 单元测试

#### 内存数据库
- 使用 `:memory:` 数据库
- 快速隔离测试
- 每个测试独立数据库

#### 测试覆盖
- 所有 SessionStore 接口方法
- 异常情况处理
- 边界条件

### 集成测试

#### 临时文件数据库
- 使用临时文件数据库
- 测试真实 I/O 行为
- 测试并发场景

## 部署配置

### 数据库文件位置

**推荐路径：**
- 开发环境：`./data/laffybot.db`
- 生产环境：`/var/lib/laffybot/laffybot.db`

**配置方式：**
- 通过配置文件指定路径
- 自动创建父目录

### 初始化脚本

应用启动时自动：
1. 创建数据库文件（如果不存在）
2. 创建表结构和索引
3. 应用迁移脚本
4. 配置 WAL 模式

### 监控指标

**基础指标：**
- 数据库文件大小
- 会话总数
- 消息总数

**健康检查：**
- 数据库连接可用性
- 磁盘空间检查

## 与 SessionManager 集成

### 依赖注入

```python
# 应用启动时
store = SQLiteStore(config.db_path)
session_manager = SessionManager(
    store=store,
    context_builder=context_builder,
    tool_registry=tool_registry,
    provider_factory=provider_factory,
)

# 应用关闭时
await store.close()
```

### 生命周期管理

**FastAPI 事件处理：**
- `startup`: 创建 SQLiteStore 实例
- `shutdown`: 关闭数据库连接

**异常处理：**
- 启动失败：快速失败，记录错误日志
- 运行时错误：转换为领域异常，返回错误响应

## 扩展性考虑

### 存储后端切换

#### 接口抽象
- SessionStore 接口定义清晰
- SQLiteStore 是接口的一种实现
- 可替换为其他存储后端（PostgreSQL、Redis）

#### 切换策略
- 实现新的 SessionStore 子类
- 修改依赖注入配置
- 无需修改 SessionManager 代码
