# Laffybot 开发效率提升计划

> 撰写日期：2026-05-14 · 状态：✅ 已完成（所有 5 步代码修改 + 文档修订已落地）

---

## 一、动机

后端（3100 行 Python）和前端（3100 行 TypeScript）中存在大量不必要的重复模式和自定义基础设施，本计划用更少的代码实现相同的功能，降低维护成本。

---

## 二、改造项

### 2.1 前端共享 UI 组件 ✅

Button / Input class 字符串在 10+ 文件中重复，Modal 遮罩层 + Escape 监听在 3 个文件中复制。提取 `<Button>`（variant/size）、`<Input>`/`<Textarea>`/`<Select>`（inputSize）、`<Modal>`（Escape 关闭 + 遮罩层 + sizes）、`<Collapsible>` 组件，消除重复。

### 2.2 TanStack Query 替代 session-store + provider-store ✅

两个 store（265 行）手写 async CRUD → 删除。创建 `use-sessions`/`use-providers` hooks（TanStack Query），含 `useInfiniteQuery` / `useMutation`。Zustand 保留给 chat-store（流式客户端状态）+ toast-store + ui-store。

### 2.3 Tool Schema 改用 Pydantic ✅

删除 `schema.py`（221 行自定义 Schema 类）。`base.py` 中 `Tool` 类新增 `_param_model: type[BaseModel]`，`cast_params`/`validate_params` 委托 Pydantic。`@tool_parameters` 接收 Pydantic model，`parameters` property 由 `TypeAdapter.json_schema()` 生成。

### 2.4 错误处理统一 ✅

新建 `laffybot/agent/tools/errors.py`（`ToolError` 领域异常）。`ToolRegistry.execute()` 显式捕获 `ToolError`。`AgentRunner.run_stream()` 区分 `ToolError` vs `Exception`。`app.py` 注册 `ToolError` FastAPI 异常处理器。

### 2.6 遗留问题扫尾 ✅

- HeartbeatManager 接入 SSE（`_stream_session_events()` 使用 `asyncio.wait_for` 15s 超时 ping）
- 暗色模式 CSS class 切换（AppShell useTheme hook，system/light/dark 三种模式）
- Tool 设置页对接真实 API（`GET /api/v1/tools` 端点 + 前端移除 mock）
- `ui/src/types/` 空目录已删除

---

## 三、执行顺序

| 步 | 内容 | 依赖 |
|----|------|------|
| 1 | 前端共享 UI 组件 | — |
| 2 | TanStack Query | — |
| 3 | Tool Schema → Pydantic | — |
| 4 | 错误处理统一 | — |
| 5 | 遗留问题扫尾 | 1~4 任意 |
