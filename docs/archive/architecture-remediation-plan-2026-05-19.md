---
archived_from: plan.md
archived_at: 2026-05-19
implements: docs/ui/ui-tech-selection.md
status: implemented
summary: |
  Architecture remediation plan - Phase 3 (dead code cleanup, test infra) and Phase 4 (frontend dependency migration: clsx+tailwind-merge, sonner, date-fns, radix dialog+collapsible, react-hook-form+zod)
---

# 架构整改计划 — 实施记录

基于 2026-05-17 架构审计结果，完成剩余待办项。

## 实施内容

### Phase 3：清理与基础

#### Item 6 — 死代码清理 ✅

| 代码 | 位置 | 操作 |
|------|------|------|
| `getProvider()` | `ui/src/lib/api.ts` | 删除 |
| `checkHealth()` | `ui/src/lib/api.ts` | 删除 |
| `MemoryStorage` 类 | `laffybot/memory/storage.py` | 删除整个文件 |

#### Item 7 — 测试基础设施 ✅

- **后端**：已有 `tests/` 目录含 6 个测试文件（59 个测试），新增 `tests/context/test_tokens.py`
- **前端**：Vitest 已配置，已有 `chat-store.test.ts`（10 个测试）

### Phase 4：前端基础依赖补齐

#### Item 8 — `cn()` 工具函数升级 ✅
- `ui/src/lib/utils.ts`：改用 `clsx` + `twMerge`
- 迁移 8 个组件使用 `cn()`：Button, Input, Sidebar, NavLinks, MessageBubble, ConnectionStatusBanner, SessionStatusBadge, Collapsible

#### Item 9 — Toast 替换 ✅
- 移除 `ui/src/stores/toast-store.ts` 和 `ui/src/components/ui/Toast.tsx`
- `AppShell.tsx` 改用 `<Toaster position="top-center" />`
- 迁移 47 处 `useToastStore.getState().addToast()` 调用为 `sonner` 的 `toast.success()`/`toast.error()`/`toast.info()`
- 涉及文件：Sidebar, ChatHeader, useSseStream, ProviderSettingsPage, MemoryManagePage, AdvancedSettingsPage

#### Item 10 — 日期格式化 ✅
- `MemoryManagePage.tsx`：`toLocaleString()` → `format(date, 'yyyy-MM-dd HH:mm')`，`toLocaleDateString()` → `format(date, 'yyyy-MM-dd')`

#### Item 11 — Modal 升级 ✅
- `Modal.tsx` 改用 `@radix-ui/react-dialog`（内置 portal、focus trap、escape key、ARIA 属性）
- 保持接口 `{ isOpen, onClose, title, children, size }` 不变

#### Item 12 — ProviderForm 重构 ✅
- `ProviderForm.tsx` 改用 `react-hook-form` + `zod` + `@hookform/resolvers`
- `useFieldArray` 管理 header key/value 对
- 消除 5 个手动 `useState` + `if` 校验样板代码

#### Item 13 — Collapsible 替换 ✅
- `Collapsible.tsx` 改用 `@radix-ui/react-collapsible`（内置 ARIA 属性）

## 核心文件变更

### 后端
- **已删除**: `laffybot/memory/storage.py`
- **新增**: `tests/context/test_tokens.py`

### 前端
- **已删除**: `ui/src/stores/toast-store.ts`, `ui/src/components/ui/Toast.tsx`
- **已修改**:
  - `ui/src/lib/api.ts` (删除 getProvider, checkHealth)
  - `ui/src/lib/utils.ts` (cn() 升级)
  - `ui/src/components/layout/AppShell.tsx` (Toaster 替换)
  - `ui/src/components/layout/Sidebar.tsx` (cn + sonner)
  - `ui/src/components/layout/NavLinks.tsx` (cn)
  - `ui/src/components/chat/ChatHeader.tsx` (sonner)
  - `ui/src/components/chat/MessageBubble.tsx` (cn)
  - `ui/src/components/chat/SessionStatusBadge.tsx` (cn)
  - `ui/src/components/ui/Button.tsx` (cn)
  - `ui/src/components/ui/Input.tsx` (cn)
  - `ui/src/components/ui/Modal.tsx` (radix rewrite)
  - `ui/src/components/ui/Collapsible.tsx` (radix rewrite)
  - `ui/src/components/ui/ConnectionStatusBanner.tsx` (cn)
  - `ui/src/components/settings/ProviderForm.tsx` (react-hook-form + zod rewrite)
  - `ui/src/hooks/useSseStream.ts` (sonner)
  - `ui/src/pages/ProviderSettingsPage.tsx` (sonner)
  - `ui/src/pages/MemoryManagePage.tsx` (date-fns + sonner + cn)
  - `ui/src/pages/AdvancedSettingsPage.tsx` (sonner)
  - `docs/ui/ui-tech-selection.md` (状态同步)

## 设计文档参考

- `docs/ui/ui-tech-selection.md` — Phase 4 依赖补齐的设计依据

## 已知遗留项

- `ProviderRegistry` 尚未实现，计划中提到的路由/限流测试无法覆盖
- `@radix-ui/react-collapsible` 的 Collapsible 组件在代码库中未被引用（预留给 StreamingMessage 使用）
