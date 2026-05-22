# 重构计划：严格对齐 ARCHITECTURE.md

> 零兼容层，零弃用标记。文件直接搬，import 直接改。重构期间项目可能不可运行，完成后一次性修复全部 import 断链。

---

## 分层对照

| ARCHITECTURE 层 | 职责 | 代码位置 (目标) | 当前代码位置 (来源) |
|---|---|---|---|
| API 层 | HTTP/SSE 协议适配、输入校验、路由分发 | `laffybot/api/` | 部分合规，但含违规：路由直调 Store、直读 request.app.state |
| 后端服务层 | 会话编排、状态管理、上下文装配 | `laffybot/session/`, `laffybot/memory/` | 含 SessionManager、MemoryManager — 但状态机、异步事件未分离 |
| Agent Runtime | 纯 AI 对话循环 | `packages/laffybot-agent-runtime/` | 部分合规，但含外溢：`ProviderFactory` Protocol 不应放在此层 |
| 基础设施层 | EventBus、持久化、可观测性 | `laffybot/eventbus/`, `laffybot/db/`, `laffybot/observability/` | 当前 EventBus 在 `laffybot/api/`；Store ABC+Impl 在 `laffybot/session/` 和 `laffybot/memory/` |

---

## Phase 0 — 基础设施层对齐 (laffybot/db/ + laffybot/eventbus/)

### 0a. `laffybot/db/` — 持久化存储层

将当前散落在 `laffybot/session/` 和 `laffybot/memory/` 的 Store ABC + SQLite 实现搬入基础设施层。

```
laffybot/db/
├── __init__.py
├── base.py                  # (空, 或放置公共类型)
├── session_store.py         # SessionStore ABC + SQLiteStore     (← laffybot/session/store.py)
├── provider_store.py        # ProviderStore ABC + SQLiteProviderStore (← laffybot/session/provider_store.py)
├── mcp_server_store.py      # McpServerStore ABC + SQLiteMcpServerStore (← laffybot/session/mcp_server_store.py)
├── app_setting_store.py     # AppSettingStore ABC + SQLiteAppSettingStore (← laffybot/session/app_setting_store.py)
├── memory_store.py          # MemoryStore ABC + SQLiteMemoryStore (← laffybot/memory/store.py)
├── consolidated_store.py    # ConsolidatedMemoryStore            (← laffybot/memory/consolidated_store.py)
└── errors.py                # DB 层错误 (可选的)
```

操作：
1. `git mv laffybot/session/store.py laffybot/db/session_store.py`
2. `git mv laffybot/session/provider_store.py laffybot/db/provider_store.py`
3. `git mv laffybot/session/mcp_server_store.py laffybot/db/mcp_server_store.py`
4. `git mv laffybot/session/app_setting_store.py laffybot/db/app_setting_store.py`
5. `git mv laffybot/memory/store.py laffybot/db/memory_store.py`
6. `git mv laffybot/memory/consolidated_store.py laffybot/db/consolidated_store.py`
7. 删除原先的所有文件（`git rm`）。不留 re-export 兼容层。

后果：所有 `from laffybot.session.store import SessionStore` 等 import 断裂。Phase 3 统一修复。

### 0b. `laffybot/eventbus/` — 事件总线基础设施

从 `laffybot/api/event_bus.py` 迁移。

```
laffybot/eventbus/
├── __init__.py
├── bus.py          # EventBus 类 + get_event_bus() 单例 (← laffybot/api/event_bus.py)
├── types.py        # GlobalEvent dataclass (← laffybot/api/event_bus.py 中内联)
└── protocol.py     # EventPublisher Protocol (← laffybot/session/interfaces.py)
```

操作：
1. 创建 `laffybot/eventbus/` 包
2. 将 `laffybot/api/event_bus.py` 的 `EventBus`、`GlobalEvent`、`get_event_bus` 搬入 `laffybot/eventbus/bus.py`
3. 将 `laffybot/session/interfaces.py` 的 `EventPublisher` Protocol 搬入 `laffybot/eventbus/protocol.py`
4. `git rm laffybot/api/event_bus.py`
5. `git rm laffybot/session/interfaces.py`
6. `laffybot/session/__init__.py` 中删除 `EventPublisher` 的导出

### 0c. `laffybot/observability/` — 可观测性基础设施

```
laffybot/observability/
├── __init__.py
├── health.py     # /health, /ready 逻辑 (← laffybot/api/health_routes.py 中的纯逻辑)
├── logging.py    # 结构化日志配置 (← laffybot/log_config.py)
└── tracing.py    # OpenTelemetry (未来扩展)
```

操作：
1. 将 `laffybot/log_config.py` 搬入 `laffybot/observability/logging.py`
2. 将 `laffybot/api/health_routes.py` 中的健康检查逻辑提取到 `laffybot/observability/health.py`

---

## Phase 1 — 后端服务层重构 (SessionStateMachine + SessionLockPort + AsyncEventProcessor)

### 1a. `SessionStateMachine` — 纯状态机

**新建 `laffybot/session/state_machine.py`**

从 `laffybot/session/manager.py` 中提取状态转移逻辑。

```python
class SessionStateMachine:
    """纯状态机, 不包含业务规则. 只定义状态和合法转移."""
    
    def __init__(self, lock_port: SessionLockPort) -> None
    
    # 核心方法
    async def transition_to_busy(self, session_id: str) -> tuple[SessionStatus, str]:
        """idle→busy 转移. 返回 (new_state, lock_key).
        
        内部调用 lock_port.try_lock().
        如果锁失败或当前非 idle 状态, 抛出 SessionStateError.
        """
    
    async def transition_to_idle(self, session_id: str, lock_key: str, error_message: str | None = None) -> SessionStatus:
        """busy→idle 转移.
        
        内部调用 lock_port.unlock().
        """
    
    async def force_to_idle(self, session_id: str) -> SessionStatus:
        """无条件重置为 idle (用于 finally 兜底)."""
    
    def cancel(self, session_id: str, reason: str | None = None) -> None:
        """设置取消标记, 不下 DB."""
```

状态转移表：

| From | To | 条件 |
|---|---|---|
| idle | busy | lock_port.try_lock() 成功 |
| busy | idle | lock_port.unlock() |
| busy | error | lock_port.unlock() + 含 error_message |
| idle | idle | 取消无状态变更 |
| busy | busy | cancel() 只设 token |

### 1b. `SessionLockPort` — 并发锁协议

**新建 `laffybot/session/lock_port.py`**

```python
class SessionLockPort(Protocol):
    """并发锁抽象. SessionStateMachine 通过此端口获取/释放锁."""
    
    async def try_lock(self, session_id: str, timeout: float = 30.0) -> str:
        """尝试加锁. 返回 lock_key. 超时/失败抛出 LockAcquisitionError."""
    
    async def unlock(self, session_id: str, lock_key: str) -> None:
        """释放锁. lock_key 不匹配抛出 LockMismatchError."""
    
    async def force_unlock(self, session_id: str) -> None:
        """强制解锁 (看门狗/超时恢复时使用)."""
```

**新建 `laffybot/session/local_lock_port.py`**

```python
class LocalSessionLockPort:
    """基于 asyncio.Lock 的进程内实现."""
    # 实现 SessionLockPort Protocol
```

### 1c. `AsyncEventProcessor` — 异步事件处理子层

**新建 `laffybot/session/async_events.py`**

从 `laffybot/session/manager.py` 中提取四个后台任务：

- `auto_title(session_id)` — 替代 `_trigger_auto_title`
- `memory_extract(session_id)` — 替代 `_trigger_extract`
- `context_compress(session_id, region_info, summarizer)` — 替代 `_fire_summary_and_replace`
- `auto_archive_excess_sessions(session_id)` — 替代 `_auto_archive_excess_sessions`

```python
class AsyncEventProcessor:
    """异步事件处理子层. 订阅 EventBus, 无感后台处理.
    
    可靠性策略:
    - 失败可重试 (最多 3 次)
    - 可追踪 (request_id 贯穿日志)
    - 不影响主链路响应
    """
    
    def __init__(
        self,
        store: SessionStore,
        provider_store: ProviderStore,
        app_setting_store: AppSettingStore,
        provider_factory: ProviderFactory,
        memory_manager: MemoryManager | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None
    
    async def submit_auto_title(self, session_id: str) -> asyncio.Task
    async def submit_memory_extract(self, session_id: str) -> asyncio.Task
    async def submit_context_compress(self, session_id: str, region_info: RegionInfo, summarizer: LLMSummarizer) -> asyncio.Task
    async def submit_auto_archive(self, session_id: str) -> asyncio.Task
    
    async def shutdown(self) -> None
```

### 1d. `ContextBuilder` 增强 — 集成压缩能力

**修改 `laffybot_agent_runtime/context/builder.py` 或 `laffybot_agent_runtime/context/base.py`**

当前 `SessionManager` 直接 import `LLMSummarizer` 并创建实例。改为在 `ContextBuilder` 上增加：

```python
class ContextBuilder(ABC):
    # ... 现有方法
    
    async def compress_messages(
        self,
        messages: list[SessionMessage],
        model: str,
        provider: BaseProvider,  # 由调用方传入, ContextBuilder 不创建 provider
    ) -> tuple[list[dict], RegionInfo | None]:
        """检测是否需要压缩, 如需则返回压缩建议.
        
        调用方 (SessionManager 或 AsyncEventProcessor) 拿 RegionInfo 异步执行替换.
        """
```

这样 `SessionManager` 不再直接 import `LLMSummarizer`.

### 1e. `SessionManager` 瘦身

`laffybot/session/manager.py` 重写 `send_message()` 为纯编排：

```python
class SessionManager:
    """薄协调器: 只编排与事务边界, 不含子步骤实现."""
    
    async def send_message(self, session_id, content, skills_block=""):
        # 1. state.transition_to_busy()           → SessionStateMachine
        # 2. provider = ProviderFactory(...)       → ProviderFactory
        # 3. history = Store.load()               → SessionStore
        # 4. memories = MemMgr.get()              → MemoryManager
        # 5. ctx = ContextBuilder.build(...)      → ContextBuilder
        # 6. for event in runtime.execute(...):   → AgentRuntime
        #       yield event
        #       EventBus.publish(event)           → EventBus
        # 7. state.transition_to_idle()           → SessionStateMachine
        # 8. finally: force_to_idle()
        #
        # 事件收集聚合 → MessageAccumulator (辅助类)
```

**提取 `MessageAccumulator`** — 从 `send_message()` 中剥离事件收集/聚合的第 317-319、380-403 行。

```python
@dataclass
class MessageAccumulator:
    assistant_chunks: list[str]
    reasoning_chunks: list[str]
    accumulated_tool_calls: list[dict]
    
    def on_content(self, text: str) -> None
    def on_reasoning(self, text: str) -> None
    def on_tool_call(self, tool_call_id, name, arguments) -> None
    def on_tool_result(self, tool_call_id, success, result, duration_ms, error_message) -> None
    def build_assistant_message(self, usage) -> dict  # 用于 save_message
```

---

## Phase 2 — 依赖方向修复

### 2a. `ProviderFactory` Protocol 移至后端服务层

**新建 `laffybot/session/provider_factory.py`**

```python
class ProviderFactory(Protocol):
    """后端服务层定义的端口: Provider 选择与装配."""
    async def create_provider(self, config: ProviderConfig) -> BaseProvider: ...
```

操作：
1. 创建 `laffybot/session/provider_factory.py`
2. 从 `packages/laffybot-agent-runtime/src/laffybot_agent_runtime/providers/factory.py` 搬内容
3. `git rm` 原文件
4. 所有 `from laffybot_agent_runtime.providers.factory import ProviderFactory` 改为 `from laffybot.session.provider_factory import ProviderFactory`

### 2b. `DefaultProviderFactory` 从 API 层移至后端服务层

**当前**: `laffybot/api/dependencies.py:DefaultProviderFactory`

架构说 API 层只做协议适配，不应该有 Provider 实现选择。将 `DefaultProviderFactory` 移入后端服务层。

**新建 `laffybot/session/default_provider_factory.py`** (或放在 `laffybot/session/provider_factory.py` 同文件)

```python
class DefaultProviderFactory:
    """ProviderFactory 默认实现: 创建 OpenAIProvider."""
    async def create_provider(self, config: ProviderConfig) -> BaseProvider:
        return OpenAIProvider(config)
```

`laffybot/api/dependencies.py` 改为 `from laffybot.session.provider_factory import DefaultProviderFactory`.

### 2c. API 层直调 Store 违规修复

**`laffybot/api/session_routes.py`** 中修复:

1. `update_session_title` (第 366-391 行): 改为调用 `manager.update_session_title(session_id, title)`. 在 `SessionManager` 加同名方法.

2. `/settings/system-prompt` (第 397-412 行): 当前直接读写 `request.app.state.context_config`. 改为:
   - GET: `return {"system_prompt": await manager.get_system_prompt(session_id)}`
   - PUT: `await manager.set_system_prompt(session_id, payload.system_prompt)`
   - `SessionManager` 通过 `AppSettingStore` 持久化 system prompt

3. `/consolidated-memory` 路由 (第 622-698 行): 当前直接操作 `memory_manager.consolidated_store` 并 new `DefaultProviderFactory()`. 改为通过 `manager.get_consolidated_memory()` 和 `manager.trigger_consolidation()`.

### 2d. `laffybot/api/app.py` 瘦身

当前 `create_app()` 包含:
- Tool 注册 (第 80-87 行) — 应在后端服务层完成
- MCP manager 创建 (第 105-114 行) — 应在后端服务层完成

搬至 `SessionManager` 初始化流程或新建 `ToolRegistryFactory`.

---

## Phase 3 — import 断链修复

一次性修复全仓库所有 import 路径变更。

| 原 import | 新 import |
|---|---|
| `from laffybot.session.store import SessionStore, SQLiteStore` | `from laffybot.db.session_store import SessionStore, SQLiteStore` |
| `from laffybot.session.provider_store import ProviderStore, SQLiteProviderStore` | `from laffybot.db.provider_store import ProviderStore, SQLiteProviderStore` |
| `from laffybot.session.mcp_server_store import McpServerStore, SQLiteMcpServerStore` | `from laffybot.db.mcp_server_store import McpServerStore, SQLiteMcpServerStore` |
| `from laffybot.session.app_setting_store import AppSettingStore, SQLiteAppSettingStore` | `from laffybot.db.app_setting_store import AppSettingStore, SQLiteAppSettingStore` |
| `from laffybot.memory.store import MemoryStore, SQLiteMemoryStore` | `from laffybot.db.memory_store import MemoryStore, SQLiteMemoryStore` |
| `from laffybot.memory.consolidated_store import ConsolidatedMemoryStore` | `from laffybot.db.consolidated_store import ConsolidatedMemoryStore` |
| `from laffybot.api.event_bus import EventBus, GlobalEvent, get_event_bus` | `from laffybot.eventbus.bus import EventBus, GlobalEvent, get_event_bus` |
| `from laffybot.session.interfaces import EventPublisher` | `from laffybot.eventbus.protocol import EventPublisher` |
| `from laffybot_agent_runtime.providers.factory import ProviderFactory` | `from laffybot.session.provider_factory import ProviderFactory` |
| `from laffybot.api.dependencies import DefaultProviderFactory` | `from laffybot.session.provider_factory import DefaultProviderFactory` |
| `from laffybot.log_config import *` | `from laffybot.observability.logging import *` |

受影响的文件列表（需全局搜索替换）：
- `laffybot/api/dependencies.py`
- `laffybot/api/app.py`
- `laffybot/api/session_routes.py`
- `laffybot/session/manager.py`
- `laffybot/memory/manager.py`
- `laffybot/memory/consolidator.py`
- `laffybot/memory/extractor.py`
- `tests/session/test_session_manager.py`
- `tests/session/test_store.py`
- `laffybot/__main__.py`
- 其他任何引用点

---

## Phase 4 — 验证

```bash
# 类型检查
uv run mypy laffybot/
uv run mypy packages/laffybot-agent-runtime/src/laffybot_agent_runtime/

# lint
uv run ruff check . && uv run ruff format --check .

# 运行时
uv run python -m laffybot --help
```

---

## 执行总顺序

```
Phase 0a: laffybot/db/     (git mv 6 个文件, git rm 6 个)
Phase 0b: laffybot/eventbus/ (搬 EventBus + EventPublisher, git rm 2 个)
Phase 0c: laffybot/observability/ (搬 log_config + health 逻辑)
Phase 1a: SessionStateMachine (新建文件 + 提取状态转移)
Phase 1b: SessionLockPort + LocalSessionLockPort (新建 2 个文件)
Phase 1c: AsyncEventProcessor (新建文件 + 提取 4 个后台任务)
Phase 1d: ContextBuilder 增强 (添加 compress_messages)
Phase 1e: SessionManager 瘦身 + MessageAccumulator
Phase 2a: ProviderFactory Protocol 搬迁
Phase 2b: DefaultProviderFactory 搬迁
Phase 2c: API 层直调 Store 修复 (3 处)
Phase 2d: app.py 瘦身 (Tool 注册 + MCP manager)
Phase 3:  全仓库 import 修复
Phase 4:  验证 (mypy + ruff + 启动)
```

---

## 不做的范围

- 不新增 Provider 实现（如 AnthropicProvider）— 只重构现有，不新增功能
- 不改造 Agent Runtime 内部执行循环 — `AgentRunner` 保持现有实现
- 不重写 UI 层 — 只改后端
- 不新增数据库 schema — 保持现有 WAL SQLite
- 不写新测试 — 先完成重构，测试后补
