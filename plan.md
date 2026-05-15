# 修复自动生成标题后UI无法实时显示的问题

## 问题描述

自动生成会话标题功能可以正常生成标题，但UI无法实时显示，需要刷新页面才能看到新标题。

## 当前状态

**已实现但未提交**：修复代码已在本地实现，但尚未提交到版本库。

当前生产环境使用的是临时方案：前端在消息完成后延迟轮询刷新会话列表（commit `7b29637`）。

## 问题分析

### 根本原因

**SSE 连接在心跳超时后断开**：

全局事件 SSE 端点（`/api/v1/events`）使用心跳机制保持连接。当心跳超时触发时，`asyncio.wait_for()` 的取消操作传播到底层的 async generator，导致订阅者被移除，连接断开。

标题生成是异步后台任务（`asyncio.create_task()`），完成时 SSE 连接已经断开，事件无法送达前端。

### 临时方案的问题

当前生产环境的延迟轮询方案：
- 不依赖 SSE 实时推送
- 在消息完成后 1s 和 3s 各刷新一次会话列表
- 存在延迟和额外请求开销

## 解决方案

### 设计思路

**解耦心跳超时与订阅生命周期**：

将订阅队列的管理与心跳超时处理分离。心跳超时只影响等待操作，不触发订阅清理。订阅在连接显式关闭时才清理。

### 设计要点

1. **直接管理订阅队列**：不使用 `EventBus.subscribe()` 的 async generator，直接创建队列并添加到订阅列表
2. **超时只取消等待操作**：使用 `queue.get()` 配合 `wait_for`，超时只取消 `get()` 操作，不影响订阅状态
3. **显式清理订阅**：在 `finally` 块中手动清理订阅，确保只在连接关闭时清理

## 修改范围

### 后端

| 文件 | 状态 | 说明 |
|------|------|------|
| `laffybot/api/event_bus.py` | 新增 | 全局事件总线 |
| `laffybot/api/routes.py` | 修改 | 添加 `/api/v1/events` 端点 |
| `laffybot/session/manager.py` | 修改 | 标题生成后发布事件 |

### 前端

| 文件 | 状态 | 说明 |
|------|------|------|
| `ui/src/lib/api.ts` | 修改 | 添加 `connectGlobalEvents()` 函数 |
| `ui/src/hooks/use-global-events.ts` | 新增 | SSE 事件处理 hook |
| `ui/src/components/layout/AppShell.tsx` | 修改 | 集成全局事件 hook |
| `ui/src/pages/ChatPage.tsx` | 修改 | 移除延迟轮询临时方案 |

## 验证步骤

1. 启动服务，打开前端页面
2. 确认 `/api/v1/events` SSE 连接建立并保持（检查网络面板）
3. 发送消息触发自动标题生成
4. 观察标题是否实时更新（无需刷新页面）
5. 检查日志确认 SSE 连接持续保持

## 相关文件

- `laffybot/api/event_bus.py` - 全局事件总线
- `laffybot/api/routes.py` - `/api/v1/events` 端点
- `laffybot/session/manager.py` - `_trigger_auto_title()` 方法
- `ui/src/lib/api.ts` - `connectGlobalEvents()` 函数
- `ui/src/hooks/use-global-events.ts` - `useGlobalEvents()` hook
