# MCP 断开后工具残留问题修复方案

> 撰写日期：2026-05-20

---

## 1. 设计目标

MCP 服务器因意外断开（进程崩溃、网络故障、SSE 断线）后，ToolRegistry 中该服务器注册的工具应被及时清理，使其不再出现在 LLM 的可用工具列表中。

| 目标 | 说明 |
|------|------|
| 及时性 | 断开后尽最大可能快速清理，不依赖轮询 |
| 完整性 | 覆盖所有断开路径（意外断开、显式关闭、启动失败） |
| 可观测性 | 断开事件可被上层组件（如 EventBus）感知 |
| 最小侵入 | 不改动工具注册/执行核心链路（ToolRegistry、runner、provider） |

---

## 2. 架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                        McpServerManager                          │
│                                                                  │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │  _start_one()       │    │  call_tool()                    │ │
│  │  ├─ 连接 & 初始化    │    │  ├─ 工具调用                    │ │
│  │  ├─ 注册工具         │    │  ├─ 传输层异常 → 清理            │ │
│  │  └─ 设置断开回调 ────┼──┐ │  └─ 返回错误给 LLM              │ │
│  └─────────────────────┘  │ └─────────────────────────────────┘ │
│                           │                                      │
│  ┌─────────────────────┐  │ ┌─────────────────────────────────┐ │
│  │  Transport          │  │ │  shutdown() / _cleanup()        │ │
│  │  ├─ 正常通信         │  │ │  ├─ 关闭传输层                  │ │
│  │  ├─ 断开检测         │  │ │  └─ 清理工具注册                │ │
│  │  └─ 调用 on_disconnect ─┼─┘                                │ │
│  └─────────────────────┘    └─────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   _on_server_       │
                    │   disconnected()    │
                    │                     │
                    │ 统一清理入口:        │
                    │  ├─ 更新 status     │
                    │  ├─ unregister 工具 │
                    │  └─ (可选) 发布事件  │
                    └─────────────────────┘
```

### 控制流

```
断开检测源 → 清理触发 → _on_server_disconnected()
                              │
                              ├─ client.status = disconnected
                              ├─ _unregister_server_tools(name)
                              │       │
                              │       ├─ ToolRegistry.unregister() × N
                              │       │       │
                              │       │       └─ _cached_definitions = None
                              │       │
                              │       └─ ToolRegistry.get_definitions() → 不包含已死工具
                              │
                              └─ (可选) EventBus.publish("mcp_server_disconnected")
```

---

## 3. 组件职责与边界

### 3.1 Transport — 断开检测触发

**现有职责不变**，新增职责：断开时调用 `on_disconnect` 回调。

- StdioTransport：子进程退出（stdout EOF 或 `process.wait()` 完成）时触发
- SseTransport：`_read_sse` 后台任务捕获异常或 SSE 流结束时触发
- StreamableHttpTransport：stream 结束时触发

**不做：** Transport 不负责工具清理、状态更新、事件发布。它仅发出断开信号。

### 3.2 McpServerManager — 断开响应

**新增统一入口 `_on_server_disconnected(server_name)`：**

- 将 `client.status` 设为 `disconnected`
- 调用 `_unregister_server_tools(server_name)` 清理 ToolRegistry
- 取消该服务器的 `_server_tasks` 中对应的 monitor task（如存在）

**三条触发路径调用此入口：**
1. `_start_one` 中设置的 Transport.on_disconnect 回调
2. `call_tool` 中捕获到传输层异常时
3. `shutdown` / `_cleanup_transports` 结尾

### 3.3 ToolRegistry — 无变动

`unregister()` 已正确清除 `_cached_definitions`，无需修改。

### 3.4 EventBus — 可选集成

`_on_server_disconnected` 可发布 `mcp_server_disconnected` 事件，供 UI 或其他组件订阅。此为增量能力，非核心要求。

---

## 4. 集成点

| 集成位置 | 改动类型 | 说明 |
|---------|---------|------|
| `transports.py` — `Transport.__init__` | 新增参数 | 增加 `on_disconnect: AsyncCallable \| None` |
| `transports.py` — 三个 Transport 实现 | 新增调用 | 在各自的断开检测点调用 `self.on_disconnect` |
| `manager.py` — `_start_one()` | 新增逻辑 | 连接成功后设置 `transport.on_disconnect` |
| `manager.py` — `_start_one()` finally | 新增逻辑 | 非 ready 状态但已注册工具时清理 |
| `manager.py` — `call_tool()` | 新增逻辑 | 传输层异常时触发 `_on_server_disconnected` |
| `manager.py` — `shutdown()` | 补充逻辑 | 关闭传输前逐个 `_on_server_disconnected` |
| `manager.py` — `_cleanup_transports()` | 补充逻辑 | 关闭每个传输时调用 `_on_server_disconnected` |
| `manager.py` — 新增 `_on_server_disconnected()` | 新增方法 | 统一清理入口 |
| `api/event_bus.py` | 可选 | 新增事件类型定义（如有 EventBus 集成需求） |

---

## 5. 错误处理

| 场景 | 可观测行为 | 日志 |
|------|-----------|------|
| Transport.on_disconnect 回调内异常 | 吞掉异常，不阻断上层逻辑 | `logger.error("Disconnect callback failed for {server}: {exc}")` |
| _on_server_disconnected 执行时 client 已被移除 | 静默跳过 | `logger.debug("Server {name} already removed, skip cleanup")` |
| call_tool 中异常类型非 TransportError | 仅返回错误文字，不触发清理 | 不变（现有记录） |

**决策点：** call_tool 中应匹配哪些异常类型触发清理？建议仅对代表"连接不可用"的异常（TransportError、ConnectionError 等）触发清理，而非所有 Exception。**待决策：** 是否仅对 TransportError 触发清理，还是对所有 Exception 触发？

---

## 6. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 服务器在工具注册后、status=ready 前失败 | finally 块中清理已注册工具 |
| 同一服务器同时触发多条断开路径（如 call_tool 失败 + 回调同时到达） | _on_server_disconnected 可重入：首次执行后 status 已变、工具已清理，重复调用无副作用 |
| 服务器从未成功连接（status=failed） | 工具从未注册，无需清理 |
| 显式 disable_server 与回调竞争 | disable_server 先执行 → status=disconnected + 工具已清理 → 回调进入时 _on_server_disconnected 检测到非 ready 状态直接跳过 |
| 服务器重启后重新连接 | hot_swap 已处理重新注册逻辑，新连接会重新注册工具 |

---

## 7. 实现顺序

1. **transports.py** — `Transport` 增加 `on_disconnect` 参数，三个实现类在断开点调用
2. **manager.py** — 新增 `_on_server_disconnected()` 方法
3. **manager.py** — `_start_one()` 设置回调 + 失败路径清理
4. **manager.py** — `call_tool()` 异常路径防御性清理
5. **manager.py** — `shutdown()` / `_cleanup_transports()` 补充清理
6. **验证** — 运行 `uv run ruff check .`、`uv run mypy laffybot/` 确保无类型/语法错误

---

## 8. 交付检查清单

- [ ] 三个 Transport 实现均在断开时触发 `on_disconnect`
- [ ] `on_disconnect` 回调异常不会阻断 Manager 主流程
- [ ] 意外断开后 ToolRegistry 中对应服务器的工具被清除
- [ ] `get_definitions()` 缓存失效，不返回已死服务器的工具
- [ ] 显式 `shutdown()` 后工具被清理
- [ ] 服务器启动失败但已部分注册工具时，工具被清理
- [ ] repeated calls to `_on_server_disconnected` 无副作用
- [ ] ruff 语法检查通过
- [ ] mypy 类型检查通过
