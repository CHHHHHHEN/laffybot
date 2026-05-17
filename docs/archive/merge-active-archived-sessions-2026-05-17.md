---
archived_from: plan.md
archived_at: 2026-05-17
implements: N/A
status: implemented
summary: |
  Merge active and archived session lists into a unified list in the sidebar,
  removing tab switching and using archived_at field to distinguish session status.
---

# Plan: 合并活跃与已归档会话列表

## Goal

将前端侧边栏中分开显示的「活跃」和「已归档」会话列表合并为一个统一列表，用户无需切换标签即可查看所有会话。

## Acceptance Criteria

1. 侧边栏移除「活跃/已归档」切换标签
2. 所有会话（活跃与已归档）显示在同一个列表中
3. 已归档会话通过视觉样式区分（如图标、透明度、标签）
4. 已归档会话支持「取消归档」和「删除」操作
5. 活跃会话支持「归档」操作
6. 列表按 `updated_at` 降序排列（后端已实现）
7. 归档/取消归档/删除操作失败时通过 Toast 显示错误信息
8. 无会话时显示统一的空状态提示（不再区分活跃/已归档）

## Design

### 架构变更

```
当前架构:
  Sidebar.tsx
    ├── archiveTab 状态 ('active' | 'archived')
    ├── useSessions(archived: boolean)
    ├── 两个标签按钮
    └── 条件渲染活跃/已归档会话

目标架构:
  Sidebar.tsx
    ├── 无 archiveTab 状态
    ├── useSessions() 不传 archived 参数
    └── 统一会话列表（按 archived_at 字段区分样式）
```

### 数据流

```
前端调用 listSessions({}) 
  → 后端返回所有会话（无 archived 过滤）
  → 前端根据 session.archived_at 是否为 null 判断归档状态
  → 渲染时应用不同样式和操作按钮
```

### 组件职责

| 组件 | 职责 |
|------|------|
| `Sidebar.tsx` | 移除标签切换逻辑，统一渲染会话列表 |
| `useSessions` hook | 移除 `archived` 参数，请求所有会话 |
| 后端 `list_sessions` | 已支持 `archived=None` 返回全部，无需修改 |

### 视觉区分设计

- **活跃会话**: 正常样式，hover 显示归档按钮
- **已归档会话**: 
  - 透明度降低（opacity: 0.6）
  - 显示归档图标
  - hover 显示「取消归档」和「删除」按钮

### 会话列表项布局

**问题**: 操作按钮（归档/删除）默认占位，导致标题显示区域被挤占。

**解决方案**: 操作按钮使用 `absolute` 定位，仅在 hover 时显示，不占用文档流空间。

```
会话列表项布局:
┌─────────────────────────────────────┐
│ [图标] 标题文字可占满整行...         │  ← 默认状态，按钮隐藏
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ [图标] 标题文字... [归档] [删除]    │  ← hover 状态，按钮覆盖显示
└─────────────────────────────────────┘
```

**实现要点**:
- 父容器设置 `relative` 定位
- 按钮容器设置 `absolute right-0` 定位
- 按钮容器添加背景渐变遮罩，确保文字可读

### 错误处理

| 场景 | 行为 |
|------|------|
| 归档失败 | Toast 显示错误信息 |
| 取消归档失败 | Toast 显示错误信息 |
| 删除失败 | Toast 显示错误信息 |
| 网络错误 | 保留现有 Toast 机制 |

## Implementation Plan

### Phase 1: 前端数据层修改

1. **修改 `use-sessions.ts`**
   - `useSessions()` 函数移除 `archived` 参数
   - 默认不传递 `archived` 参数，获取全部会话
   - `useCreateSession` 的 `invalidateQueries` 更新为 `['sessions']`（移除 `{ archived: false }`）
   - `useDeleteSession` 的 `invalidateQueries` 更新为 `['sessions']`（移除 `{ archived: true }`）

### Phase 2: 前端 UI 层修改

2. **修改 `Sidebar.tsx`**
   - 移除 `archiveTab` 状态
   - 移除「活跃/已归档」标签按钮
   - 修改 `useSessions()` 调用，不传参数
   - 根据 `session.archived_at` 判断归档状态
   - 统一列表渲染，按归档状态应用不同样式和操作按钮

3. **优化会话列表项布局**
   - 操作按钮改为 `absolute` 定位
   - 按钮容器添加渐变背景遮罩

## Scope Definition

### In Scope
- 前端侧边栏 UI 变更
- `useSessions` hook 参数调整
- 会话列表项操作按钮布局优化

### Out of Scope
- 后端 API 修改（已支持）
- 会话排序逻辑（后端已按 `updated_at` 降序）
- 新增归档/取消归档功能（已存在）
- 移动端响应式适配

### Deprecated
- `Sidebar.tsx` 中的 `ArchiveTab` 类型定义
- `archiveTab` 状态变量
- 标签切换按钮相关 JSX

## References
- `ui/src/components/layout/Sidebar.tsx` - 当前侧边栏实现
- `ui/src/hooks/use-sessions.ts` - 会话数据获取 hook
- `laffybot/api/routes.py:224` - 后端 `list_sessions` 端点

## Implementation Record

### Files Changed

**ui/src/hooks/use-sessions.ts**:
- Removed `archived` parameter from `useSessions()` function
- Changed queryKey from `['sessions', { archived }]` to `['sessions']`
- Updated `useCreateSession` and `useDeleteSession` to invalidate `['sessions']` without archived filter

**ui/src/components/layout/Sidebar.tsx**:
- Removed `ArchiveTab` type definition
- Removed `archiveTab` state variable
- Removed tab switching buttons UI
- Changed `useSessions()` call to not pass any parameters
- Updated session list rendering to use `session.archived_at` to determine archived status
- Changed action buttons container to use absolute positioning with gradient background mask
- Updated empty state message from "没有活跃会话/没有已归档会话" to "没有会话"

### Outstanding Items
None
