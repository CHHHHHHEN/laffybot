# 会话-模型绑定设计

> **文档性质**：设计文档  
> **最后更新**：2026-05-14  
> **实现状态**：待实现  
> **模拟验证**：2026-05-14  
> **模拟结论**：计划可行，详见下方各节补充

---

## 现状与问题

当前所有会话共用全局选中的 provider + model：

- `SessionInfo.model`（仅存模型名，不存 provider）在创建时做一次快照存储
- `send_message()` 每次执行时从 `ProviderStore.get_active_selection()` 重新解析（含 provider）
- 切换全局选中会**即时影响所有会话的下一次消息执行**

### 带来的问题

1. **切换风险**：用户切换全局模型后，旧会话下一轮回复可能用了不兼容的模型
2. **标题生成依赖不明**：Auto-Title 需要调用 LLM 生成标题，但不知道用哪个模型
3. **会话隔离不足**：不同会话无法绑定不同的模型

---

## 设计目标

1. 每个会话独立绑定 provider + model，互不干扰
2. 创建会话时默认继承 `default_session_config`（由用户在设置中配置）
3. 支持在会话内切换 provider + model

---

## 设计要点

### SessionInfo 字段变更

| 变更 | 字段 | 类型 | 说明 |
|------|------|------|------|
| 删除 | `model` | — | 语义模糊，被 `provider_id` + `model_name` 取代 |
| 新增 | `provider_id` | str | 会话绑定的提供商 ID |
| 新增 | `model_name` | str | 会话绑定的模型名 |

### Store 接口变更

`SessionStore`（`laffybot/session/store.py`）：

- `create_session()` 签名：参数 `model: str` 改为 `provider_id: str, model_name: str`
- 新增 `update_session_model(session_id, provider_id, model_name, expected_status: SessionStatus | tuple[SessionStatus, ...] | None = ("idle", "error")) → SessionInfo`：更新绑定的 provider 和 model。内部通过 `expected_status` 做 SQL 层乐观锁（单值用 `WHERE status = ?`，多值用 `WHERE status IN (...?)`），默认接受 idle 或 error，仅拒绝 busy 状态。防止执行消息时被并发修改配置。
- `_row_to_session()` 读取 `provider_id` + `model_name` 两列

### AppSettingStore 新增

新增独立的 `AppSettingStore`（`laffybot/session/app_setting_store.py`），负责管理全局键值对配置，与 provider/model 管理解耦。SQLite 实现拥有 `app_settings` 表的所有权，该表从 `ProviderStore` 的 schema 中移除。

提供类型化方法（而非通用 kv 接口），避免调用方自行处理 JSON 序列化/反序列化：

| 方法 | 签名 | 说明 |
|------|------|------|
| `get_default_session_config` | `() → ProviderModelPair \| None` | 读取新建会话默认模型配置，返回 None 表示未配置 |
| `set_default_session_config` | `(provider_id: str, model_name: str) → None` | 写入默认模型配置 |
| `delete_default_session_config` | `() → None` | 清除默认模型配置 |
| `get_summary_model` | `() → ProviderModelPair \| None` | 读取总结模型配置，返回 None 表示未配置 |
| `set_summary_model` | `(provider_id: str, model_name: str) → None` | 写入总结模型配置 |
| `delete_summary_model` | `() → None` | 清除总结模型配置 |

`ProviderModelPair` 为 `dataclass` 或 `TypedDict`，包含 `provider_id: str` 和 `model_name: str` 两个字段。

内部存储仍为 `app_settings` 表，key 为 `default_session_config` / `summary_model`，value 为 JSON 字符串。单一字段原子写入由 SQLite 单行更新保证。

### ProviderStore 接口移除

`ProviderStore` 移除以下与全局选中相关的方法：`get_active_selection()`、`set_active_selection()`、`clear_active_selection()`。

全局选中的概念不再存在。新建会话的默认值改为从 `AppSettingStore` 的 `default_session_config` key 读取。

### 数据库变更

sessions 表：

| 变更 | 列 | 类型 | 说明 |
|------|------|------|------|
| 删除 | `model` | TEXT | 被 provider_id + model_name 取代 |
| 新增 | `provider_id` | TEXT NOT NULL | 会话绑定的提供商 ID |
| 新增 | `model_name` | TEXT NOT NULL | 会话绑定的模型名 |

`provider_id` 不设外键约束。删除 provider 后已有会话会出现悬浮引用，由应用层在 `send_message()` 和模型切换时检测并返回 404 提示（见"执行消息"章节）。不设外键是为了避免删除 provider 时级联删除会话，或 `SET NULL` 破坏 NOT NULL 约束。

> **开发阶段说明**：当前采用删库重建策略，`CREATE TABLE` 直接使用新 schema。上线前需提供数据迁移方案，避免用户数据丢失。

### 数据库连接

当前 `SessionStore` 和 `ProviderStore` 各自持有独立的 SQLite 连接（两个 `sqlite3.connect`），`AppSettingStore` 也独立创建连接。三个连接并发操作同一 `.db` 文件，通过 WAL 模式 + 忙重试处理并发。

**各 Store 自行管理连接**，不引入统一 `Database` 类：

- 每个 Store 的 SQLite 实现接受 `db_path: str`，内部创建独立 `aiosqlite.Connection`
- 各连接在 `__init__` 中执行 `PRAGMA journal_mode=WAL`，允许读-写并发
- 各连接设置 `aiosqlite.Row` 作为 row factory
- 各连接执行 `PRAGMA foreign_keys = ON`
- 写入操作对 `SQLITE_BUSY` 做最多 3 次重试（指数退避），各 Store 自行实现或使用统一的重试工具函数

**事务边界**：调用方自行管理 `BEGIN` / `COMMIT` / `ROLLBACK`，Store 不自动包装事务。

> 当前 `SQLiteSessionStore.__init__` 和 `SQLiteProviderStore.__init__` 已接受 `db_path: str`，`SQLiteAppSettingStore` 沿用相同签名，无需修改调用方。不存在连接共享问题，Manager 层和 API 层无需任何修改。

### 创建会话

`SessionManager.create_session()` 新增可选参数 `provider_id` 和 `model_name`（`laffybot/session/manager.py`）：

| 传入情况 | 行为 |
|----------|------|
| 同时传入 `provider_id` + `model_name` | 校验 provider 存在且 model 属于该 provider，通过后写入 session |
| 均不传 | 从 `AppSettingStore.get_default_session_config()` 读取默认配置 |

- `provider_id` 和 `model_name` 必须同时传入或同时不传（违反则 422）
- 传入时校验失败返回 404（provider 不存在 / model 不属于 provider）
- `default_session_config` 未配置时返回 400，提示用户先在设置中配置默认模型
- 前端收到 400 时弹出 Toast 错误提示（5 秒自动消失），文案如"请先在设置中配置默认会话模型"。`toast-store.ts` 已提供 `addToast(type, message)` 接口，`type: 'error'` 的 Toast 不会自动消失需手动关闭，实现时传 `type: 'info'` 或使用 `setTimeout` 在 5 秒后调用 `removeToast`

### 执行消息

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

> **`ModelNotFoundError` 迁移（不向后兼容）**：当前构造函数接收 `model_id: str`（内部数据库自增主键），全面迁移为接收 `model_name: str`（用户可理解的名称）。`self.model_id` 属性一并移除（`api/errors.py` 仅用 `str(exc)`，未访问 `.model_id`，无需修改）。
>
> **受影响调用方及迁移方式**：
> | 位置 | 方法 | 迁移方式 |
> |------|------|----------|
> | `provider_store.py:335` | `delete_model(model_id)` | 删除前先 SELECT name，若 row 不存在用 `f"id:{model_id}"` 构造异常；若 row 存在但后续 DELETE rowcount == 0（并发删除），用查询到的 name 构造异常 |
> | `provider_store.py:418` | `set_active_selection(provider_id, model_id)` | 该方法随全局选中概念移除（见 §ProviderStore 接口移除），不迁移 |
>

前端收到此类错误时，应展示提示信息并允许用户通过模型切换控件重新选择。

#### SSE 流错误处理补充

`send_message()` 是 async generator，`ProviderNotFoundError` 和 `ModelNotFoundError` 在 lock 块内、try 块外抛出，不会进入 `except Exception` 分支。

**实现要求**：将 `send_message()` 中 provider resolution（`get_provider_config` + model 校验）移至 `try` 块内，或将这两个异常加入 `try/except` 保护范围。同时在 `_stream_session_events()`（`laffybot/api/routes.py`）中新增 `except ProviderNotFoundError` 和 `except ModelNotFoundError` 的捕获，将它们映射为 SSE error event 而非 500 崩溃。映射规则：

| 异常类型 | SSE error code | 行为 |
|----------|---------------|------|
| `ProviderNotFoundError` | `PROVIDER_NOT_FOUND` | yield error event，stream 结束 |
| `ModelNotFoundError` | `MODEL_NOT_FOUND` | yield error event，stream 结束 |

### 会话内切换模型

`PUT /api/v1/sessions/{session_id}/model`

请求体：`{ "provider_id": "deepseek", "model_name": "deepseek-chat" }`

| 条件 | 状态码 |
|------|--------|
| 成功 | 200，返回 `SessionResponse` |
| provider_id + model_name 未同时提供 | 422 |
| provider 不存在 / model 不属于 provider | 404 |
| 会话不存在 | 404 |
| 会话状态为 busy | 409 |

`SessionManager` 侧的处理流程：
1. 校验 provider 存在且 model 属于该 provider（失败抛 `ProviderNotFoundError` / `ModelNotFoundError` → 404）
2. 调用 `store.update_session_model(session_id, provider_id, model_name, expected_status=("idle", "error"))`
   - 内部 SQL 条件更新：`UPDATE sessions SET ... WHERE session_id=? AND status IN (...?)`
   - 受影响行数为 0 → 会话为 busy → 抛 `SessionBusyError` → 409
3. 返回更新后的 `SessionInfo`

> **关于 `expected_status` 默认值**：`update_session_model` 的 `expected_status` 默认 `("idle", "error")`，而 `update_session_status` 默认 `None`。两者默认值不同的原因是——切换模型需要保证会话不在执行中（busy），但异常状态的会话也应允许切换模型以恢复（如提供商 key 过期导致 error，用户切到有效模型即可恢复）；而状态更新（如异常后强制覆写为 idle）有时需要无条件执行。语义不同，不应统一。
>
> **`expected_status` 类型语义**：单值用 `WHERE status = ?`，元组用 `WHERE status IN (...?)`，`None` 跳过 status 条件（无条件 `UPDATE`）。`update_session_model` 默认接受 idle 和 error，调用方可在特定场景传单值做严格校验；`update_session_status` 默认 `None`，调用方可传具体状态做条件更新。

切换即时生效，下一条消息使用新配置。使用 `expected_status` 做条件更新，与 `send_message()` 的状态变更机制一致，无需额外锁排队。若会话正忙则立即返回 409（不阻塞、不排队），前端可根据 `isStreaming` 状态提前禁用切换控件避免用户误触。

### API Schema 变更

`SessionCreateRequest`（`laffybot/api/schemas.py`）新增可选字段 `provider_id: str | None` + `model_name: str | None`。

新增 `SessionModelUpdateRequest`：字段 `provider_id: str` + `model_name: str`。

`SessionBase` 及所有子类（`SessionResponse` / `SessionDetailResponse` / `SessionListItem`）：字段 `model: str` 替换为 `provider_id: str` + `model_name: str`。

### 前端类型变更

- `CreateSessionRequest`：新增可选字段 `provider_id` + `model_name`
- `SessionResponse`（及列表项）：`model` 替换为 `provider_id` + `model_name`
- 新增 `UpdateSessionModelRequest`：包含 `provider_id` + `model_name`
- 新增 `updateSessionModel` API 函数，请求 `PUT /sessions/{session_id}/model`

### 依赖注入补充

`SessionManager` 新增 `app_setting_store: AppSettingStore` 参数（`laffybot/session/manager.py`），用于 `create_session()` 读取默认配置：

```python
class SessionManager:
    def __init__(
        self,
        store: SessionStore,
        provider_store: ProviderStore,
        app_setting_store: AppSettingStore,  # 新增
        tool_registry: ToolRegistry,
        context_config: ContextConfig | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
```

`laffybot/api/dependencies.py` 对应变更：

| 新增/修改 | 函数 | 说明 |
|-----------|------|------|
| 新增 | `build_app_setting_store(config) → AppSettingStore` | 创建 `SQLiteAppSettingStore(config.database_path)` |
| 新增 | `get_app_setting_store(request) → AppSettingStore` | FastAPI dependency |
| 修改 | `build_session_manager(...)` | 新增参数 `app_setting_store: AppSettingStore`，透传给 `SessionManager` |

`ProviderStore` 不再需要暴露给 settings 路由做校验——validation 由 routes 层同时持有 `provider_store` + `app_setting_store` 完成：provider_store 用于校验 provider 存在性和 model 归属，app_setting_store 用于读写。

### 新建会话流程简化

解耦后，模型选择由聊天内的模型切换控件完成，不再需要创建会话时选择模型。

**变更**：移除新建会话对话框组件及其所有引用。

**新流程**：

| 触发位置 | 旧行为 | 新行为 |
|----------|--------|--------|
| Sidebar "新建会话" 按钮 | 弹出新建会话对话框 | 直接创建会话并跳转到聊天页 |
| ChatPage 空状态 "新建会话" 按钮 | 弹出新建会话对话框 | 同上，直接创建并跳转 |
| ChatPage 有会话时的新建 | 弹出新建会话对话框 | 输入框右侧添加 `+` 按钮，直接创建并跳转 |

创建会话后，默认继承 `default_session_config` 中配置的 provider + model（若未配置则创建失败，引导用户先在设置中配置默认模型）。用户如需切换模型，通过输入框旁的模型选择控件完成。`max_iterations` 在当前版本中不通过 UI 设置（API 层面保留字段）。

**关于 `max_iterations` 的语义**：它控制的是**每次 `send_message()` 调用中 Agent 的最大 LLM 迭代次数**（默认 50），不是整个会话的总次数。每次用户发送一条消息，Agent Runner 循环执行 `for iteration in range(max_iterations)`，每轮包含一次 LLM 请求 + 可能的工具调用。达到上限后停止，`done` 事件的 `stop_reason` 为 `"max_iterations"`。这是一个 per-request 的安全阀，防止单次请求陷入无限工具调用循环。

**关于 `system_prompt` 的变更**：`system_prompt` 已从 per-session 参数移除，改为全局 UI 设置。`SessionCreateRequest` 不再接收 `system_prompt` 字段。系统提示可通过 `GET/PUT /api/v1/settings/system-prompt` 管理，对所有新会话生效。

---

## 移除清单

以下为解耦后各层需移除或替换的代码，按文件组织。

### 后端

|laffybot/session/provider_store.py||
|--|--|
| 移除 | `ActiveSelection` dataclass |
| 移除 | 常量 `_ACTIVE_PROVIDER_KEY`、`_ACTIVE_MODEL_KEY` |
| 移除 | ABC 中的 `get_active_selection()`、`set_active_selection()`、`clear_active_selection()` |
| 移除 | `SQLiteProviderStore` 中的上述三个方法实现 |
| 移除 | `_PROVIDER_SCHEMA_SQL` 中的 `app_settings` 表 DDL（由 `SQLiteAppSettingStore` 接管） |
| 修改 | `delete_provider()`：移除 active selection 检查和清除逻辑，返回值从 `bool` 简化为 `None` |
| 修改 | `delete_model()`：移除 active selection 检查和清除逻辑 |

|laffybot/session/models.py||
|--|--|
| 替换 | `SessionInfo.model: str` → `SessionInfo.provider_id: str` + `SessionInfo.model_name: str` |

|laffybot/session/store.py||
|--|--|
| 修改 | `_SCHEMA_SQL`：sessions 表 `model TEXT NOT NULL` → `provider_id TEXT NOT NULL, model_name TEXT NOT NULL` |
| 修改 | `create_session()` 参数：`model: str` → `provider_id: str, model_name: str` |
| 修改 | `_row_to_session()`：读 `model` 列改为读 `provider_id` + `model_name` 两列 |
| 新增 | `update_session_model()` 方法 |

|laffybot/session/manager.py||
|--|--|
| 移除 | import `NoActiveProviderError` |
| 新增 | `__init__` 参数 `app_setting_store: AppSettingStore` |
| 修改 | `create_session()`：移除 `get_active_selection()` 调用，新增可选参数 `provider_id`/`model_name`，回调 `AppSettingStore.get_default_session_config()` |
| 修改 | `send_message()`：移除 `get_active_selection()` 调用，改为从 `session.provider_id` 获取 provider、`session.model_name` 获取 model。将 provider resolution 移入 `try` 块以正确捕获 `ProviderNotFoundError`/`ModelNotFoundError` |
| 修改 | `_build_messages()`：`model or session.model` → `model or session.model_name` |

|laffybot/session/errors.py||
|--|--|
| 无变更 | `NoActiveProviderError` 保留不动（移除引用即可，类定义无需删除） |

|laffybot/api/schemas.py||
|--|--|
| 移除 | `ActiveSelectionResponse` |
| 移除 | `ActiveSelectionUpdateRequest` |
| 修改 | `SessionCreateRequest`：新增可选字段 `provider_id: str | None = None`、`model_name: str | None = None`；后续已移除 `system_prompt` 字段 |
| 修改 | `SessionBase`：`model: str` → `provider_id: str`、`model_name: str` |
| 新增 | `SessionModelUpdateRequest`：字段 `provider_id: str`、`model_name: str` |

|laffybot/api/routes.py||
|--|--|
| 移除 | import `ActiveSelectionResponse`、`ActiveSelectionUpdateRequest` |
| 移除 | GET `/providers/active` 路由处理函数 |
| 移除 | PUT `/providers/active` 路由处理函数 |
| 修改 | `_serialize_session()`：`session.model` → `session.provider_id`、`session.model_name` |
| 修改 | `delete_provider` 路由响应：移除 `active_cleared` 字段 |
| 新增 | PUT `/sessions/{session_id}/model` 路由 |
| 新增 | GET/PUT/DELETE `/settings/default-session-model` 路由 |
| 新增 | GET/PUT/DELETE `/settings/summary-model` 路由 |
| 修改 | `_stream_session_events()`：新增 `except ProviderNotFoundError` 和 `except ModelNotFoundError` 捕获 |

|laffybot/api/dependencies.py||
|--|--|
| 新增 | `build_app_setting_store(config) → AppSettingStore` |
| 新增 | `get_app_setting_store(request) → AppSettingStore` FastAPI dependency |
| 修改 | `build_session_manager()`：新增 `app_setting_store` 参数 |

|laffybot/session/__init__.py||
|--|--|
| 无变更 | 不 export `AppSettingStore`（由调用方直接 import），不 export `NoActiveProviderError`（已是 provider_store 的 detail） |

### 前端

|ui/src/lib/api.ts||
|--|--|
| 移除 | `ActiveSelectionResponse` 接口 |
| 移除 | `ActiveSelectionUpdateRequest` 接口 |
| 移除 | `getActiveSelection()` 函数 |
| 移除 | `setActiveSelection()` 函数 |
| 修改 | `CreateSessionRequest`：新增可选字段 `provider_id?: string`、`model_name?: string` |
| 修改 | `SessionResponse`：`model: string` → `provider_id: string`、`model_name: string` |
| 新增 | `UpdateSessionModelRequest` 接口：`{ provider_id: string; model_name: string }` |
| 新增 | `updateSessionModel(sessionId, data)` 函数：`PUT /sessions/{session_id}/model` |

|ui/src/hooks/use-providers.ts||
|--|--|
| 移除 | `useActiveSelection()` hook |
| 移除 | `useSetActiveSelection()` hook |
| 修改 | `useDeleteProvider()`：移除 `invalidateQueries(['active-selection'])` |

|ui/src/hooks/use-sessions.ts||
|--|--|
| 新增 | `useUpdateSessionModel()`：mutation 调用 `api.updateSessionModel()`，成功后 invalidate `['sessions']` |

|ui/src/components/ui/NewSessionDialog.tsx||
|--|--|
| 移除 | 整个文件及所有引用 |

|ui/src/components/layout/GlobalModelSelector.tsx||
|--|--|
| 移除 | 整个文件及所有引用 |

|ui/src/components/layout/Sidebar.tsx||
|--|--|
| 修改 | 移除 `NewSessionDialog` 的 import、state、render；"新建会话"按钮直接调用 `useCreateSession().mutateAsync({})` 并导航 |
| 修改 | 会话列表项：`session.model` → `${session.provider_id}/${session.model_name}` 或 `session.model_name` |
| 移除 | 移除 `useActiveSelection()` 相关逻辑（不再需要展示全局选中模型） |

|ui/src/components/chat/ChatHeader.tsx||
|--|--|
| 修改 | `session.model` → 展示 `provider_id / model_name` |

|ui/src/components/chat/InputBar.tsx||
|--|--|
| 修改 | 新增 props：`sessionProviderId: string`、`sessionModelName: string`、`sessionId: string` |
| 新增 | 输入框左侧渲染两级模型下拉选择器 |
| 新增 | 模型切换调用 `updateSessionModel()`，失败时 Toast 提示（5 秒自动消失），控件回退旧值 |

|ui/src/pages/ChatPage.tsx||
|--|--|
| 移除 | `NewSessionDialog` 的 import、state、render |
| 修改 | 空状态"新建会话"按钮 → 直接调用 `useCreateSession().mutateAsync({})` |
| 新增 | 有会话时输入框右侧添加 `+` 按钮 → 调用 `useCreateSession().mutateAsync({})` |
| 修改 | 传递 session provider/model 给 InputBar |

|ui/src/components/layout/GlobalModelSelector.tsx||
|--|--|
| 移除 | 全局模型选择器不再需要 |

|ui/src/pages/ProviderSettingsPage.tsx||
|--|--|
| 新增 | "默认会话模型"配置区：provider 下拉 + model 下拉 + 保存/清除 |
| 新增 | "总结模型"配置区（仅在 Auto-Title 上线后启用）：provider 下拉 + model 下拉 + 保存/清除 |

---

### UI 交互 — 模型切换控件

**位置**：模型切换控件置于消息输入框（`InputBar`）左侧，与发送按钮对称。

**数据源**：来自 `use-providers` hook 返回的 providers 列表及各自 models。

**InputBar 接口变更**：新增以下 props：

| Prop | 类型 | 来源 |
|------|------|------|
| `sessionId` | `string` | 从 ChatPage 的 URL param 获取 |
| `providerId` | `string` | 当前 session 的 `provider_id` |
| `modelName` | `string` | 当前 session 的 `model_name` |

ChatPage 从 `useSessionById(sessionId)` 获取 session 信息，提取 `providerId`/`modelName` 传给 InputBar。InputBar 内部使用 `useProviders()`/`useModels()` 获取可选列表，调用 `api.updateSessionModel()` 进行切换。

**操作流程**：
6. 失败时：Toast 提示错误信息（5 秒自动消失），控件回退到旧值

**禁用条件**：
- 会话状态为 `busy`（`isStreaming === true`）时禁用
- API 调用中禁用

### 新增路由

新增 `PUT /api/v1/sessions/{session_id}/model` 端点。错误映射：`SessionBusyError` → 409，`ProviderNotFoundError` / `ModelNotFoundError` → 404。

### 默认会话模型配置

`default_session_config` 决定新建会话时默认使用哪个 provider + model，替代原全局选中概念。

**存储**：通过 `AppSettingStore.get_default_session_config()` / `set_default_session_config()` / `delete_default_session_config()` 读写，内部存储为 `app_settings` 表的 JSON 值。

**API 端点**：

| 方法 | 路径 | 说明 | 响应 |
|------|------|------|------|
| GET | `/api/v1/settings/default-session-model` | 获取默认会话模型 | `{ provider_id, model_name }` 或 204 |
| PUT | `/api/v1/settings/default-session-model` | 设置默认会话模型 | 200 `{ provider_id, model_name }` |
| DELETE | `/api/v1/settings/default-session-model` | 清除配置 | 200 `{ status: "cleared" }` |

PUT 校验规则与 `summary_model` 一致：`provider_id` + `model_name` 必须同时提供，provider 必须存在且 model 属于该 provider。

**UI 配置入口**：位于设置页面的提供商配置区域，与总结模型配置同级。用户在此配置新建会话时默认继承的模型。

---

## 全局总结专用模型

> **与"会话-模型绑定"是正交的**：会话绑定解决"用哪个模型对话"，全局总结模型解决"用哪个轻量模型做标题生成"。两者独立配置，互不依赖。

### 动机

对话使用的模型可能较大、较贵（如 DeepSeek-V3），不适合用于标题生成这类轻量任务。

### 存储方式

通过 `AppSettingStore.get_summary_model()` / `set_summary_model()` / `delete_summary_model()` 读写，内部存储为 `app_settings` 表 `summary_model` key 的 JSON 值。

### API 端点

| 方法 | 路径 | 说明 | 响应 |
|------|------|------|------|
| GET | `/api/v1/settings/summary-model` | 获取总结模型配置 | `{ provider_id, model_name }` 或 204 |
| PUT | `/api/v1/settings/summary-model` | 设置总结模型配置 | 200 `{ provider_id, model_name }` |
| DELETE | `/api/v1/settings/summary-model` | 清除总结模型配置 | 200 `{ status: "cleared" }` |

PUT 校验：`provider_id` + `model_name` 必须同时提供，provider 必须存在且 model 属于该 provider，校验失败返回 422。校验通过后调用 `AppSettingStore.set_summary_model()` 原子写入。

### 回退逻辑

```
Auto-Title 选择模型:
  1. `AppSettingStore.get_summary_model()` 返回非空 `ProviderModelPair`
     → 得到 provider_id + model_name
     → get_provider_config(provider_id) 解析配置
     → 用 model_name 作为模型
  2. 未配置（key 不存在或 JSON 不完整）
     → 用 session.provider_id → get_provider_config() 解析配置
     → 用 session.model_name 作为模型
```

- 全局配置对所有会话共享，不在 SessionInfo 上做逐会话覆盖
- 读取时返回 `ProviderModelPair` 或 `None`，内部 JSON 解析对调用方透明

> **注意**：退回到 `session.model_name` 意味着标题生成使用与对话相同的模型。如果对话模型成本较高（如 reasoning 或图像输入模型），建议设置 `summary_model` 使用更廉价的模型，避免 Auto-Title 每次调用产生不必要的开销。
>
> **容错处理**：步骤 1 和步骤 2 中的 `get_provider_config(provider_id)` 若对应的 provider 已被删除，会抛出 `ProviderNotFoundError`。Auto-Title 应捕获此异常并跳过标题生成（记录 warn 日志），而非向上传播导致 500 错误。

### UI 配置入口

位于设置页面的提供商配置区域（`SettingsPage` → `ProviderSettingsPage`），新增"总结模型"配置区：

- 提供 provider 下拉选择器 + model 下拉选择器
- 保存时调用 `PUT /api/v1/settings/summary-model`
- 清除时调用 `DELETE /api/v1/settings/summary-model`
- 仅在 Auto-Title 功能上线后启用

### Config 模型

`laffybot/config.py` 中不新增总结模型字段——所有配置均通过 UI + API 完成，存储在 `AppSettingStore` 中。

---

## 依赖关系

```
会话-模型绑定（此文档）
  ├── 解决：用哪个模型对话
  ├── 依赖：SessionStore 接口变更 + AppSettingStore（default_session_config）
  └── 被 Auto-Title 依赖（需要 SessionInfo.provider_id + model_name 字段）

默认会话模型配置（此文档）
  ├── 解决：新建会话默认用哪个模型
  ├── 依赖：AppSettingStore.get_default_session_config()
  └── 被会话-模型绑定依赖（create_session 需要读取默认值）

全局总结模型配置（此文档）
  ├── 解决：用哪个轻量模型做标题生成
  ├── 依赖：AppSettingStore.get_summary_model()
  └── 与会话-模型绑定正交，独立配置
      └── Auto-Title 选择逻辑：先查 summary_model，
           有（JSON 完整）则用总结专用模型，无则退回到 session.provider_id + session.model_name
```

Auto-Title 不直接依赖整个解耦机制上线——它仅依赖 `SessionInfo` 拥有 `provider_id` 和 `model_name` 两个字段即可。消息执行层是否也从 session 读取（而非全局选中）可后续独立上线。

## 实现顺序建议

```
会话-模型绑定：
  1. 数据库：sessions 表加 provider_id + model_name 列，删 model 列（开发阶段删库重建）
  2. SessionStore：create_session 签名变更 + update_session_model（含 expected_status）
  3. AppSettingStore：实现独立 Store（类型化方法），接管 app_settings 表
  4. Manager：send_message() 改为从 session 读取 provider + model
  5. API：新增 PUT /sessions/{session_id}/model 端点
  6. UI：模型切换控件 + 移除新建会话对话框

默认会话模型配置（与会话-模型绑定同步上线，是新建会话的前提）：
  1. AppSettingStore：已在上一步实现
  2. API：新增 GET/PUT/DELETE /api/v1/settings/default-session-model
  3. UI：设置页面"默认模型"配置区

全局总结模型配置（与会话-模型绑定无依赖关系，可独立安排）：
  1. AppSettingStore：已在上一步实现
  2. API：GET/PUT/DELETE /api/v1/settings/summary-model
  3. UI：设置页面"总结模型"配置区
```
