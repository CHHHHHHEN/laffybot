# Auto-Title 会话标题自动生成设计

> **文档性质**：设计文档  
> **最后更新**：2026-05-15  
> **实现状态**：已实现  
> **迁移策略**：全量重构，不提供数据库迁移和后向兼容

---

## 概述

当前会话缺少可读性标识，会话列表仅显示 session_id 和 model 信息，用户在侧边栏无法快速定位目标会话。Auto-Title 功能在每次对话完成后自动生成描述性标题，并在用户消息数积累足够后使用完整对话历史重新生成标题，同时支持用户手动编辑。

---

## 设计目标

1. **自动生成**：首次对话完成后异步生成标题，不阻塞 SSE 流
2. **全局重生成**：不采用增量拼凑，用户新增足够消息后使用全部历史重新生成标题
3. **语言跟随**：标题语言自动跟随对话语言
4. **用户可控**：支持用户手动编辑标题，手动编辑结果不被自动生成覆盖
5. **零阻塞**：标题生成完全异步，不影响消息发送和流式响应

---

## 依赖

| 依赖 | 文档 | 说明 | 状态 |
|------|------|------|------|
| 会话-模型绑定 | `session-model-decoupling.md` | `SessionInfo` 需持有 `provider_id` + `model_name` | ✅ 已实现 |
| 全局总结专用模型 | `session-model-decoupling.md` | 可选配置，指定标题生成使用的轻量模型 | ✅ 已实现 |

**当前代码状况**：
- `SessionInfo` 已包含 `provider_id` 和 `model_name` 字段
- `AppSettingStore` 已提供 `get_summary_model()` 和 `set_summary_model()` 方法
- `SessionManager.send_message()` 已有 `done` 事件处理点，可集成标题生成触发逻辑

---

## 数据模型变更

### SessionInfo 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | str \| None | 会话标题，未生成时为 NULL |
| `user_message_count` | int | 用户消息计数（仅统计 role="user" 的消息） |
| `title_updated_at_user_message_count` | int | 上次更新标题时的用户消息数 |
| `title_auto_generated` | bool | 标记当前标题是否为自动生成 |

### 字段约束

- `user_message_count` 初始为 0，仅统计用户消息
- `title_updated_at_user_message_count` 初始为 0
- `title_auto_generated` 初始为 `False`
- 自动生成成功后 `title_auto_generated = True`
- 用户手动编辑后 `title_auto_generated = False`

### 数据库变更

sessions 表新增以下列（全量重构，无迁移）：

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `title` | TEXT | NULL | 会话标题 |
| `user_message_count` | INTEGER | NOT NULL DEFAULT 0 | 用户消息计数 |
| `title_updated_at_user_message_count` | INTEGER | NOT NULL DEFAULT 0 | 上次标题更新时的用户消息数 |
| `title_auto_generated` | INTEGER | NOT NULL DEFAULT 0 | 标题是否为自动生成（0=False, 1=True） |

**迁移策略**：删除现有数据库文件，使用新 schema 重建。不提供存量数据迁移。

---

## 标题生成策略

### 触发时机

| 时机 | 触发条件 | 上下文 |
|------|----------|--------|
| 首次生成 | SSE `done` 事件，title 为 NULL | 第一条 user msg + 第一条有 content 的 assistant msg |
| 重生成 | SSE `done` 事件，title 已存在，`user_message_count - title_updated_at_user_message_count >= 5` | 全部历史消息（用户 + 助手） |

### 为何不采用增量更新

增量更新使用最近 2-3 轮对话刷新标题，容易丢失原始话题——新标题会片面对焦尾部的讨论内容。采用全量历史重生成确保标题始终覆盖会话全貌，且实现更简单（无需拼接上下文）。

### 生成模型选择

优先使用全局配置的总结专用模型（`AppSettingStore.get_summary_model()`）；未配置时截取第一条 user message 前 50 字符作为标题，不做 LLM 调用。

### 首次生成的特殊处理

Agent 首条响应可能仅为 tool_call（无自然语言 content），此时跳过首次生成，等待下一条 `done` 事件。检测方式：检查累积的 `assistant_chunks` 是否为空——为空说明本条 assistant 消息仅有 tool_call 而无 content。

### 无总结模型时的行为

| 场景 | 行为 |
|------|------|
| 首次生成，无总结模型 | 截取首条 user message 前 50 字符写入 title |
| 重生成触发，无总结模型 | 直接跳过（截取结果不会因重生成而改变，无意义） |

### 手动编辑保护

用户手动编辑后 `title_auto_generated = False`，后续自动生成跳过该会话。

### 错误处理策略

- LLM 调用失败：静默忽略，不抛出异常，下次触发时重试
- 所有失败场景标题保持原值（NULL 或旧值）
- 不阻塞主消息流

---

## 并发安全

标题生成通过 `asyncio.create_task` 异步执行，在 session lock 外运行，可能与其他 task 竞态。

### 乐观锁写入策略

使用精确匹配旧值的 WHERE 条件，而非 `<` 比较，避免两个并发 task 都通过条件：

- 匹配 `title_updated_at_user_message_count` 旧值
- 匹配 `title_auto_generated = True`（确保手动编辑不被覆盖）
- 若 WHERE 不匹配（0 rows affected），表示已被其他 task 或用户手动更新，当前 task 静默放弃

### 竞态场景处理

长时间运行的标题生成 task 读到的是旧 `title_updated_at_user_message_count` 值，写入时被另一个已经完成的 task 拦截——这是正确行为，放弃即可。不应发生由于读取发生在 WHERE 判断之前造成的脏覆盖。

---

## API 变更

### 响应变更

所有返回 SessionInfo 的端点新增 `title` 字段：

| 响应模型 | 变更 |
|----------|------|
| `SessionResponse` | 新增 `title: str \| None` |
| `SessionDetailResponse` | 新增 `title: str \| None`, `title_auto_generated: bool` |
| `SessionListItem` | 新增 `title: str \| None` |

### 新增端点

`PATCH /api/v1/sessions/{session_id}/title`

**请求体**：
```json
{
    "title": "用户自定义标题"
}
```

**响应**：更新后的会话详情（含 title）

**后端处理**：
- 设置 `title = 用户提交值`
- 设置 `title_auto_generated = False`
- 同步更新 `title_updated_at_user_message_count = 当前 user_message_count`（避免下次命中重生成阈值后触发不必要的生成流程）

**约束**：
- 会话不存在返回 404
- 标题为空字符串返回 400
- 标题长度上限 100 字符

---

## 前端交互

### 侧边栏（SessionList）

- 每条会话显示 title，单行文本截断
- title 为 NULL 时显示 `"New Chat"` + model 名（灰色）
- 标题生成中不做额外 loading 状态（不阻塞列表渲染）

### 聊天头部（ChatHeader）

- 显示当前会话 title
- 点击标题进入 inline 编辑模式
- 回车 / 失焦提交编辑 → `PATCH /title`
- 编辑后 `title_auto_generated = False`，不再被自动生成覆盖
- 标题未生成时显示 `"Generating title..."` 占位

---

## 数据流

```
对话完成（done 事件）
  │
  ├─ title 为 NULL? ──→ 检查首条 assistant 是否有 content
  │                          │                │
  │                       有 content      纯 tool_call
  │                          │                │
  │                    异步生成标题         跳过，等下次
  │                          │
  │                   LLM 调用（总结专用模型 / 会话模型）
  │                          │
  │                    成功? ──→ 乐观锁写入
  │                    失败? ──→ 静默忽略
  │
  └─ title 已存在且 title_auto_generated? ──→ user_message_count 增量 >= 5?
                                                     │                      │
                                                     是                    否
                                                     │                      │
                                             有总结模型?                   跳过
                                                   │                 │
                                                 是              否(跳过)
                                                   │
                                             异步重生成标题
                                                   │
                                        LLM 调用（全部历史为上下文）
                                                   │
                                             成功? ──→ 乐观锁写入
                                             失败? ──→ 静默忽略
```

---

## 实现范围约束

### 本版本包含

- SessionInfo 新增 title / user_message_count 相关字段
- 数据库 sessions 表新增对应列（全量重建）
- 全局总结模型配置（通过 `AppSettingStore` 管理）
- TitleGenerator 服务（LLM 非流式调用生成标题）
- SessionManager 集成：done 事件后异步触发，乐观锁写入
- API 序列化新增 title 字段
- PATCH 端点支持手动编辑
- 前端侧边栏显示标题
- 前端 ChatHeader 显示和编辑标题

### 本版本不包含

- 存量会话批量回填标题（title 为 NULL，访问时按需生成）
- SSE 事件推送标题更新（前端通过列表刷新获取）
- 标题生成的队列/限流机制（单实例无并发压力）
- 会话模型切换 UI（provider_id + model_name 仅通过 API 设置）

---

## 待实现组件

### 后端组件

**TitleGenerator 服务**：
- 职责：封装 LLM 非流式调用，生成会话标题
- 输入：消息历史列表、模型配置
- 输出：标题字符串或 None（失败时）
- 错误处理：静默捕获异常，返回 None

**SessionStore 扩展**：
- 新增 `update_session_title()` 方法，实现乐观锁写入逻辑
- 修改 `save_message()` 方法，条件递增 `user_message_count`

**SessionManager 集成**：
- 在 `send_message()` 的 `done` 事件处理中触发标题生成
- 使用 `asyncio.create_task()` 异步执行，不阻塞响应流

### 前端组件

**SessionList 修改**：
- 显示 title 字段，NULL 时显示占位文本
- 单行文本截断样式

**ChatHeader 修改**：
- 显示 title 字段
- 实现 inline 编辑模式（点击进入编辑，回车/失焦提交）
- NULL 时显示生成中占位文本

### API 组件

**新增 schemas**：
- `SessionTitleUpdateRequest`：包含 title 字段

**新增路由**：
- `PATCH /api/v1/sessions/{session_id}/title`：处理手动编辑请求

**修改序列化**：
- `_serialize_session()` 新增 title 字段
- `_serialize_session_detail()` 新增 title 和 title_auto_generated 字段
