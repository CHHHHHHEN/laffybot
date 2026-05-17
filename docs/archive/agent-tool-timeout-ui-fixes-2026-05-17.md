---
archived_from: plan.md
archived_at: 2026-05-17
implements: N/A (multi-issue fix plan)
status: implemented
summary: |
  Implemented five fixes: tool execution timeout mechanism, cancel request frontend state sync,
  session delete restriction removal, sidebar collapse layout, and InputBar dropdown horizontal layout.
---

# 计划：Agent 工具执行与前端 UI 问题修复 — 实施记录

## 修改的文件

### Python 后端

| 文件 | 修改内容 |
|------|---------|
| `laffybot/agent/runner.py` | `AgentRunSpec` 新增 `tool_timeout_s` 字段（默认 120）；`run_stream()` 工具执行处添加 `asyncio.wait_for()` 超时包装 |
| `laffybot/session/manager.py` | `SessionManager.__init__` 新增 `tool_timeout_s: int = 120` 参数；`send_message()` 传递 `tool_timeout_s` 到 `AgentRunSpec` |
| `laffybot/api/dependencies.py` | `build_session_manager()` 新增 `tool_timeout_s: int = 120` 参数 |

### 前端 TypeScript

| 文件 | 修改内容 |
|------|---------|
| `ui/src/pages/ChatPage.tsx` | `handleCancel()` 在成功（200）和 409 SESSION_NOT_BUSY 时强制重置前端状态为 idle 并刷新会话列表 |
| `ui/src/components/layout/Sidebar.tsx` | 未归档 Session 显示删除按钮；`deleteTarget` 扩展为 `{ sessionId, isArchived }`；ConfirmDialog 标题动态；折叠模式适配（NavLinks collapsed prop、新建按钮仅图标、隐藏会话列表） |
| `ui/src/components/layout/NavLinks.tsx` | 新增 `collapsed` prop；折叠时隐藏文字标签 |
| `ui/src/components/chat/InputBar.tsx` | 下拉框容器从 `flex-col` 改为 `flex-col sm:flex-row` |

## 验证

- `uv run ruff check . && uv run ruff format --check . && uv run mypy laffybot/` — 全部通过
- `pnpm run check` (typecheck + lint) — 全部通过

## 已知问题/待办

无。所有五项问题均已按计划实现。

## 实现细节

### 问题一：工具执行超时

- `AgentRunSpec.tool_timeout_s` 默认 120 秒
- 超时返回错误消息 `"Tool '{name}' timed out after {timeout}s"`
- `asyncio.TimeoutError` 被捕获并记录 WARNING 日志，Agent 继续下一轮迭代
- `CancelledError` 保持向上抛出
- 各工具内部超时逻辑保持不变（ExecTool 60 秒继续生效）

### 问题二：取消状态同步

- 取消成功（200）后强制同步前端状态（SSE 连接已提前断开，无法接收 cancelled 事件）
- 409 `SESSION_NOT_BUSY` 时强制重置状态（后端已自动恢复为 idle）

### 问题三：删除限制移除

- 未归档 Session 同时显示「归档」和「删除」按钮
- 删除确认对话框标题根据归档状态动态切换

### 问题四：侧边栏折叠

- 折叠时仅显示图标，隐藏所有文字标签
- NavLinks 接收 `collapsed` prop（通过 props 传递）
- 新建会话按钮折叠时仅显示图标
- 会话列表折叠时隐藏（选项 A）

### 问题五：InputBar 下拉框

- `flex-col` → `flex-col sm:flex-row`（小屏幕保持垂直，sm 及以上横向排列）
