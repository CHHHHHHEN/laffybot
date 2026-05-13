# Laffybot - Inspried by nanobot

# Laffybot 项目整体结构报告

> 撰写日期：2026-05-13

---

## 一、项目概览

Laffybot 是一个基于 FastAPI 的 AI 对话代理系统，后端提供 REST + SSE API，前端为 React SPA。整体采用"后端 Python (FastAPI) + 前端 TypeScript (React/Vite)"的全栈架构，数据持久化使用 SQLite，LLM 调用兼容 OpenAI API 格式。

**版本**: 0.1.0 · **Python**: >=3.13 · **Node**: Vite 8 + React 19

---

## 二、目录结构

```
laffybot/
├── AGENTS.md                    # 本文件 + 项目环境规则
├── README.md                    # 项目简介
├── pyproject.toml               # Python 依赖 & 工具配置
├── config.example.json          # 提供商配置示例
├── config.json                  # 本地提供商配置（已 gitignore）
├── laffybot.db / .db-shm / .db-wal  # SQLite 数据库文件
│
├── laffybot/                    # Python 后端核心包
│   ├── __init__.py              # 版本号
│   ├── __main__.py              # CLI 入口: uvicorn 启动
│   ├── config.py                # Pydantic 配置模型
│   │
│   ├── api/                     # HTTP API 层
│   │   ├── app.py               # FastAPI 应用工厂 + lifespan
│   │   ├── routes.py            # 所有 API 路由定义
│   │   ├── schemas.py           # 请求/响应 Pydantic Schema
│   │   ├── dependencies.py      # 依赖注入（factory, store 构建）
│   │   └── errors.py            # 领域异常 → HTTP 响应映射
│   │
│   ├── agent/                   # Agent 执行层
│   │   ├── runner.py            # AgentRunner: LLM 循环 + 流式事件
│   │   ├── events.py            # SSE 事件类型 & 工厂函数
│   │   ├── cancellation.py      # CancellationToken 取消机制
│   │   ├── heartbeat.py         # HeartbeatManager 心跳保活
│   │   └── tools/               # 工具系统
│   │       ├── base.py          # Tool/Schema 抽象基类 + @tool_parameters
│   │       └── registry.py      # ToolRegistry 注册/执行
│   │
│   ├── providers/               # LLM 提供商抽象层
│   │   ├── base.py              # BaseProvider 抽象接口
│   │   ├── openai.py            # OpenAIProvider 实现（流式 + 非流式）
│   │   └── types.py             # LLMResponse, StreamChunk, ToolCallRequest
│   │
│   ├── session/                 # 会话管理层
│   │   ├── manager.py           # SessionManager: 状态协调 + 请求调度
│   │   ├── store.py             # SessionStore 接口 + SQLiteStore 实现
│   │   ├── models.py            # 领域模型 (SessionInfo, SessionStatus)
│   │   └── errors.py            # 领域异常 (SessionNotFound, SessionBusy...)
│   │
│   └── context/                 # 上下文构建层
│       ├── base.py              # ContextBuilder / TokenCounter 抽象接口
│       ├── builder.py           # SimpleContextBuilder 实现
│       ├── tokens.py            # ApproximateTokenCounter + UsageBasedTokenCounter
│       ├── templates.py         # SystemPromptTemplate (Jinja2)
│       └── types.py             # 上下文类型（重导出 ContextConfig）
│
├── tests/                       # Python 测试
│   ├── __init__.py
│   ├── context/
│   │   └── __init__.py
│   └── api/
│       └── __pycache__/         # 仅缓存，无源码
│
├── ui/                          # 前端 SPA
│   ├── index.html               # HTML 入口
│   ├── package.json             # 依赖声明
│   ├── vite.config.ts           # Vite 构建配置
│   ├── tsconfig*.json           # TypeScript 配置
│   ├── eslint.config.js         # ESLint 配置
│   └── src/
│       ├── main.tsx             # React 入口
│       ├── App.tsx              # 路由定义 (react-router-dom)
│       ├── index.css            # 全局样式 + Tailwind 主题变量
│       │
│       ├── lib/                 # 工具层
│       │   ├── api.ts           # HTTP 客户端 (fetch 封装 + SSE 解析)
│       │   ├── sse.ts           # SSE 类型重导出
│       │   └── utils.ts         # cn() classnames 工具
│       │
│       ├── stores/              # Zustand 状态管理
│       │   ├── chat-store.ts    # 消息流 + SSE 连接状态 + streamBuffer
│       │   ├── session-store.ts # 会话列表 CRUD + 分页
│       │   └── ui-store.ts      # 侧边栏 + 主题偏好
│       │
│       ├── pages/               # 页面级组件
│       │   ├── ChatPage.tsx      # 聊天主页（SSE 事件分发）
│       │   ├── SettingsPage.tsx  # 设置面板容器（二级导航）
│       │   ├── ProviderSettingsPage.tsx  # 提供商配置（mock 数据）
│       │   └── ToolSettingsPage.tsx      # 工具管理（本地 toggle）
│       │
│       ├── components/
│       │   ├── chat/            # 聊天相关组件
│       │   │   ├── ChatHeader.tsx
│       │   │   ├── InputBar.tsx
│       │   │   ├── MessageList.tsx
│       │   │   ├── MessageBubble.tsx
│       │   │   ├── StreamMessage.tsx     # Markdown 渲染 + 流式光标
│       │   │   ├── ReasoningBlock.tsx    # 推理过程折叠
│       │   │   ├── ToolCallCard.tsx      # 工具调用进行中
│       │   │   ├── ToolResultBlock.tsx   # 工具执行结果
│       │   │   ├── ScrollToBottomButton.tsx
│       │   │   └── SessionStatusBadge.tsx
│       │   │
│       │   ├── layout/          # 布局组件
│       │   │   ├── AppShell.tsx  # 整体骨架 (Sidebar + Outlet)
│       │   │   ├── Sidebar.tsx   # 侧边栏（导航 + 会话列表内联）
│       │   │   └── NavLinks.tsx  # 导航链接
│       │   │
│       │   └── ui/              # 通用 UI 组件
│       │       ├── NewSessionDialog.tsx
│       │       ├── ConfirmDialog.tsx
│       │       ├── ErrorBoundary.tsx
│       │       ├── Toast.tsx     # Toast 通知（Zustand store + 渲染）
│       │       └── ConnectionStatusBanner.tsx
│       │
│       ├── hooks/
│       │   └── useKeyboardShortcuts.ts   # Ctrl+B 切换侧边栏
│       │
│       └── types/               # (空目录，类型定义内联在 lib/api.ts)
│
└── docs/                        # 技术文档（中文）
    ├── readme-document-content-guidelines.md  # 文档撰写规范
    ├── api.md                   # API 端点 & SSE 事件规范
    ├── agent-runner-streaming-design.md       # AgentRunner 流式架构
    ├── context-builder-design.md              # ContextBuilder 架构
    ├── heartbeat-design.md                    # 心跳机制设计
    ├── session-manager-design.md              # SessionManager 架构
    ├── session-manager-sqlite-impl.md         # SQLite 存储实现设计
    └── ui/
        ├── ui-api-interface.md               # UI-API 接口契约
        ├── ui-design-spec.md                 # 视觉设计规范
        ├── ui-design.md                      # 交互 & 组件设计
        └── ui-tech-selection.md              # 技术选型依据
```

---

## 三、后端架构（Python）

### 3.1 分层架构

```
┌──────────────────────────────────────────────────┐
│              HTTP API 层 (laffybot/api)            │
│  FastAPI 路由 → 参数校验 → 错误映射 → SSE 流式响应    │
├──────────────────────────────────────────────────┤
│            会话管理层 (laffybot/session)            │
│  SessionManager: 状态机 + 并发锁 + 事件转发          │
│  │  SQLiteStore: 数据库 CRUD + 乐观锁 + WAL 模式    │
├──────────────────────────────────────────────────┤
│           Agent 执行层 (laffybot/agent)             │
│  AgentRunner: LLM 循环 + 工具调用 + SSE 事件流      │
│  │  ToolRegistry: 工具注册/参数校验/执行             │
├──────────────────────────────────────────────────┤
│           LLM 提供商层 (laffybot/providers)         │
│  OpenAIProvider: OpenAI/DeepSeek/OpenRouter 兼容   │
├──────────────────────────────────────────────────┤
│         上下文构建层 (laffybot/context)              │
│  SimpleContextBuilder: 系统提示 + 历史 + 容量控制    │
└──────────────────────────────────────────────────┘
```

### 3.2 核心数据流

```
用户请求
  │
  ▼
SessionManager.send_message()
  ├─ 获取会话锁 (asyncio.Lock)
  ├─ 检查状态 (idle → busy)
  ├─ 保存用户消息 (SQLiteStore.save_message)
  ├─ 构建上下文 (ContextBuilder.build_messages)
  │   ├─ 渲染系统提示 (Jinja2 模板 / 静态提示)
  │   ├─ 加载历史消息 (SQLiteStore.get_messages)
  │   ├─ 添加当前消息
  │   └─ 容量控制 (max_tokens / max_messages 截断)
  ├─ 创建 AgentRunner + Provider
  ├─ 流式执行 (AgentRunner.run_stream)
  │   ├─ LLM 请求 (OpenAIProvider.chat_completion_stream)
  │   ├─ SSE 事件产出 (session_start → content/reasoning → tool_call/tool_result → done)
  │   └─ 工具执行 (ToolRegistry.execute)
  ├─ 转发 SSE 事件 (yield event)
  ├─ done 时保存助手消息 (SQLiteStore.save_message)
  └─ 更新状态 (busy → idle/error)
```

### 3.3 会话状态机

```
idle ──(发送消息)──→ busy ──(完成)──→ idle
                      │
                      ├──(错误)──→ error ──(重试)──→ idle
                      │
                      └──(取消)──→ idle
```

- **并发控制**: 每个会话独立 `asyncio.Lock`，同一会话串行
- **乐观锁**: `update_session_status` 支持 `expected_status` 参数，数据库 WHERE 条件检查
- **CancellationToken**: 请求级别取消标志，在迭代/LLM/工具执行前 check()

### 3.4 SSE 事件类型

| 事件 | 触发时机 | 关键字段 |
|------|----------|----------|
| `session_start` | 流开始 | session_id, request_id |
| `content` | LLM 文本片段 | text |
| `reasoning` | 推理过程片段 | text |
| `tool_call` | 工具调用 | tool_call_id, name, arguments |
| `tool_result` | 工具完成 | tool_call_id, name, result, success, duration_ms |
| `done` | 流结束 | stop_reason, usage, tools_used |
| `error` | 异常 | error: {code, message, details} |
| `cancelled` | 取消 | reason |
| `ping` | 心跳 | timestamp |

事件顺序: `session_start → (content|reasoning)* → [tool_call→tool_result]+ → done`

### 3.5 会话信息模型

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | str | UUID 主键 |
| model | str | LLM 模型标识 |
| status | idle/busy/error | 会话状态 |
| created_at / updated_at | datetime | 时间戳 |
| message_count | int | 消息数（冗余字段） |
| current_request_id | str\|None | 当前请求 ID |
| error_message | str\|None | 错误信息 |
| system_prompt | str\|None | 会话级别系统提示 |
| max_iterations | int | Agent 最大迭代次数（默认 10） |

### 3.6 SQLite 存储设计

- **WAL 模式**: `PRAGMA journal_mode=WAL` 提升并发
- **外键约束**: `PRAGMA foreign_keys=ON`，级联删除
- **自动迁移**: `_run_migrations()` 运行时检查并添加缺失列
- **乐观锁更新**: UPDATE + WHERE status = expected_status
- **两张表**: `sessions`（元数据） + `messages`（消息正文，含 JSON metadata + token 字段）
- **aiosqlite**: 异步 SQLite 驱动，与 FastAPI 异步架构一致

### 3.7 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/sessions` | 创建会话 |
| GET | `/api/v1/sessions` | 列会话（支持 status/limit/offset） |
| GET | `/api/v1/sessions/{id}` | 获取会话详情 |
| POST | `/api/v1/sessions/{id}/messages` | 发送消息（SSE 流式响应） |
| POST | `/api/v1/sessions/{id}/cancel` | 取消请求 |
| DELETE | `/api/v1/sessions/{id}` | 删除会话（级联消息） |
| GET | `/api/v1/sessions/{id}/history` | 获取消息历史 |
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/ready` | 就绪检查（含数据库检测） |

### 3.8 配置项

| 配置 | 来源 | 说明 |
|------|------|------|
| api_key / base_url | config.json / 环境变量 | LLM 提供商 |
| extra_headers / extra_body | config.json | 额外 HTTP 头/请求体 |
| host / port | 环境变量 | HTTP 绑定（默认 0.0.0.0:8000） |
| cors_origins | 环境变量 | CORS（默认 *） |
| database_path | 环境变量 | SQLite 路径（默认 laffybot.db） |
| max_tokens / max_messages | ContextConfig | 上下文容量控制 |
| system_prompt / system_prompt_template | ContextConfig | 系统提示 / Jinja2 模板 |
| LAFFYBOT_STREAM_IDLE_TIMEOUT_S | 环境变量 | 流空闲超时（默认 90s） |
| LAFFYBOT_HEARTBEAT_INTERVAL_S | 环境变量 | 心跳间隔（默认 15s） |
| LAFFYBOT_OPENAI_COMPAT_TIMEOUT_S | 环境变量 | OpenAI 请求超时（默认 120s） |

---

## 四、前端架构（TypeScript/React）

### 4.1 技术栈

- **框架**: React 19 + TypeScript 6
- **构建**: Vite 8 + Tailwind CSS 4
- **路由**: React Router 7（嵌套路由 + layout route）
- **状态**: Zustand 5（三个独立 store）
- **SSE**: 基于 `fetch` + `ReadableStream` 手动解析
- **图标**: lucide-react
- **Markdown**: react-markdown + remark-gfm + rehype-highlight
- **PWA**: vite-plugin-pwa

### 4.2 Store 职责

| Store | 关键状态 | 职责 |
|-------|----------|------|
| `chat-store` | messages[], isStreaming, streamBuffer, connectionStatus, activeRequestId | 消息流 + SSE 事件处理 + 流缓冲区 |
| `session-store` | sessions[], activeSessionId, isLoading, error | 会话列表 CRUD + 分页加载 |
| `provider-store` | providers[], models{}, activeSelection, isLoading | 提供商/模型 CRUD + 全局选中管理 |
| `ui-store` | sidebarOpen, theme | 侧边栏折叠 + 主题切换 |

### 4.3 流式渲染机制

SSE 流使用两层缓冲区机制：
1. **streamBuffer** 在流期间累积 text/reasoning/toolCalls
2. 流结束后 `flushStreamBuffer()` 将缓冲区**原地更新**到最后一条 `isStreaming=true` 的 assistant 消息上（不追加新消息）
3. 流期间仅显示闪烁光标

### 4.4 路由规划

```
/chat                         → 重定向到 /chat
/chat/:sessionId              → 指定会话聊天
/settings                     → 重定向到 /settings/provider
/settings/provider            → 提供商配置（CRUD，对接真实 API）
/settings/tools               → 工具管理（本地 toggle）
```

### 4.5 UI 组件树

```
AppShell
├── ErrorBoundary
├── ToastContainer
├── Sidebar
│   ├── NavLinks (聊天 / 设置)
│   ├── GlobalModelSelector
│   ├── NewSessionDialog (只读展示全局选中)
│   ├── ConfirmDialog
│   └── 会话列表（内联）
└── Outlet
    ├── ChatPage
    │   ├── ChatHeader
    │   ├── ConnectionStatusBanner
    │   ├── MessageList → MessageBubble → StreamMessage
    │   │   ├── ReasoningBlock
    │   │   ├── ToolCallCard / ToolResultBlock
    │   │   └── react-markdown 渲染
    │   ├── InputBar
    │   └── ScrollToBottomButton
    └── SettingsPage
        ├── ProviderSettingsPage（对接真实 API）
        │   ├── ProviderForm
        │   └── ModelList
        └── ToolSettingsPage（toggle）
```

---

## 五、关键设计决策

### 5.1 架构方面

1. **单实例部署**: 不考虑水平扩展，SQLite 足够
2. **SessionManager 单例 + AgentRunner 按需创建**: 会话协调全局共享，执行器轻量按请求创建
3. **ContextBuilder 依赖注入**: 支持不同的上下文构建策略
4. **ProviderStore 运行时配置**: 提供商配置存储在数据库，API Key 加密保存，运行时实时读取和解密
5. **会话与提供商解耦**: model 字段作为创建快照，运行时模型由全局选中决定
6. **乐观锁 + asyncio.Lock 双重保护**: 应用层锁 + 数据库乐观锁

### 5.2 功能方面

1. **无 tiktoken 依赖**: Token 计数使用近似估算（CJK: 2 字符/token, 拉丁: 4 字符/token），优先使用 LLM 返回的 exact usage
2. **工具参数校验**: 使用 JSON Schema 片段 + `@tool_parameters` 装饰器
3. **工具 ID 规范化**: 统一为 9 字符 alphanumeric（SHA1 截断或随机生成）
4. **POST-based SSE**: 不使用 `EventSource`，而是 `fetch` + `ReadableStream`，支持 `AbortController` 取消
5. **多提供商管理**: 通过 UI 配置多个 LLM 提供商及模型，API Key 加密存储
6. **OpenAI 兼容**: 支持 OpenAI / DeepSeek / OpenRouter / 本地模型

### 5.3 前端方面

1. **无 openapi-typescript**: 类型定义手写（后端 API 稳定，维护成本低）
2. **无 TanStack Query**: Zustand + fetch 更轻量（核心是 SSE 推送而非请求缓存）
3. **无 shadcn/ui**: 虽然有选型文档提到，但实际未使用（组件均手写）
4. **无 Tauri**: 桌面端规划中，未实现
5. **主题切换待接入**: CSS 变量已定义但 `.dark` class 切换逻辑未接入

---

## 七、已知问题/待办项

1. ❌ 测试用例完全缺失
2. ⚠️ 心跳 `HeartbeatManager` 已实现但未接入 SSE 主流程
3. ⚠️ 暗色模式 `.dark` CSS class 切换未接入
4. ⚠️ 前端未实现响应式 tablet/mobile 断点区分
5. ⚠️ 工具管理页面仍使用 mock 数据，后端工具 toggle API 未实现
6. ⚠️ 前端 `types/` 目录未使用（空）——类型定义在 `lib/api.ts` 中

---

## 八、项目配置文件速查

```toml
# pyproject.toml 关键配置
dev-dependencies: pytest, pytest-asyncio, pytest-cov, ruff, mypy
ruff: select E/F/I/N/W, ignore E501
mypy: strict true, python_version 3.13
pytest: asyncio_mode=auto
```
