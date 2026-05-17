---
archived_from: plan.md
archived_at: 2026-05-16
implements: docs/memory-system-impl-roadmap.md
status: implemented
summary: |
  修复记忆提取（Memory Extraction）的时机问题：移除对话中自动提取，改为 Session 归档时触发。
---

# Plan: 记忆提取时机修复

## Goal

修复记忆提取（Memory Extraction）的时机问题。

**当前问题**：每次消息完成后都在 `send_message` 中 fire-and-forget 调用 `_trigger_extract`。这种"对话中自动提取"模式不合理：
- 对话过程中提取的时机过早，内容不完整
- 干扰用户体验（后台 LLM 调用）
- `MemoryManager.extract()` 中有"每 Session 最多一条记忆"的去重检查，导致只有第一次消息触发真正提取

**决策方案**：
1. 移除对话过程中的自动记忆提取（删除 `send_message` 中的 `_trigger_extract` 调用）
2. 引入 Session 归档机制：用户主动归档时触发记忆提取
3. 保留 `extract()` 中的去重检查（每 Session 最多一条记忆），无需 UPSERT
4. 归档后的 Session 仍可继续对话，但不再触发记忆提取（已归档则跳过）

## Acceptance Criteria

- `POST /sessions/{id}/archive` 归档成功 → 设置 `archived_at` 时间戳，触发记忆提取
- 归档已归档的 Session → 返回 `SessionAlreadyArchivedError`
- 归档繁忙的 Session → 返回 `SessionBusyError`（复用既有 `SessionBusyError`）
- 已归档 Session 可继续发消息（不影响对话功能）
- `GET /sessions?archived=true` 只返回已归档列表；`archived=false` 只返回未归档
- 已有未归档 Session 不受影响（`archived_at=NULL`）
- auto-title 不受影响，继续在每次消息完成后触发

## Implementation Record

### Core files changed

**session/models.py**:
- `SessionInfo` 增加 `archived_at: datetime | None = None` 字段

**session/store.py**:
- Schema: sessions 表增加 `archived_at TEXT` 列
- Migration: `ALTER TABLE sessions ADD COLUMN archived_at TEXT`
- `_row_to_session`: 解析 `archived_at` 字段
- `SessionStore` 抽象类：新增 `archive_session()` 抽象方法，`list_sessions` 增加 `archived` 参数
- `SQLiteStore.archive_session()`: 设置 `archived_at` 和 `updated_at` 为当前时间
- `SQLiteStore.list_sessions()`: 支持 `archived=True/False/None` 过滤

**session/errors.py**:
- 新增 `SessionAlreadyArchivedError`

**session/manager.py**:
- 新增 `archive_session()` 方法：校验 busy/已归档 → 设置归档 → 触发记忆提取
- `list_sessions()` 增加 `archived` 参数透传到 store
- 移除 `send_message()` 中的 `_trigger_extract` 调用

**api/schemas.py**:
- `SessionBase` / `SessionDetailResponse` / `SessionListItem` 增加 `archived_at: datetime | None = None`

**api/routes.py**:
- 新增 `POST /sessions/{session_id}/archive` 路由
- `list_sessions` 增加 `archived` 查询参数
- `_serialize_session` / `_serialize_session_detail` 输出 `archived_at`

**api/errors.py**:
- `map_session_error` 增加 `SessionAlreadyArchivedError` → HTTP 409 `SESSION_ALREADY_ARCHIVED`

**docs/memory-system-impl-roadmap.md**:
- 更新提取时机描述：Session 归档时触发，而非消息完成时触发

**docs/api.md**:
- 新增归档描述和状态转换说明
- `GET /sessions/{session_id}` 响应增加 `archived_at` 字段
- `GET /sessions` 增加 `archived` 查询参数
- 新增 `POST /sessions/{session_id}/archive` 端点文档
- 错误码表增加 `SESSION_ALREADY_ARCHIVED`
- 修复重复的 7/8/9 章节编号

**docs/session-manager-design.md**:
- `SessionInfo` 增加 `archived_at` 字段说明
- `SessionStore` 接口增加 `archive_session()` 方法和 `list_sessions` 的 `archived` 参数
- `SessionManager` 接口增加 `archive_session()` 方法和 `list_sessions` 的 `archived` 参数
- 异常类型增加 `SessionAlreadyArchivedError`

**docs/session-manager-sqlite-impl.md**:
- sessions 表 schema 增加 `archived_at` 列
- 实现状态表增加归档行
- 新增 `archive_session()` 实现策略描述
- `list_sessions` 补充归档过滤逻辑
- `updated_at` 更新表增加 `archive_session`

### Outstanding items

~~- 前端 UI 改动（Session 列表区分归档/未归档、归档按钮等）不在本次范围内~~
~~- 自动归档策略（如删除时自动归档而非直接删除）作为后续优化~~
~~- 取消归档（unarchive）不在本次范围内~~

以上三项已在 [archive-ui-autoarchive-unarchive-2026-05-16](archive-ui-autoarchive-unarchive-2026-05-16.md) 中实现。

---
Implementation record: see `docs/archive/archive-ui-autoarchive-unarchive-2026-05-16.md`
