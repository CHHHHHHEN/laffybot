---
archived_from: plan.md
archived_at: 2026-05-16
implements: docs/archive/memory-extraction-timing-fix-2026-05-16.md
status: implemented
summary: |
  实现归档前端 UI（标签页过滤、归档/取消归档按钮）、自动归档策略（max_active_sessions）、取消归档端点。
---

# Plan: Archive UI + Auto-Archive + Unarchive

## Goal

实现 [memory-extraction-timing-fix-2026-05-16](./docs/archive/memory-extraction-timing-fix-2026-05-16.md) 中列为 Outstanding items 的三个功能：

1. **前端 UI 改动** — Session 列表区分归档/未归档、归档/取消归档操作按钮
2. **自动归档策略** — 活跃 Session 超过 N 个时自动归档最旧的
3. **取消归档（Unarchive）** — 恢复已归档 Session 到正常状态

后端归档基础（`POST /sessions/{id}/archive`、`GET /sessions?archived=`、`archived_at` 字段、`SessionAlreadyArchivedError`）已在 Phase 1 中实现。

## Acceptance Criteria

- **前端 UI**
  - 侧边栏会话列表顶部有"活跃" / "已归档" 两个过滤标签页
  - 已归档会话有视觉区分（归档图标 + 降低不透明度）
  - 非归档会话：hover 时显示归档按钮（Archive 图标），而非删除按钮
  - 已归档会话：hover 时显示取消归档按钮（Restore 图标）+ 删除按钮
  - 聊天页 Header 中：归档状态显示归档图标，非归档显示归档按钮；已归档显示取消归档按钮
  - `GET /sessions?archived=false`（默认）只显示未归档会话

- **自动归档策略（Max Active Sessions）**
  - 新增配置 `max_active_sessions: int = Field(default=3, ge=1)`，控制活跃 Session 数量上限（`ge=1` 防止误设为 0 导致新会话立即归档）
  - 每次创建新 Session 后，检查非归档 Session 总数；若超过上限，自动归档最旧的 N 个（仅保留最近 N 个活跃）
  - 自动归档触发 `_trigger_extract()` 记忆提取
  - 已归档 Session 的"删除"操作执行实际硬删除（调用 `DELETE /sessions/{id}`）
  - 后端 `DELETE /sessions/{id}` 行为保持不变（仅用于已归档会话的硬删除）

- **归档**
  - 归档忙碌的 Session → 等待流式输出完成后自动归档（不再返回 `SessionBusyError`）

- **取消归档**
  - `POST /sessions/{id}/unarchive` 将 `archived_at` 设为 NULL
  - 取消归档已归档的 Session 成功 → 返回更新后的 SessionInfo
  - 取消归档未归档的 Session → 返回 `SessionNotArchivedError`（HTTP 409 `SESSION_NOT_ARCHIVED`）
  - 取消归档忙碌的 Session → 返回 `SessionBusyError`（复用既有逻辑）

## Implementation Record

### Core files changed

**Backend:**

| File | Change |
|------|--------|
| `laffybot/config.py` | `ApiConfig` 增加 `max_active_sessions: int = 3` |
| `laffybot/session/errors.py` | 新增 `SessionNotArchivedError` |
| `laffybot/session/store.py` | `SessionStore` 抽象类 + `SQLiteStore` 新增 `unarchive_session()`；`list_sessions` 增加 `order_by_asc` 参数 |
| `laffybot/session/manager.py` | `archive_session()` 使用 Lock 等待 busy；新增 `unarchive_session()`、`_auto_archive_excess_sessions()`；`create_session()` 末尾触发自动归档；`__init__` 接受 `max_active_sessions` |
| `laffybot/api/errors.py` | `map_session_error` 增加 `SessionNotArchivedError` → 409 `SESSION_NOT_ARCHIVED` |
| `laffybot/api/routes.py` | 新增 `POST /sessions/{id}/unarchive` 路由 |
| `laffybot/api/dependencies.py` | `build_session_manager` 增加 `max_active_sessions` 参数 |
| `laffybot/api/app.py` | `create_app` 传递 `api_config.max_active_sessions` |

**Frontend:**

| File | Change |
|------|--------|
| `ui/src/lib/api.ts` | `SessionResponse` 增加 `archived_at`；`listSessions` 支持 `archived` 参数；新增 `archiveSession()`、`unarchiveSession()` |
| `ui/src/hooks/use-sessions.ts` | `useSessions()` 接受 `archived` 参数；新增 `useArchiveSession()`、`useUnarchiveSession()` mutations；`useCreateSession`/`useDeleteSession` query key 精细化；`useSessionById` 改用独立 `useQuery` |
| `ui/src/components/layout/Sidebar.tsx` | 顶部"活跃/已归档"标签页；非归档 hover 显示归档按钮；已归档 hover 显示取消归档+删除按钮；降低不透明度+归档图标 |
| `ui/src/components/chat/ChatHeader.tsx` | 非归档显示归档按钮；已归档显示归档标识+取消归档按钮 |

**Design docs referenced:**
- `docs/archive/memory-extraction-timing-fix-2026-05-16.md`

### Outstanding items / known gaps

None.
