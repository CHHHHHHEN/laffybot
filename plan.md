# MCP 接入实现计划

> 撰写日期：2026-05-19
>
> 参考：codex-rs MCP 架构为主线，nanobot/hermes-agent 为辅

---

## 一、设计目标

使 laffybot 能够通过 MCP（Model Context Protocol）协议连接外部工具服务器，将远程工具、资源和提示作为 Agent 的 Tool 使用。

- **零 SDK 依赖**：基于 JSON-RPC 2.0 直接实现协议，不依赖 `mcp` Python SDK
- **三传输层支持**：Stdio（子进程）、SSE（HTTP + Server-Sent Events）、Streamable HTTP
- **UI 可配置**：MCP 服务器配置通过前端 CRUD 管理，支持服务器级开关 + 工具级过滤
- **运行时热加载**：修改配置后即时断开旧连接、基于新配置建立新连接，不重启服务
- **并行启动隔离失败**：所有启用的服务器并行连接，单服务器失败不影响其他
- **按 name 路由**：所有 MCP 工具调用通过 McpServerManager 按服务器名路由

---

## 二、架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ToolRegistry                                 │
│  builtin_tools[]  │  mcp_tools[] (运行时按服务器分组注册)           │
└────────┬────────────────────────────────────────────────────────────┘
         │ register / unregister_group
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      McpServerManager                                │
│  ┌───────────────────────────┐  ┌───────────────────────────┐       │
│  │  AsyncManagedClient       │  │  AsyncManagedClient       │ ...   │
│  │  - config (MCPServerConf) │  │  - config                 │       │
│  │  - client (McpClient)     │  │  - client                 │       │
│  │  - transport              │  │  - transport              │       │
│  │  - tools[] (after filter) │  │  - tools[]                │       │
│  │  - status (state machine) │  │  - status                 │       │
│  │  - cancel_token (child)   │  │  - cancel_token           │       │
│  └───────────────────────────┘  └───────────────────────────┘       │
│                                                                      │
│  - startup_cancel_token (root)                                       │
│  - call_tool(server_name, tool_name, args) → Result                  │
│  - list_all_tools() → aggregated + filtered + deduplicated           │
│  - list_all_resources() → concurrent JoinSet                         │
│  - hot_swap(configs) → atomically replace all clients               │
└──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    JSON-RPC 传输层 (RMCP Transport)                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  TransportRecipe (创建策略) → PendingTransport → ClientState │   │
│  │     Stdio           SSE            StreamableHttp             │   │
│  │  (subprocess)   (HTTP+SSE)       (HTTP POST)                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    SQLiteMcpServerStore                               │
│  mcp_servers 表: id, name, enabled, transport_type,                  │
│                 command/url, args, env(encrypted), headers(encrypted),│
│                 tool_timeout, enabled_tools[], disabled_tools[]       │
└──────────────────────────────────────────────────────────────────────┘
```

**McpServerManager 生命周期**：

```
Manager::new(configs)
  ├─ 创建根 CancellationToken
  ├─ for each enabled server:
  │   └─ 创建 child CancellationToken
  │   └─ 启动后台 task（Transport → initialize → list_tools → filter → register）
  │       └─ 各 task 独立，互不阻塞
  ├─ 返回启动状态收集
  │
  └─ call_tool(server, name, args):
      ├─ 按 server_name 路由到对应的 AsyncManagedClient
      ├─ 双检 filter（启动时 + 调用时）
      ├─ McpClient.call_tool(name, args)
      └─ 返回结果或错误
```

---

## 三、不在本计划范围内

以下功能在本设计中明确排除，不纳入当前实现：

| 功能 | 理由 |
|------|------|
| OAuth 2.1 认证流程 | codex/hermes 已实现但复杂度高，laffybot 暂无需求 |
| Sampling（服务器发起 LLM 请求） | MCP 协议可选功能，需额外的 LLM 调用编排 |
| 自动重连 | 不设计 fallback——断开后标记 failed，由用户手动 reconnect 或下次启动 |
| 动态工具发现（`tools/list_changed` 通知） | 需在 McpClient 中增加 notification 分发机制 |
| 资源订阅（`resources/subscribe`） | MCP 协议可选功能，暂不需要实时资源变更通知 |
| 多进程共享连接 | SQLite 单实例部署，不考虑 MCP 连接跨进程共享 |

---

## 四、组件分解

### 4.1 JSON-RPC 核心 `McpClient` — `laffybot/agent/tools/mcp/client.py`

MCP 协议级别的 JSON-RPC 2.0 会话封装：

| 方法 | JSON-RPC 方法 | 说明 |
|------|---------------|------|
| `initialize()` | `initialize` | 协商协议版本和 capabilities。发送 client 端 capabilities（tools/resources/prompts 等），接收 server 端 capabilities |
| `ping()` | `ping` | 心跳保活 |
| `list_tools()` | `tools/list` | 返回 `list[Tool]` 结构 |
| `call_tool(name, args)` | `tools/call` | 返回 `CallToolResult`（含 `content: list[ContentBlock]` + `isError: bool`） |
| `list_resources()` | `resources/list` | 返回 `list[Resource]` 结构 |
| `read_resource(uri)` | `resources/read` | 返回 `ResourceContents`（text 或 blob） |
| `list_prompts()` | `prompts/list` | 返回 `list[Prompt]` 结构 |
| `get_prompt(name, args)` | `prompts/get` | 返回 `GetPromptResult`（含 `messages: list[PromptMessage]`） |
| `set_logging_level(level)` | `logging/setLevel` | 设置服务器日志级别 |
| `send_request(method, params)` | — | 通用 JSON-RPC 请求发送（底层原语） |
| `close()` | — | 关闭传输层连接 |

**请求 ID**：严格递增整数（`self._request_id += 1`），避免 ID 冲突。

**协议版本**：发送 `protocolVersion: "2025-03-26"`，接收并检查 server 端的兼容版本。

**Capabilities**：

| 方向 | Capabilities |
|------|-------------|
| Client → Server | `roots(listChanged)`, `sampling`（占位） |
| Server → Client | `tools(listChanged)`, `resources(listChanged, subscribe)`, `prompts(listChanged)`, `logging` |

**职责**：协议级通信，不关心传输细节。通过依赖注入接收一个 `Transport` 实例。

### 4.2 传输层 — `laffybot/agent/tools/mcp/transports.py`

所有 Transport 实现同一接口（类似 codex 的 `TransportRecipe` → `PendingTransport` → `ClientState` 两阶段创建模式）：

```python
class Transport(ABC):
    async def connect(self) -> None: ...
    async def send(self, message: str) -> None: ...
    async def receive(self) -> str: ...
    async def close(self) -> None: ...
```

#### 4.2.1 `StdioTransport`

- `asyncio.create_subprocess_exec(command, *args, env=filtered_env)` 启动子进程
- stdin 写入 `\n` 分隔的 JSON 行
- stdout 逐行读取 JSON 行
- stderr 重定向到日志文件（避免污染 TTY），仅在 stdout JSON 解析失败时检查
- **环境变量过滤**（参考 hermes-agent）：仅透传 `PATH/HOME/USER/LANG/LC_ALL/TERM/SHELL/TMPDIR` + 用户显式指定的 env
- **Windows 兼容**：`npx`/`bunx`/`.cmd`/`.bat` 自动包裹 `cmd.exe /d /c`
- **进程清理**：先 SIGTERM，超时后 SIGKILL（`process.wait()` + timeout）

#### 4.2.2 `SseTransport`

MCP SSE 是双向传输：服务器→客户端通过 SSE 事件流，客户端→服务器通过 HTTP POST。

**连接流程**：
1. `httpx` GET 请求连接到 MCP 服务器 SSE 端点（如 `http://host/sse`）
2. 服务器发送 `endpoint` 事件（含 POST URL，如 `http://host/messages?sessionId=abc`）
3. 后续所有客户端→服务器的 JSON-RPC 请求通过 HTTP POST 发送到该 POST URL
4. 服务器→客户端响应通过 SSE 事件流的 `event: jsonrpc` / `data:` 行返回

**SSE 线协议解析**（手动实现，基于 `httpx` 流式响应）：
- 按行读取：`event: <type>\n` 和 `data: <payload>\n`，空行 `\n` 触发事件派发
- 支持的 event 类型：`endpoint`（首次连接）、`jsonrpc`（JSON-RPC 响应）
- 忽略未知事件类型和 SSE 注释行（`:` 开头）
- 如果在收到 `endpoint` 事件前收到 JSON-RPC 事件，说明服务端使用 streamable HTTP

**连接状态**：
- `connected` — SSE 流正常
- `disconnected` — 流中断或连接失败

#### 4.2.3 `StreamableHttpTransport`

- 基于 `httpx`：HTTP POST 到单一端点
- 请求：`Content-Type: application/json`，body 为 JSON-RPC 请求
- 响应：SSE 格式流式读取（`event: jsonrpc` / `data: <JSON-RPC response>` 行）
- 支持自定义 headers

#### 传输错误处理

| 场景 | 行为 |
|------|------|
| 子进程启动失败（命令不存在） | 抛出 `TransportError`，管理任务捕获后标记 server status = Failed |
| 子进程运行时退出 | 关闭连接，标记 status = Failed。不降级——该服务器所有工具从 ToolRegistry 移除 |
| HTTP 连接超时 | 抛出 `TimeoutError` |
| HTTP 连接被拒绝 | 抛出 `TransportError` |
| SSE 流中断 | 关闭连接，标记 status = Failed。不设计自动重连 |
| JSON 解析失败 | 返回 JSON-RPC Error 响应（code -32700 Parse Error） |
| JSON-RPC 响应 ID 与请求 ID 不匹配 | 记录 `error` 日志，丢弃该响应，等待匹配的响应或超时 |
| SSE 流中收到非 JSON 事件 | 记录 `warning` 日志，忽略该事件 |
| Stdio 进程 stderr 有输出 | 记录到日志；仅当 stdout 解析失败时检查 stderr 并给出提示 |

### 4.3 工具包装 — `laffybot/agent/tools/mcp/wrappers.py`

三个包装类，均继承 `Tool` 并设置 `kind = "mcp"`：

| 类 | 包装目标 | 对应 JSON-RPC 方法 | read_only | 注册条件 |
|---|---|---|---|---|
| `McpToolCall` | 远程 MCP Tool | `call_tool` | 从 `readOnlyHint`/`destructiveHint` 推断 | server 声明 `tools` capability |
| `McpResourceTool` | 远程 MCP Resource | `read_resource` | true | server 声明 `resources` capability |
| `McpPromptTool` | 远程 MCP Prompt | `get_prompt` | true | server 声明 `prompts` capability |

每个包装类持有所属 `AsyncManagedClient` 的引用，通过 client 路由到正确的 `McpClient` 并获取当前 `ToolFilter`（调用时双检）。

**CallToolResult 内容处理**：MCP 工具返回的 `content` 是 `list[ContentBlock]`。转换为 laffybot Tool 结果字符串的规则：
- `TextContent` → 直接拼接 text 字段
- `ImageContent` → 插入 `[Image: {mimeType}, {data[:64]}...]` 占位符
- `EmbeddedResource` → 插入 `[Resource: {uri}]` 占位符
- 所有块后续以换行连接；若 `isError = True`，结果字符串前缀 `Error: `

**名称规范化**：`{server_name}_{tool_name}`

- 使用正则 `[^a-zA-Z0-9_-] → _` 替换
- 多个连续下划线 `_+` → 单个 `_`
- 前缀和名称之间始终用 `_` 分隔

**JSON Schema 转换**（参考 codex `parse_tool_input_schema` + hermes-agent `_normalize_schema_for_openai`）：

| 转换 | 说明 |
|------|------|
| `missing "properties"` | inputSchema 缺少 `properties` 时，插入 `{"type": "object", "properties": {}}` |
| `nullable union` | `["string", "null"]` → `{"type": "string", "nullable": true}` |
| `nullable anyOf/oneOf` | `{"oneOf": [..., {"type": "null"}]}` → 提取非 null 分支 |

### 4.4 服务器客户端 `AsyncManagedClient` — `laffybot/agent/tools/mcp/manager.py`

单服务器的生命周期管理器（参考 codex `ManagedClient` + `AsyncManagedClient`）：

```python
class AsyncManagedClient:
    server_name: str
    config: MCPServerConfig
    client: McpClient | None
    transport: Transport | None
    tools: list[ToolInfo]          # 过滤后的工具列表
    tool_filter: ToolFilter        # 启动时 + 调用时双检
    status: ServerStatus           # 状态机
    cancel_token: CancellationToken
    started_at: datetime | None
```

**状态机**：

```
[created]
    │
    ▼
[starting] ──(success)──→ [ready]
    │                          │
    ├──(fail)──→ [failed]      ├── disable/disconnect → [disconnected]
    │                          │
    └── cancel  → [disconnected]  └── hot_swap → [disconnected]
```

**工具过滤**（`ToolFilter`，参考 codex `ToolFilter::allows()`）：

当 plan 中提及"工具"时，统一涵盖 MCP Tool、MCP Resource、MCP Prompt 三类，除非特别指明仅限 Tool。

- 启动时应用 `enabled_tools`（allow-list `["*"]` = 全部）和 `disabled_tools`（deny-list）
- 调用时双检：`ToolFilter.allows(name)` 确保调用时刻仍被允许
- 资源/Prompt 的调用时双检与 Tool 相同：通过统一的 `ToolFilter.allows()` 方法

**启用/禁用粒度**：目前基于服务器级 `enabled_tools`/`disabled_tools`，工具名称含类型前缀（`{server}_{tool}`、`{server}_resource_{resource}`、`{server}_prompt_{prompt}`），用户可分别控制 Tool/Resource/Prompt 的启用与禁用。

### 4.5 服务器管理器 `McpServerManager` — `laffybot/agent/tools/mcp/manager.py`

核心管理器（参考 codex `McpConnectionManager`）：

| 方法 | 说明 |
|------|------|
| `__init__(configs)` | 只读初始化，不连接 |
| `start()` | 并行启动所有启用的服务器。每个服务器创建独立 task 运行 `_start_one()`；所有 task 通过 `asyncio.gather(return_exceptions=True)` 并行执行 |
| `shutdown()` | 取消根 CancellationToken，等待所有子 task 退出，关闭所有 transport |
| `call_tool(server_name, tool_name, arguments)` | 按服务器名路由到对应的 `AsyncManagedClient.client.call_tool()`；调用前双检 filter；调用后双检 `isError` 返回 |
| `list_all_tools()` | 聚合所有 ready 服务器的工具列表，按服务器名分组排序 |
| `list_all_resources()` | 使用 `asyncio.gather` 并发获取所有 ready 服务器的资源列表 |
| `list_all_prompts()` | 同上，并发获取 prompt 列表 |
| `get_status(server_name)` | 返回指定服务器的状态 |
| `get_all_status()` | 返回所有服务器的状态快照 |
| `hot_swap(configs)` | 原子替换：创建新的 `McpServerManager`，启动后替换引用，关闭旧的 |

**并行启动**：

```
McpServerManager.start()
  ├─ 创建根 CancellationToken
  ├─ tasks = []
  ├─ for each server where config.enabled:
  │     tasks.append(_start_one(server_name, config, root_token.child()))
  ├─ results = await asyncio.gather(*tasks, return_exceptions=True)
  └─ 收集每个 task 的启动结果（成功/失败 + 原因）
```

**单服务器启动流程 `_start_one()`**：

```
1. status = starting
2. try:
3.   transport = create_transport(config)
4.   await asyncio.wait_for(transport.connect(), timeout=config.startup_timeout)
5.   client = McpClient(transport)
6.   await asyncio.wait_for(client.initialize(), timeout=config.startup_timeout)
7.   raw_tools = await asyncio.wait_for(client.list_tools(), timeout=config.startup_timeout)
8.   filtered = tool_filter.apply(raw_tools)
9.   resources = await client.list_resources() if capability (lazy: only eager if startup_timeout allows)
10.  prompts = await client.list_prompts() if capability (lazy: only eager if startup_timeout allows)
11.  wrap all filtered tools/resources/prompts as Tool
12.  register to ToolRegistry
13.  status = ready
14. except (asyncio.TimeoutError, Exception) as e:
15.  status = failed, error = str(e)
16.  close transport if opened
```

**Hot-swap 流程**（参考 codex `refresh_mcp_servers_inner`，修正了时序窗口）：

```
1. 创建新管理器 = McpServerManager(new_configs)
2. 新管理器.start() 并 await 全部启动完成（或超时 config.startup_timeout * 2，确保单服务器超时后全局仍有合理等待）
3. 收集旧配置中存在、新配置中不存在的服务器名 → stale_names
4. 新管理器将所有已发现的工具注册到 ToolRegistry
5. 对 stale_names 中的每个服务器：ToolRegistry.unregister_group(prefix)
6. 原子替换：old = self._active_manager; self._active_manager = new
7. old.shutdown()（旧工具已被覆盖或移除，不影响已注册的工具）
```

这样确保：切换过程中 ToolRegistry 始终有有效的 MCP 工具（旧配置的工具保留到新配置的工具就绪为止）。

**取消机制**：当前 `CancellationToken`（`laffybot/agent/cancellation.py`）不支持父子层级。改用 `asyncio.Task` 管理取消：

```
Manager:
  ├─ _tasks: set[asyncio.Task]    # 所有后台启动 task
  ├─ _server_tasks: dict[str, asyncio.Task]  # server_name → startup task
  │
  ├─ shutdown() → 取消 _tasks 中所有 task → gather(wait them)
  ├─ disable_server(name) → 取消 _server_tasks[name]
  └─ hot_swap() → 旧 Manager 的 shutdown() 取消其所有 task
```

每个启动 task 内使用传递给 transport 和 client 的 `CancellationToken` 实例进行协作式取消检查（在 `transport.connect()`、`client.initialize()`、`client.list_tools()` 等阻塞操作前调用 `token.check()`）。task 级别取消通过 `asyncio.Task.cancel()` 传播 `CancelledError`。

### 4.6 MCP 配置存储 — `laffybot/session/mcp_server_store.py`

遵循 `ProviderStore` 模式（参考 codex `McpServerConfig` 的字段设计）：

| 组件 | 说明 |
|------|------|
| 抽象接口 | `McpServerStore(ABC)` — 定义 CRUD 方法 |
| SQLite 实现 | `SQLiteMcpServerStore` — `mcp_servers` 表 |
| 敏感字段 | `env` 和 `headers` 字段加密存储（复用 `laffybot.crypto`） |
| 传输类型 | 自动检测（参考 codex untagged enum + hermes-agent 检测逻辑）：有 `command` → stdio；有 `url` 且以 `/sse` 结尾 → SSE；有 `url` → streamableHttp |

`mcp_servers` 表字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| server_id | TEXT PK | UUID |
| name | TEXT UNIQUE | 用户自定义名称，用作 tool name 前缀 |
| enabled | INTEGER | 全局开关：1=启用（连接并注册工具），0=禁用 |
| transport_type | TEXT | stdio / sse / streamableHttp（可空，自动检测） |
| command | TEXT | stdio：可执行命令 |
| args | TEXT(JSON) | stdio：命令行参数列表 |
| env | TEXT(JSON, encrypted) | stdio：额外环境变量 KV 对 |
| url | TEXT | SSE/HTTP：端点 URL |
| headers | TEXT(JSON, encrypted) | SSE/HTTP：自定义请求头 KV 对 |
| tool_timeout | INTEGER | 单次工具调用超时秒数（默认 30；注意全局 `tool_timeout_s` 在 SessionManager 中默认 120，MCP 超时应小于或等于该值以确保被上层捕获） |
| enabled_tools | TEXT(JSON) | 工具 allow-list（默认 `["*"]` = 全部允许） |
| disabled_tools | TEXT(JSON) | 工具 deny-list（默认 `[]` = 全部不禁用） |
| startup_timeout | INTEGER | 连接超时秒数（默认 30） |
| created_at / updated_at | TEXT | ISO 8601 时间戳 |

### 4.7 MCP API 路由及 Schemas

**Pydantic 请求/响应模型** — `laffybot/api/schemas.py`（遵循 `ProviderCreateRequest`/`ProviderResponse` 模式）：

| Schema | 字段 |
|--------|------|
| `MCPServerCreateRequest` | name, transport_type (自动检测时可空), command, args, url, env, headers, tool_timeout, enabled_tools, disabled_tools, startup_timeout |
| `MCPServerUpdateRequest` | 同上，所有字段可选 |
| `MCPServerResponse` | id, name, transport_type, command, url, has_env, has_headers, tool_timeout, enabled_tools, disabled_tools, startup_timeout, enabled, connection_status (ready/starting/failed/disconnected), tool_count, created_at |
| `MCPServerTestResponse` | success, message（含义同 `TestResultResponse`） |

**API 路由** — `laffybot/api/mcp_routes.py`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/mcp/servers` | 列出所有 MCP 服务器配置（含 enabled、connection_status） |
| POST | `/api/v1/mcp/servers` | 创建 MCP 服务器配置（enabled 默认为 false，不自动连接） |
| GET | `/api/v1/mcp/servers/{id}` | 获取服务器详情 |
| PUT | `/api/v1/mcp/servers/{id}` | 更新服务器配置（env/headers 可选。若启用中则触发 hot_swap） |
| DELETE | `/api/v1/mcp/servers/{id}` | 删除服务器配置（如已启用则触发 hot_swap 移除该服务器，再删除数据库记录） |
| POST | `/api/v1/mcp/servers/{id}/enable` | 启用服务器（连接 + 初始化 + 过滤 + 注册工具） |
| POST | `/api/v1/mcp/servers/{id}/disable` | 禁用服务器（取消注册工具 + 断开连接 + 清理进程） |
| POST | `/api/v1/mcp/servers/{id}/toggle` | 切换启用/禁用状态 |
| POST | `/api/v1/mcp/servers/{id}/test` | 连通性测试（连接 + initialize + 列出工具，不注册到 ToolRegistry） |
| POST | `/api/v1/mcp/servers/{id}/reconnect` | 重新连接服务器（先断开再连接） |

**PUT 时的 hot_swap 触发**：
```
PUT /mcp/servers/{id} 收到
  → 更新数据库
  → 如果该服务器当前是 enabled 且连接中:
      → 收集所有 enabled 服务器配置
      → McpServerManager.hot_swap(all_configs)
      → 旧连接断开，新连接使用新配置
```

### 4.8 前端 MCP 设置页面 — `ui/src/pages/McpSettingsPage.tsx`

遵循 `ProviderSettingsPage` 的 CRUD 模式：

| 组件 | 职责 |
|------|------|
| `McpSettingsPage` | 主页面：服务器列表 + CRUD 操作入口 |
| `McpServerForm` | 创建/编辑对话框（传输类型、命令/URL、参数、环境变量、请求头） |
| `McpServerCard` | 单服务器卡片：**启停开关**、名称、传输类型、URL/命令、连接状态指示（ready/starting/failed）、工具数 |
| `McpToolFilterForm` | 工具级过滤设置对话框（可选，可用 `enabled_tools`/`disabled_tools` JSON 编辑器或列表选择） |
| `use-mcp-servers.ts` | TanStack Query hooks（list/create/update/delete/test/toggle/enable/disable） |

**McpServerCard 交互**：
```
┌──────────────────────────────────────────────────────┐
│  [🔘 开关]  📡 filesystem          状态: ● ready    │
│  ─ stdio: npx -y @modelcontextprotocol/...          │
│  工具: 5 / 5 enabled  超时: 30s                     │
│  [测试] [编辑] [删除]                                │
└──────────────────────────────────────────────────────┘
```

**SettingsPage 标签**：追加 `{ to: '/settings/mcp', label: 'MCP 服务' }`

### 4.9 应用生命周期集成

#### 启动连接

采用 codex 的**并行后台启动**模式：

```
app startup (lifespan startup)
  → 从 SQLiteMcpServerStore 读取所有 enabled = True 的配置
  → McpServerManager(configs)
  → manager.start()  // 并行后台，不 await
  → app.state.mcp_manager = manager
```

连接在后台进行，不阻塞应用启动。`list_all_tools()` 自动忽略尚未 ready 的服务器。

#### 运行时热加载

```
用户通过 UI 修改/创建/删除 MCP 服务器配置
  → API 更新数据库
  → API 调用 McpServerManager.hot_swap(全部配置)
    → 新管理器启动并等待就绪
    → 注册新工具，移除过时工具
    → 原子替换 app.state.mcp_manager
    → 旧管理器 shutdown
```

#### 关闭清理

```
app shutdown (lifespan shutdown)
  → app.state.mcp_manager.shutdown()
    → 取消所有 server 启动 task
    → await task 退出
    → close all transports
  → ToolRegistry 清除所有 mcp 工具
```

---

## 五、集成点

### 5.1 ToolRegistry 集成

`ToolRegistry` 已有 `kind = "mcp"` 排序逻辑，MCP 工具自动排在 builtin 之后。新增：

- `unregister_group(prefix: str)` — 按服务器名前缀批量移除工具（hot_swap/disable 时使用）

### 5.2 AgentRunner 集成

`AgentRunner.run_stream()` 通过 `spec.tools.execute(name, params)` 调用工具。MCP 工具的 `execute()` 内部通过 `AsyncManagedClient` 路由调用，对 AgentRunner 完全透明。

### 5.3 SessionManager 集成

`SessionManager` 不直接感知 MCP。MCP 工具注册到 `ToolRegistry` 后自动对 AgentRunner 可见。

### 5.4 API 路由集成

在 `laffybot/api/routes.py` 的 `router.include_router()` 中追加 `mcp_router`。

### 5.5 依赖注入集成

在 `laffybot/api/dependencies.py` 中新增：
- `build_mcp_server_store(config)` → `SQLiteMcpServerStore`
- `get_mcp_server_store(request)` → FastAPI Depends

`McpServerManager` 由 `create_app()` 直接初始化并挂载到 `app.state`（全局单例，与 `SessionManager` 同级）。

---

## 六、错误处理

| 场景 | 行为 |
|------|------|
| 服务器启动失败（配置无效、命令不存在、URL 不可达） | 记录警告，status = failed（含失败原因），不影响其他服务器 |
| initialize 失败（协议版本不兼容） | 记录错误，status = failed |
| 并行启动中一个服务器失败 | `asyncio.gather(return_exceptions=True)` 确保其他服务器不受影响 |
| 启动成功后运行时断开 | 工具调用返回 `Error: MCP server '{name}' disconnected` |
| 工具调用超时（超出 tool_timeout） | `asyncio.wait_for` 超时 → 返回 `Error: Tool '{name}' timed out after {timeout}s` |
| 工具调用返回 JSON-RPC error | 返回 `Error: {error_message}`，消息中剥离凭据模式（参考 hermes-agent `_sanitize_error`） |
| 工具调用被 `CancelledError` 中断 | 重新抛出，由 AgentRunner 处理 |
| 调用时工具不在 active list 中（双检不通过） | 返回 `Error: Tool '{name}' is disabled on server '{server}'` |
| 删除或修改连接中的服务器配置 | 通过 `hot_swap` 流程：创建新管理器 → 原子替换 → 旧管理器 shutdown |
| 禁用服务器时存在 in-flight 工具调用 | 工具调用在 transport.close() 时因底层连接断开而失败，结果由 AgentRunner 的 `try/except` 捕获，返回 `Error`；旧管理器 shutdown 不等待 in-flight 调用完成 |
| 数据库不可用（McpServerStore 初始化失败） | 记录 error 日志，McpServerManager 以空配置启动（不连接任何服务器），所有 MCP 相关 API 返回空列表或错误状态 |
| Agent 并发调用同一服务器工具 | `McpClient` 内部串行化 JSON-RPC 请求（请求-ID 严格配对，McpClient 实例内部用一个 asyncio.Lock 串行化所有请求——这不是性能取舍而是协议要求：JSON-RPC 请求-响应通过 ID 配对，若无串行化则无法确定哪个响应对应哪个请求。长耗时请求（如 `call_tool`）会阻塞同一连接上的 `ping` |
| 服务器名重复（配置冲突） | `name` 字段 UNIQUE 约束，后创建的拒绝。API 层捕获 `IntegrityError` 并返回 409 和 `MCP_SERVER_NAME_CONFLICT` error code |
| 工具名冲突（跨服务器） | 前缀天然避免冲突；若仍有冲突，后注册覆盖先注册的 |
| 调用一个不存在的服务器 | 返回 `Error: MCP server '{name}' not found` |

---

## 七、边缘情况

- **JSON-RPC 请求 ID 单调递增**：从 1 开始递增，不会重复
- **Stdio 进程 stderr 污染**：stderr 重定向到日志，仅在 stdout JSON 解析失败时输出提示
- **SSE 连接中断**：不自动重连，标记 status = failed
- **工具名称长度限制**：部分模型的 tool name 有长度限制；前缀 + 名称总长度超过 64 字符时截断尾部
- **inputSchema 缺失 "properties"**：自动插入空 `properties: {}`（参考 codex `parse_mcp_tool`）
- **nullable JSON Schema**：`["string", "null"]` → `type: string + nullable: true`
- **无工具服务器**：连接成功但工具列表为空（或全部被 filter 过滤），status = ready，不注册任何工具
- **Hot-swap 中的竞争**：旧管理器 shutdown 前可能有正在执行的工具调用——这些调用会正常完成或超时，不会影响新管理器
- **环境变量泄露**：stdio 子进程仅接受白名单环境变量 + 用户显式指定的 env；headers 中的敏感值加密存储

---

## 八、实现顺序

1. **JSON-RPC 核心 + McpClient** → `laffybot/agent/tools/mcp/client.py`
   - JSON-RPC 2.0 请求/响应结构
   - initialize / ping / list_tools / call_tool / close
   - 可独立测试（mock transport）

2. **三个 Transport** → `laffybot/agent/tools/mcp/transports.py`
   - StdioTransport（子进程、环境变量过滤、stderr 重定向、Windows 兼容）
   - SseTransport（httpx + SSE 事件流）
   - StreamableHttpTransport（httpx + POST + 流式响应）

3. **工具包装类** → `laffybot/agent/tools/mcp/wrappers.py`
   - ToolFilter（allow-list + deny-list）
   - McpToolCall / McpResourceTool / McpPromptTool
   - JSON Schema 规范化（nullable / missing properties）

4. **Server Manager** → `laffybot/agent/tools/mcp/manager.py`
   - AsyncManagedClient（状态机、生命周期）
   - McpServerManager（并行启动、路由、hot_swap、取消令牌树）

5. **配置存储** → `laffybot/session/mcp_server_store.py`
   - Abstract + SQLite 实现 + 加密存储

6. **生命周期集成** → 修改 `laffybot/api/app.py` + `laffybot/api/dependencies.py`
   - lifespan startup/shutdown
   - app.state 挂载
   - ToolRegistry.unregister_group 支持

7. **API 路由** → `laffybot/api/mcp_routes.py`
   - 后端 CRUD + toggle/enable/disable/test/reconnect 端点

8. **前端页面** → `ui/src/`
   - `ui/src/lib/api.ts` — 类型定义 + API 调用函数
   - `ui/src/hooks/use-mcp-servers.ts` — TanStack Query hooks
   - `ui/src/pages/McpSettingsPage.tsx` — 设置页面
   - `ui/src/components/settings/McpServerForm.tsx` — 表单对话框
   - 路由注册到 `SettingsPage.tsx`

---

## 九、交付检查清单

**Stdio 传输**：
- [ ] `asyncio.create_subprocess_exec` 启动子进程成功
- [ ] stdin 写入 JSON 行 / stdout 读取 JSON 行正常通信
- [ ] 环境变量过滤：只透传白名单变量 + 用户显式指定变量
- [ ] stderr 重定向到日志文件，不污染 TTY
- [ ] Windows 兼容：`npx`/`.cmd` 自动包裹 `cmd.exe /d /c`
- [ ] 进程清理：SIGTERM → 超时 → SIGKILL

**SSE 传输**：
- [ ] HTTP GET + SSE 事件流接收（`event:` / `data:` 行解析）
- [ ] 从 `endpoint` 事件发现 POST URL
- [ ] 客户端→服务器 HTTP POST 通信正常
- [ ] 支持自定义 headers

**Streamable HTTP 传输**：
- [ ] HTTP POST + SSE 格式流式响应读取

**McpClient**：
- [ ] `initialize()` 协商协议版本和 capabilities
- [ ] `ping()` 心跳保活
- [ ] `list_tools()` / `call_tool()` 正常通信
- [ ] `close()` 关闭传输层
- [ ] 请求 ID 严格递增不冲突
- [ ] JSON-RPC 响应 ID 校验（丢弃 ID 不匹配的响应）
- [ ] 并发工具调用通过 asyncio.Lock 串行化，保证请求-响应配对正确

**Tool 包装**：
- [ ] McpToolCall / McpResourceTool / McpPromptTool 均设 `kind = "mcp"`
- [ ] CallToolResult 内容处理：TextContent 拼接，Image/Resource 占位符
- [ ] `isError = True` 时结果前缀 `Error: `

**JSON Schema 规范化**：
- [ ] 缺失 `properties` 时自动插入空 `{}`
- [ ] `["string", "null"]` → `type: string + nullable: true`
- [ ] `oneOf`/`anyOf` 中提取非 null 分支

**名称规范化**：
- [ ] `[^a-zA-Z0-9_-] → _` 替换
- [ ] 连续下划线合并
- [ ] 总长度超过 64 字符时截断

**ToolFilter**：
- [ ] 启动时应用 allow-list + deny-list
- [ ] 调用时双检过滤
- [ ] 资源/Prompt 同样受 filter 控制

**AsyncManagedClient 状态机**：
- [ ] created → starting → ready | failed → disconnected
- [ ] 失败时记录原因

**McpServerManager**：
- [ ] 并行启动：`asyncio.gather(return_exceptions=True)` 隔离失败
- [ ] `call_tool()` 按服务器名路由
- [ ] `call_tool()` 对不存在的服务器名返回 `Error: MCP server '{name}' not found`
- [ ] `list_all_tools()` / `list_all_resources()` 聚合
- [ ] `hot_swap()` 原子替换，无工具窗口期（create-before-destroy：新管理器就绪后才关闭旧管理器）
- [ ] `hot_swap()` 中的 in-flight 调用不受旧管理器 shutdown 影响（调用已完成或超时）
- [ ] `shutdown()` 取消所有 task 并清理
- [ ] 启动超时：`startup_timeout` 在 connect/initialize/list_tools 阶段生效

**配置存储**：
- [ ] SQLite CRUD（mcp_servers 表）
- [ ] env / headers 字段加密存储（复用 `laffybot.crypto`——函数名虽含 `api_key` 但 Fernet 加密是通用的）
- [ ] 传输类型自动检测（command/url 推断，`/sse` 后缀启发式）
- [ ] `name` 字段 UNIQUE 约束确保服务器名不重复

**后端 API**：
- [ ] CRUD：GET/POST/PUT/DELETE `/api/v1/mcp/servers[/{id}]`
- [ ] enable/disable/toggle 端点
- [ ] test 端点（连接 + 列出，不注册）
- [ ] reconnect 端点

**前端页面**：
- [ ] 服务器列表（名称、传输类型、URL/命令、状态、工具数）
- [ ] 创建/编辑表单（传输类型、命令/URL、参数、环境变量、请求头）
- [ ] 启停开关（per-server toggle）
- [ ] 状态指示（ready/starting/failed）

**生命周期**：
- [ ] 启动时后台并行连接 enabled 服务器
- [ ] hot_swap 热加载不阻塞 API
- [ ] shutdown 时清理所有连接

**隔离失败**：
- [ ] 单服务器启动失败不影响其他服务器
- [ ] 失败服务器工具不注册

**ToolRegistry 扩展**：
- [ ] `unregister_group(prefix)` 正确移除指定前缀的所有工具
- [ ] `get_definitions()` 正确返回 builtins + MCP 工具

**透明集成**：
- [ ] AgentRunner 无需修改即可使用 MCP 工具

---

## 十、参考文件

- `third-party/codex/codex-rs/codex-mcp/src/` — **主要参考**：McpConnectionManager、rmcp_client、工具过滤、取消令牌树、hot_swap
- `third-party/codex/codex-rs/config/src/mcp_types.rs` — McpServerConfig 字段设计（enabled/enabled_tools/disabled_tools/tool_timeout/startup_timeout/transport）
- `third-party/codex/codex-rs/tools/src/mcp_tool.rs` — tool schema 规范化（missing properties）
- `third-party/nanobot/nanobot/agent/tools/mcp.py` — JSON-RPC 传输逻辑、名称规范化、nullable schema 处理
- `third-party/hermes-agent/tools/mcp_tool.py` — 环境变量过滤、凭据剥离、stderr 重定向
- `docs/provider-model-design.md` — Provider 配置 CRUD 模式（MCP 配置存储的参照）
- `laffybot/agent/tools/base.py` — Tool 基类（`kind: "mcp"` 已预留）
- `laffybot/agent/tools/registry.py` — ToolRegistry（MCP 排序逻辑已存在）
- `laffybot/session/provider_store.py` — 配置存储模式参照（加密字段、JSON 序列化）
- `laffybot/api/provider_routes.py` — CRUD 路由模式参照
- `laffybot/crypto.py` — 加密工具（复用，注意函数名 `encrypt_api_key`/`decrypt_api_key` 含 `api_key` 但底层 Fernet 加密是通用的，可用于 env/headers 字段）

## Existing Technical Debt

Pre-existing issues in the codebase outside this plan's scope. Recorded for awareness.

| Category | Location | Description |
|----------|----------|-------------|
| Structure | `laffybot/api/tool_routes.py:24` | 直接访问 `registry._tools` 私有属性而非使用公共 API（如 `tool_names` 属性或新增公开方法） |
| Reliability | `laffybot/session/provider_store.py:329-333` | `get_provider_config()` 在已有 `ProviderRow` 后又重新查询 DB 取加密 API key，额外一次 DB 往返 |
| Maintainability | `laffybot/session/app_setting_store.py` | 226 行内含 10+ 组模式完全相同的 get/set/delete 方法对，大量复制粘贴冗余 |
