# Laffybot Bug 排查 & 修改计划

> 撰写日期：2026-05-14 · 状态：📝 计划阶段

---

## Issue 5: 消息流式渲染仍为一次性显示（根因矫正）

### 严重性
🔴 核心体验缺陷

### 背景
Issue 2 之前修复了前端 store 的 buffer 机制，改为每次 chunk 到达时直接 `updateLastMessage` 触发 React 重渲染。但流式渲染仍不生效——消息始终在 LLM 完成全部输出后才一次性显示。

### 根因
`laffybot/agent/runner.py:run_stream()`（约 line 107-123）采用**顺序执行**模式：

```python
# ❌ 当前实现：先等 LLM 流结束，再读队列
response = await self._request_model_stream_with_events(
    spec, messages, event_queue, token
)  # ← 此处 await 会阻塞直到 LLM 全部输出完成
...
# 此时队列里已经积压了全部事件
while True:
    event = await event_queue.get()
    if event is None:
        break
    yield event  # ← 一次性 yield 所有事件
```

`_request_model_stream_with_events` 内部的 `on_chunk` 回调在 LLM 流式输出期间**实时**往 `event_queue` 里放事件，但外层 `await` 使得消费者循环必须等整个流结束后才开始读取。所有事件在队列里积压，一旦开始读取就瞬间全部 yield → 前端 SSE 一次性收到所有 content 事件。

### 目标行为
LLM 每吐一个 token，`on_chunk` 放队列 → 消费者立即取出来 yield → 前端 SSE 逐 token 收到 → React 逐 token 重渲染。

### 修复方案

#### 5a. 并发消费队列

`laffybot/agent/runner.py` `run_stream()`:

将 `_request_model_stream_with_events` 改成后台 Task 运行，消费者在 Task 运行期间实时读队列：

```python
# ✅ 修复后：生产者和消费者并发运行
task = asyncio.create_task(
    self._request_model_stream_with_events(spec, messages, event_queue, token)
)

while True:
    event = await event_queue.get()
    if event is None:   # None 是结束信号
        break
    yield event         # ← 每来一个事件立即 yield

response = await task    # 拿到 LLM 完整响应
```

#### 5b. 确认多轮工具调用不受影响

```
第一轮：
  task1 开始流式 → on_chunk 放 content/reasoning → 消费者实时 yield
  → task1 结束，放 None → 消费者收到 None → break → await task1
  → 检查 response.tool_calls → 有 → 执行工具，yield tool_call/tool_result
  → continue 进入下一轮

第二轮：
  task2 开始流式 → on_chunk 放 content/reasoning → 消费者实时 yield
  → ...
```

#### 5c. 异常安全：防止后台 Task 失败导致消费者死锁

**问题**：`_request_model_stream_with_events` 没有保证 `None` 信号始终发送。如果 `chat_completion_stream` 或 `cancellation_token.check()` 抛出异常，`None` 永远不会放入队列 → 消费者在 `await event_queue.get()` 永久挂起。

**解决**：给 `_request_model_stream_with_events` 加 `try/finally`，确保无论成功/异常/取消，`None` 信号都能到达：

```python
async def _request_model_stream_with_events(self, spec, messages, event_queue, cancellation_token):
    try:
        cancellation_token.check()

        async def on_chunk(chunk: StreamChunk) -> None:
            if chunk.content:
                await event_queue.put(event_content(chunk.content))
            if chunk.reasoning:
                await event_queue.put(event_reasoning(chunk.reasoning))

        response = await self.provider.chat_completion_stream(
            messages=messages,
            model=spec.model,
            on_chunk=on_chunk,
            tools=spec.tools.get_definitions(),
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
        )
        return response
    finally:
        await event_queue.put(None)  # ← 确保消费者不会永久阻塞
```

这样即便后台 Task 内部抛出异常，消费者也能收到 `None` 信号 → 退出循环 → `await task` 重新抛出异常 → 外层 handler 捕获处理。

#### 5d. 防御性清理：外层异常 handler 中 cancel 后台 Task

`run_stream()` 的 `except CancelledError` / `except Exception` 中，如果后台 Task 仍在运行，应显式 cancel 防止泄漏：

```python
try:
    for iteration in range(spec.max_iterations):
        token.check()
        response = await self._request_model_stream_with_events(...)  # 旧：顺序
        ...
except (CancelledError, Exception):
    if "task" in dir() and not task.done():
        task.cancel()
    raise  # 或 yield 对应事件
```

> 注：配合 5c 的 try/finally，5d 不是必须的（消费者不会死锁，异常能正常传播），但作为防御性编程保留。

### 修改文件清单

| 文件 | 改动 |
|------|------|
| `laffybot/agent/runner.py` | `run_stream()` 并发消费 event_queue |
| `laffybot/agent/runner.py` | `_request_model_stream_with_events()` 加 `try/finally` 确保 None 信号 |
| `laffybot/agent/runner.py` | （可选）外层异常 handler 中 cancel 后台 Task |

### 验证
1. 发送消息后立即看到思考/正文内容逐 token 出现
2. 工具调用场景：正文逐 token 渲染 → tool_call 事件 → tool_result 事件 → 第二段正文逐 token 渲染
3. 运行 `pnpm run check` 前端检查 + `uv run ruff check . && uv run mypy laffybot/` 后端检查

---