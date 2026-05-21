# Plan: 将 Agent Runtime 从 laffybot 独立为可复用包

> 撰写日期：2026-05-21 · 作者：AI · 状态：草稿

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 关注点分离 | 将 Agent 执行引擎从 Session/API 基础设施中剥离，使引擎可独立测试、复用、演进 |
| 可复用性 | 新包可被其他项目直接依赖，只需提供 Provider + ContextBuilder + ToolRegistry |
| 变革最小化 | laffybot 保持现有功能，仅将 import 目标从 `laffybot.*` 改为新包 |
| 独立发布 | 新包拥有独立版本号，可发布到 PyPI |

### 非目标
- 不改变 laffybot 的 API / Session / Memory / UI / Tauri 代码
- 不引入 DI 框架
- 不重构现有组件内部实现逻辑（仅 relocate）
- 不设计 fallback / retry / recovery 路径

---

## 2. 架构概览

### 2.1 包边界

```
┌─────────────────────────────────────────────────────┐
│  laffybot (修改后)                                    │
│  ├── session/     (SessionManager, store, models)     │
│  ├── api/         (FastAPI routes, event_bus, DI)     │
│  ├── memory/      (导入 runtime 的 tokens/errors)      │
│  ├── config.py    (只有 ApiConfig)                    │
│  ├── crypto.py    (导入 runtime 的 ProviderConfigError)│
│  └── log_config.py, __main__.py                       │
│  DEPENDS ON → laffybot-agent-runtime                  │
└─────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────┐
│  laffybot_agent_runtime (新包, import 路径)           │
│  ├── runner.py        AgentRunner, AgentRunSpec      │
│  ├── cancellation.py  CancellationToken              │
│  ├── events.py        SSEEvent, event_* factories    │
│  ├── heartbeat.py     HeartbeatManager               │
│  ├── title_generator.py  TitleGenerator              │
│  ├── tools/           Tool 基类 + 内置工具             │
│  ├── skills/          SkillsLoader, SkillRegistry     │
│  ├── context/         ContextBuilder + 实现 + 压缩     │
│  ├── providers/       BaseProvider + OpenAIProvider    │
│  └── config.py        ContextConfig (从 laffybot 移入) │
└─────────────────────────────────────────────────────┘
```

### 2.2 数据流（运行时）

```
API Route
  → SessionManager.send_message()            # laffybot
    → ContextBuilder.build_messages()         # runtime
    → ProviderFactory.create_provider()       # runtime
    → AgentRunner.run_stream()               # runtime
      → Provider.chat_completion_stream()    # runtime
      → ToolRegistry.execute()               # runtime
        → Tool.execute()                     # runtime
    → 返回 AsyncGenerator[SSEEvent]           # runtime
  → SessionStore.save_message()              # laffybot
```

SessionManager 作为胶水层：协调锁、状态、存储，但不涉及 agent 循环的实现细节。

---

## 3. 组件分解

### 3.1 移入新包的组件

以下组件按原样从 `laffybot/` 复制到新包，**不改实现逻辑**：

| 原路径 | 新路径 (Python import) | 职责 | 外部依赖 |
|--------|------------------------|------|---------|
| `agent/runner.py` | `laffybot_agent_runtime/runner.py` | Agent 主循环 | loguru |
| `agent/cancellation.py` | `laffybot_agent_runtime/cancellation.py` | 取消令牌 | 无 |
| `agent/events.py` | `laffybot_agent_runtime/events.py` | SSE 事件模型 | 无 |
| `agent/heartbeat.py` | `laffybot_agent_runtime/heartbeat.py` | 心跳保活 | 无 |
| `agent/title_generator.py` | `laffybot_agent_runtime/title_generator.py` | 自动标题 | loguru |
| `agent/tools/base.py` | `laffybot_agent_runtime/tools/base.py` | Tool 抽象基类 | pydantic |
| `agent/tools/errors.py` | `laffybot_agent_runtime/tools/errors.py` | ToolError | 无 |
| `agent/tools/registry.py` | `laffybot_agent_runtime/tools/registry.py` | ToolRegistry | 无 |
| `agent/tools/file_state.py` | `laffybot_agent_runtime/tools/file_state.py` | 文件状态跟踪 | loguru |
| `agent/tools/filesystem.py` | `laffybot_agent_runtime/tools/filesystem.py` | 文件读写工具 | loguru, pydantic |
| `agent/tools/shell.py` | `laffybot_agent_runtime/tools/shell.py` | Shell 执行工具 | loguru, pydantic |
| `agent/tools/skill_view.py` | `laffybot_agent_runtime/tools/skill_view.py` | Skill 查看工具 | pydantic |
| `agent/tools/mcp/*.py` | `laffybot_agent_runtime/tools/mcp/*.py` | MCP 协议工具 | httpx, httpx_sse, loguru |
| `agent/skills/*.py` | `laffybot_agent_runtime/skills/*.py` | Skill 系统 | loguru |
| `context/*.py` | `laffybot_agent_runtime/context/*.py` | 上下文构建 | loguru, jinja2, pydantic |
| `providers/*.py` | `laffybot_agent_runtime/providers/*.py` | LLM 提供商抽象 | loguru, httpx, openai, json-repair |
| `config.py` (ContextConfig 部分) | `laffybot_agent_runtime/config.py` | 上下文配置 | pydantic |

### 3.2 保留在 laffybot 的组件

| 组件 | 保留原因 |
|------|---------|
| `session/manager.py` | Session 生命周期、锁、状态管理、自动标题/记忆触发 |
| `session/store.py` | SQLite 持久化（会话、消息） |
| `session/models.py` | SessionInfo, SessionStatus 等领域类型 |
| `session/errors.py` | SessionError 异常层次 |
| `session/provider_store.py` | 提供商配置持久化（含加密字段） |
| `session/app_setting_store.py` | 全局设置持久化 |
| `session/mcp_server_store.py` | MCP 服务器配置持久化 |
| `session/interfaces.py` | EventPublisher 协议（被 SessionManager 使用） |
| `api/*.py` | FastAPI 路由、Schema、DI、EventBus |
| `memory/*.py` | Memory 管理（依赖 SessionStore） |
| `crypto.py` | API 密钥加密（被 provider_store 使用） |
| `config.py` (ApiConfig 部分) | 环境变量配置（host/port/db_path） |
| `__main__.py`, `log_config.py` | CLI 入口和日志配置 |

### 3.3 需要修改的组件

共 22 处文件需要变更（不含测试）。以下按模块分组：

| 模块 | 文件 | 修改内容 |
|------|------|---------|
| **session** | `laffybot/session/manager.py` | 9 处 import 改为 `laffybot_agent_runtime.*` (agent/runner, cancellation, events, title_generator, tools/registry, context/types, providers/errors, providers/factory) |
| | `laffybot/session/provider_store.py` | 2 处 import 改为 `laffybot_agent_runtime.*` (providers/config, providers/errors) |
| **memory** | `laffybot/memory/extractor.py` | 3 处 import 改为 `laffybot_agent_runtime.*` (context/tokens, providers/types, providers/base) |
| | `laffybot/memory/consolidator.py` | 2 处 import 改为 `laffybot_agent_runtime.*` (providers/types, providers/base) |
| | `laffybot/memory/manager.py` | 2 处 import 改为 `laffybot_agent_runtime.*` (context/tokens, providers/base) |
| **api** | `laffybot/api/session_routes.py` | 4 处 import 改为 `laffybot_agent_runtime.*` (agent/events, agent/heartbeat, agent/skills, providers/errors) |
| | `laffybot/api/app.py` | 8 处 import 改为 `laffybot_agent_runtime.*` (agent/tools/*, providers/errors) |
| | `laffybot/api/dependencies.py` | 7 处 import 改为 `laffybot_agent_runtime.*` (agent/skills, agent/tools/registry, providers/*) |
| | `laffybot/api/errors.py` | 修改 `from laffybot.providers.errors import ...` |
| | `laffybot/api/mcp_routes.py` | import 改为 `laffybot_agent_runtime.tools.mcp.*` |
| | `laffybot/api/skill_routes.py` | import 改为 `laffybot_agent_runtime.skills.*` |
| | `laffybot/api/tool_routes.py` | import 改为 `laffybot_agent_runtime.tools.registry` |
| | `laffybot/api/provider_routes.py` | import 改为 `laffybot_agent_runtime.providers.errors` |
| **crypto** | `laffybot/crypto.py` | import 改为 `laffybot_agent_runtime.providers.errors` |
| **config** | `laffybot/config.py` | 删除 `ContextConfig` 类，只保留 `ApiConfig` |
| **init** | `laffybot/__init__.py` | 保持版本号，无需修改 |
| **删除** | `laffybot/agent/` 整目录 | **删除**——源码移入新包 |
| | `laffybot/context/` 整目录 | **删除**——源码移入新包 |
| | `laffybot/providers/` 整目录 | **删除**——源码移入新包 |
| **pyproject** | `pyproject.toml` | 添加 `laffybot-agent-runtime` 依赖；修改 `packages.find` 排除已删除的目录 |
| **tests** | `tests/agent/` | 移入新包 `tests/` 目录 |
| | `tests/context/` | 移入新包 `tests/` 目录 |
| | `tests/providers/` | 移入新包 `tests/` 目录 |
| | 其他 tests | import 目标改为 `laffybot_agent_runtime.*` |

---

## 4. 集成点

### 4.1 仓库结构（Monorepo）

```
laffybot/
├── pyproject.toml          # laffybot-ai 包（主应用）
├── uv.lock
├── packages/
│   └── laffybot-agent-runtime/
│       ├── pyproject.toml  # laffybot-agent-runtime 包
│       └── src/
│           └── laffybot_agent_runtime/  # Python import 路径
│               ├── __init__.py
│               ├── runner.py
│               ├── cancellation.py
│               ├── events.py
│               ├── heartbeat.py
│               ├── title_generator.py
│               ├── config.py          # ContextConfig
│               ├── tools/
│               ├── skills/
│               ├── context/
│               └── providers/
├── laffybot/               # 主应用源码（修改后）
│   ├── __init__.py
│   ├── config.py           # 仅 ApiConfig
│   ├── session/
│   ├── api/
│   ├── memory/
│   ├── crypto.py
│   └── log_config.py
└── tests/
```

根 `pyproject.toml` 使用 `uv workspace` 声明子包：

```toml
[tool.uv.workspace]
members = ["packages/*"]
```

子包 `packages/laffybot-agent-runtime/pyproject.toml`：

```toml
[project]
name = "laffybot-agent-runtime"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "loguru",
    "pydantic",
    "openai",
    "httpx",
    "httpx_sse",
    "json-repair",
    "jinja2",
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["laffybot_agent_runtime*"]
```

主包 `pyproject.toml` 修改：

```toml
[project]
dependencies = [
    "laffybot-agent-runtime >= 0.1.0",
    ... # 其他现有依赖保持不变
]

[tool.setuptools.packages.find]
include = ["laffybot*"]
# agent/, context/, providers/ 已删除，无需额外 exclude
```

### 4.2 跨包依赖关系

```
laffybot (主应用)
  ├── laffybot_agent_runtime (必需)     — Agent 引擎核心
  ├── aiosqlite                         — 持久化
  ├── fastapi / uvicorn                 — HTTP API
  ├── cryptography                      — API 密钥加密
  └── pydantic / pydantic-settings      — 配置模型
       ↑ 此两项也被 runtime 使用，但作为独立依赖声明

laffybot_agent_runtime (独立包)
  ├── loguru     — 日志
  ├── pydantic   — 工具参数校验 + 配置模型
  ├── openai     — OpenAI SDK（AsyncOpenAI）
  ├── httpx      — MCP 传输层 + OpenAI 备用 HTTP
  ├── httpx_sse  — MCP SSE 传输
  ├── json-repair — LLM JSON 修复
  └── jinja2     — 系统提示词模板
```

**版本策略**：两个包独立遵守语义化版本。runtime 的 API 更稳定（抽象接口），主包的版本随功能发布节奏走。

### 4.3 边界问题与解决方案

| 问题 | 源头 | 方案 |
|------|------|------|
| `SkillRegistry` 依赖 `AppSettingStore` | `agent/skills/registry.py:5` | 在 runtime 中定义 `SkillRegistryStore` Protocol（含 `get_enabled_skills() -> list[str]` 和 `set_enabled_skills(skills) -> None`）；`SkillRegistry` 接收该 Protocol；laftybot 的 `AppSettingStore` 实现该 Protocol（新增适配方法） |
| `crypto.py` 依赖 `ProviderConfigError` | `laffybot/crypto.py:11` | `ProviderConfigError` 随 `providers/errors.py` 移入 runtime；laftybot 的 `crypto.py` 从 `laffybot_agent_runtime.providers.errors` 导入 |
| `memory/` 依赖 `context/tokens` + `providers/types` | `memory/extractor.py:9,11`, `memory/manager.py:10` | 内存模块的导入目标改为 `laffybot_agent_runtime.*`。这是纯 import 路径变更，不改逻辑 |
| `config.py` 需拆分 | `laffybot/config.py` | `ContextConfig` 移入 runtime；`ApiConfig` 保留在主包。laftybot 代码中引用 `ContextConfig` 的地方改为从 runtime 导入 |
| 环境变量 `LAFFYBOT_HEARTBEAT_INTERVAL_S` | `agent/heartbeat.py:17` | 改为 `LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S`。心跳是 runtime 的能力，不应带主应用前缀 |
| `OPENAI_COMPAT_REQUEST_TIMEOUT_S`, `STREAM_IDLE_TIMEOUT_S` | `providers/openai.py` | **保持原名不变**——它们没有 `LAFFYBOT_` 前缀，属于 provider 层面的通用环境变量，不影响包独立性 |

**SkillRegistryStore Protocol 设计**：

```python
# laffybot_agent_runtime/skills/registry.py

from typing import Protocol


class SkillRegistryStore(Protocol):
    """Persistence abstraction for skill enabled-state."""

    async def get_enabled_skills(self) -> list[str]: ...
    async def set_enabled_skills(self, skills: list[str]) -> None: ...
```

laftybot 侧的 `AppSettingStore` 已有 `get_enabled_skills()` 和 `set_enabled_skills()` 方法，签名完全匹配——**零适配代码**。

### 4.4 import 变更总览

所有变更均为以下三类之一：

| 变更类型 | 转换 | 实例 |
|----------|------|------|
| A. 顶层模块 | `laffybot.agent.X` → `laffybot_agent_runtime.X` | `from laffybot.agent.runner import AgentRunner` → `from laffybot_agent_runtime.runner import AgentRunner` |
| B. 子模块 | `laffybot.context.X` → `laffybot_agent_runtime.context.X` | `from laffybot.context.tokens import ...` → `from laffybot_agent_runtime.context.tokens import ...` |
| C. 提供商 | `laffybot.providers.X` → `laffybot_agent_runtime.providers.X` | `from laffybot.providers.errors import ...` → `from laffybot_agent_runtime.providers.errors import ...` |

不存在跨包的语义依赖变更——所有映射都是机械的路径替换。

---

## 5. 错误处理

所有领域异常保持不变，仅 relocate：

| 异常 | 所在包 | 被谁捕获 |
|------|--------|---------|
| `CancelledError` | runtime | SessionManager → 转为 error SSE event |
| `ToolError` | runtime | AgentRunner → 转为 tool_result error event |
| `ProviderError` 及其子类 | runtime | SessionManager + API error mapping |
| `SessionError` 及其子类 | laffybot | API error mapping |
| `SkillError` | runtime | 内部使用，不同步传播 |

---

## 6. 边界情况

### 6.1 代码边界

- **`ToolRegistry._cached_definitions`**：缓存逻辑无外部依赖，直接迁移
- **`FileStates` ContextVar**：ContextVar 的 `__getattr__` fallback 机制保持不表。迁移后，laftybot 的代码通过 `from laffybot_agent_runtime.tools.file_state import current_file_states` 使用
- **`_DEFAULT_OPENROUTER_HEADERS`**：provider 中的 OpenRouter 特定逻辑保留在新包中——它不属于 laffybot 特有，而是 `OpenAIProvider` 的通用优化
- **`TitleGenerator`**：当前被 `SessionManager._trigger_auto_title()` 使用，迁移后 import 路径变更，接口不变。它接收 `BaseProvider`（已在新包），无耦合问题

### 6.2 环境变量

| 当前变量名 | 新变量名 | 说明 |
|-----------|---------|------|
| `LAFFYBOT_HEARTBEAT_INTERVAL_S` | `LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S` | 前缀改为 `LAFFYBOT_AGENT_RUNTIME`，表明属于 runtime 包 |
| `OPENAI_COMPAT_REQUEST_TIMEOUT_S` | **不变** | 无 `LAFFYBOT_` 前缀，通用 OpenAI 兼容层配置 |
| `STREAM_IDLE_TIMEOUT_S` | **不变** | 同上 |

### 6.3 已知不受影响的模块

- **`laffybot/session/interfaces.py`**：`EventPublisher` Protocol 在 session 层定义，被 runtime 的 `SessionManager`（实际是 laffybot 的 `SessionManager`）使用。该 Protocol 在 laffybot 内定义，不被 runtime 引用，不受迁移影响
- **`laffybot/api/event_bus.py`**：是 API 层的事件总线，与 runtime 无关。`SessionManager` 通过 `EventPublisher` Protocol 引用它，不引入跨包依赖
- **`laffybot/memory/`**：import 路径变更但逻辑不变。`MemoryExtractor` 接收 `BaseProvider`（现在从 runtime 导入），`MemoryManager` 使用 `ApproximateTokenCounter`（现在从 runtime 导入）

---

## 7. 生态约束

| 维度 | 决策结果 |
|------|---------|
| **PyPI 包名** | `laffybot-agent-runtime` |
| **Python import 路径** | `laffybot_agent_runtime`（PEP 503 命名转换：`-` → `_`） |
| **仓库结构** | 同仓库 monorepo，路径 `packages/laffybot-agent-runtime/`，使用 `uv workspace` |
| **版本管理** | 两个包独立遵守语义化版本。runtime 以 `0.x` 起步，API 稳定后进入 `1.x`。主包 `laffybot-ai` 保持 `0.1.0` |
| **SkillRegistry 持久化** | runtime 定义 `SkillRegistryStore` Protocol；laftybot 的 `AppSettingStore` 已有匹配签名，零适配 |

<!-- 不在决策范围内：部署、CI/CD、发布频率等工程配置 -->

---

## 8. 实施顺序

依赖关系：`cancellation` → `events` → `heartbeat`, `title_generator`；`tools/base` → `tools/registry` → `tools/filesystem`, `tools/shell`, `tools/mcp`；`providers` ↔ `context`（独立）；`skills`（独立）。所有零依赖模块可以并行迁移。

| 阶段 | 步骤 | 内容 | 产出 | 可验证标准 |
|------|------|------|------|-----------|
| **P0: 基建** | 1 | 创建 `packages/laffybot-agent-runtime/` 骨架 + 根 `pyproject.toml` 的 `uv workspace` 配置 | 仓库 monorepo 结构就绪 | `uv workspace` 识别子包，`uv run --package laffybot-agent-runtime python -c "..."` 可用 |
| | 2 | 复制 `providers/` 下全部文件到新包；修改内部 import（`laffybot.providers.*` → `laffybot_agent_runtime.providers.*`） | provider 层在新包独立 | 新包可 import `laffybot_agent_runtime.providers.base.BaseProvider` |
| | 3 | 复制 `cancellation.py`, `events.py` 到新包（零外部依赖） | 事件 + 取消机制 | 可构造 `CancellationToken`, `SSEEvent` |
| | 4 | 复制 `tools/` 全部文件；修改内部 import；按 base → errors → registry → filesystem/shell/mcp/skill_view 顺序 | 工具系统就位 | `ToolRegistry` 可注册 `ExecTool`, `ReadFileTool` 等 |
| | 5 | 复制 `context/` 全部文件；修改内部 import（context 内部引用 `laffybot.config.ContextConfig` → `laffybot_agent_runtime.config.ContextConfig`） | 上下文构建就位 | `SimpleContextBuilder.build_messages()` 可用 |
| | 6 | 复制 `runner.py`, `heartbeat.py`, `title_generator.py` 到新包；修改 envinronment var 前缀 | Agent 主循环就位 | `AgentRunner.run_stream()` 可基于 mock provider 运行 |
| | 7 | 复制 `skills/` 全部文件；定义 `SkillRegistryStore` Protocol；修改 `SkillRegistry` 接收 Protocol 而非 `AppSettingStore` | Skill 系统就位 | `SkillRegistry` 可用 Protocol 实例构建 |
| | 8 | 复制 `ContextConfig` 到新包 `config.py` | 配置模型就位 | 新包可 `from laffybot_agent_runtime.config import ContextConfig` |
| **P1: 接入** | 9 | 逐一修改 laffybot 侧的 22 处 import（按 4.4 的三种类型批量替换）；删除 `agent/`, `context/`, `providers/` 三个目录；清理 `tests/` 对应目录 | laffybot 编译通过 | `uv run ruff check .` 无 import 错误；`uv run mypy laffybot/` 通过 |
| | 10 | 将 `tests/agent/`, `tests/context/`, `tests/providers/` 移入新包 `tests/`；修改其中 import；保留的测试改为 import 新包 | 测试全部通过 | 两个包分别 `uv run pytest` 通过 |
| **P2: 收尾** | 11 | 更新 `pyproject.toml` 的 `dependencies` 字段；验证 `uv lock` 正确解析 workspace 依赖 | 依赖链正确 | `uv sync` 无错误 |
| | 12 | 全局搜索 `LAFFYBOT_HEARTBEAT_INTERVAL_S` 确保已更名为新常量；更新 `docs/` 中相关环境变量文档 | 无遗留 env var | `grep -r LAFFYBOT_HEARTBEAT_INTERVAL_S` 无结果 |
| | 13 | 运行完整质量门禁：`ruff check`, `ruff format --check`, `mypy`, `pytest` | 双包均通过 | 两个包各自 CI 步骤通过 |
| | 14 | 更新 `README.md`, `AGENTS.md` 反映新结构 | 文档与实际一致 | 目录结构图和依赖声明匹配源码 |

---

## 9. 现有技术债

以下为代码审计中发现的预存问题，不在本计划范围内，但记录以供参考：

| 类别 | 位置 | 描述 |
|------|------|------|
| Reliability | `laffybot/session/mcp_server_store.py:292` | `update_server()` 中 `elif env is not None` 是不可达死代码。当调用方传入 `env=None` 时本应清除 DB 中的 env 字段，但 `elif env is not None` 永远不会触发（`if env is not None` 已捕获）。应为 `elif env is None:` |
| Reliability | `laffybot/session/mcp_server_store.py:301` | 同上，`elif headers is not None` 应为 `elif headers is None:` |

---

## 10. 验收标准

| # | 标准 | 验证方式 | 关联阶段 |
|---|------|---------|---------|
| 1 | 新包从 PyPI（或 workspace）安装后，`from laffybot_agent_runtime.runner import AgentRunner` 可工作 | `uv run --package laffybot-agent-runtime python -c "from laffybot_agent_runtime.runner import AgentRunner; print(AgentRunner)"` | P0 |
| 2 | 新包所有公共 API（`AgentRunner`, `CancellationToken`, `SSEEvent`, `Tool`, `ToolRegistry`, `ContextBuilder`, `BaseProvider`, `OpenAIProvider`）均可独立 import | 同上方式验证每个核心类 | P0 |
| 3 | 新包运行 `ruff check . && ruff format --check . && mypy laffybot_agent_runtime/` 通过 | CI 步骤 | P2 |
| 4 | 主包运行 `ruff check . && ruff format --check . && mypy laffybot/` 通过 | 当前质量门禁 | P2 |
| 5 | 主包所有现有测试通过（pytest） | `uv run pytest tests/` | P1 |
| 6 | 新包所有迁移的测试通过 | `uv run --package laffybot-agent-runtime pytest tests/` | P1 |
| 7 | `laffybot/agent/` 目录已删除 | `ls laffybot/agent/` 返回 `No such file` | P1 |
| 8 | `laffybot/context/` 目录已删除 | `ls laffybot/context/` 返回 `No such file` | P1 |
| 9 | `laffybot/providers/` 目录已删除 | `ls laffybot/providers/` 返回 `No such file` | P1 |
| 10 | `laffybot/config.py` 不包含 `ContextConfig` | `grep -c "class ContextConfig" laffybot/config.py` 返回 0 | P1 |
| 11 | 环境变量 `LAFFYBOT_HEARTBEAT_INTERVAL_S` 被替换为 `LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S` | `grep -r LAFFYBOT_HEARTBEAT_INTERVAL_S .` 无结果 | P2 |
| 12 | `SkillRegistryStore` Protocol 在 runtime 中定义，laftybot 的 `AppSettingStore` 隐式实现 | `grep -c "class SkillRegistryStore" packages/laffybot-agent-runtime/src/laffybot_agent_runtime/skills/registry.py` > 0 | P0 |
| 13 | 端到端验证：用 `dev.sh` 启动主应用，发送一条消息，得到完整 SSE 事件流 | 手动回归 | P2 |
