# Codex Agent 核心架构设计

本文档描述 OpenAI Codex 中 Agent 系统的核心架构设计，涵盖多代理协作、生命周期管理、通信机制等关键设计决策。

---

## 1. 设计目标

Codex Agent 架构旨在实现：

- **多代理协作**：支持层级化的代理树结构，允主代理派生子代理执行子任务
- **异步事件驱动**：采用 SQ/EQ 模式实现用户与代理间的异步通信
- **安全沙箱**：细粒度的权限控制和命令审批机制
- **状态独立**：每个代理独立运行，通过消息传递协作

---

## 2. 核心架构模式

### 2.1 层级化代理系统

代理以树形结构组织，使用 `AgentPath` 进行层级寻址。根代理（`/root`）作为会话入口点，子代理从父代理派生。

**设计决策**：

- 子代理继承父代理的 `AgentControl` 实例，保持控制面一致性
- 同一代理树共享 `AgentRegistry`，实现会话级别的资源限制
- 派生深度可配置，防止无限递归

### 2.2 SQ/EQ 异步通信模式

Codex 采用 Submission Queue / Event Queue 模式实现客户端与代理间的异步通信。

**提交操作类型**：
- 用户输入（`UserTurn`、`UserInput`）
- 代理间通信（`InterAgentCommunication`）
- 任务中断（`Interrupt`）
- 命令审批响应（`ExecApproval`）

**事件消息类型**：
- 回合生命周期（`TurnStarted`、`TurnComplete`）
- 消息内容（`AgentMessage`、`UserMessage`）
- 工具调用（`McpToolCallBegin/End`）
- 命令执行（`ExecCommandBegin/End`）
- 子代理派生（`CollabAgentSpawnBegin/End`）

---

## 3. 核心组件

### 3.1 AgentControl（控制面句柄）

`AgentControl` 是多代理操作的控制面句柄，由会话持有。

**职责**：
- 派生新代理
- 管理代理间通信
- 维护代理树元数据

**设计约束**：
- 每个根代理树创建一个实例
- 子代理共享父代理的实例，保持注册表作用域在根线程级别
- 使用弱引用避免循环引用

### 3.2 AgentRegistry（代理注册表）

`AgentRegistry` 追踪已派生的代理，管理会话级限制。

**职责**：
- 记录活跃代理元数据
- 管理代理昵称分配与去重
- 强制执行最大代理数量限制
- 追踪派生深度

**限制机制**：
- 会话内最大子代理数量（`max_threads`）
- 代理树最大深度（`max_depth`）
- 超限时返回 `AgentLimitReached` 错误

### 3.3 AgentMetadata（代理元数据）

每个代理的元数据包括：线程唯一标识、层级路径、人类可读昵称、角色配置名称、最近任务描述。

### 3.4 AgentStatus（代理状态）

代理生命周期状态机：

| 状态 | 含义 | 可转换至 |
|------|------|----------|
| `PendingInit` | 等待初始化 | `Running` |
| `Running` | 正在执行 | `Completed`, `Errored`, `Interrupted`, `Shutdown` |
| `Interrupted` | 被中断 | `Running`, `Shutdown` |
| `Completed` | 完成 | - |
| `Errored` | 错误终止 | - |
| `Shutdown` | 已关闭 | - |
| `NotFound` | 不存在 | - |

---

## 4. 代理间通信

### 4.1 消息结构

代理间消息包含：发送方路径、接收方路径、抄送列表、消息内容、是否触发执行标记。

### 4.2 Mailbox（邮箱）

每个代理拥有一个 `Mailbox`，用于接收其他代理的消息。

**设计决策**：
- 使用无界通道实现，支持异步消息传递
- 单调递增序列号追踪消息顺序
- `trigger_turn` 标记的消息会触发代理执行

**数据流**：发送方将消息封装为 `Op::InterAgentCommunication`，经事件队列投递至接收方邮箱，接收方通过 `MailboxReceiver` 消费并处理。

---

## 5. 子代理派生

### 5.1 历史继承模式

派生子代理时可选择历史继承策略：

| 模式 | 说明 |
|------|------|
| `FullHistory` | 继承完整对话历史 |
| `LastNTurns(N)` | 仅继承最近 N 个回合 |

### 5.2 历史过滤规则

派生子代理时，历史项按以下规则过滤：

- **保留**：`system`、`developer`、`user` 消息；`assistant` 的 `FinalAnswer` 阶段消息
- **丢弃**：工具调用、推理内容、上下文压缩标记等

**设计理由**：子代理建立独立的上下文基线，避免继承父代理的运行时状态。

### 5.3 派生深度控制

派生深度超过配置上限时，禁用相关特性（`SpawnCsv`、`Collab`），防止无限递归。

---

## 6. 工具集成架构

### 6.1 工具分类

| 类别 | 说明 |
|------|------|
| MCP Tools | Model Context Protocol 服务器工具 |
| Shell Commands | 沙箱强制的命令执行 |
| Dynamic Tools | 运行时动态提供的工具 |
| Built-in Tools | 内置工具（plan、request_permissions 等） |

### 6.2 审批系统

命令审批策略决定何时需要用户确认：

| 策略 | 行为 |
|------|------|
| `OnRequest` | 每次请求审批（默认） |
| `Never` | 从不审批 |
| `UnlessTrusted` | 信任源跳过审批 |
| `OnFailure` | 仅失败时审批 |
| `Granular` | 细粒度控制 |

**Guardian 评估**：高风险操作触发自动风险评估，生成评估事件供前端展示。

---

## 7. 沙箱与安全

### 7.1 沙箱策略

| 策略 | 限制范围 |
|------|----------|
| `ReadOnly` | 只读文件系统 |
| `WorkspaceWrite` | 工作区写入权限 |
| `DangerFullAccess` | 完全访问（危险） |
| `ExternalSandbox` | 外部沙箱进程 |

### 7.2 平台实现

- **macOS**：Seatbelt
- **Linux**：Landlock / bubblewrap
- **Windows**：Token 限制

### 7.3 权限配置

`PermissionProfile` 定义细粒度权限：文件系统访问模式、网络策略、特殊路径处理。

---

## 8. 会话与线程

### 8.1 SessionSource（会话来源）

会话来源决定代理的初始化上下文和权限继承：`Cli`、`VSCode`、`Exec`、`Mcp`、`SubAgent`。

### 8.2 ThreadSource（线程来源）

线程来源追踪执行发起方：`User`（用户发起）、`Subagent`（代理派生）、`MemoryConsolidation`（自动内存整理）。

### 8.3 TurnContext（回合上下文）

每个回合携带独立的上下文配置：工作目录、沙箱策略、审批策略、模型配置、推理参数、用户指令、开发者指令、权限配置、网络策略。

---

## 9. 架构原则

| 原则 | 实现方式 |
|------|----------|
| 异步事件驱动 | SQ/EQ 模式 |
| 层级多代理 | AgentPath 树结构 + 共享 Registry |
| 状态独立 | 消息传递 + 历史过滤派生 |
| 权限安全 | 沙箱策略 + 审批系统 |
| 工具抽象 | 统一工具接口（MCP/Shell/Dynamic） |
| 事件流 | 丰富的 EventMsg 类型供 UI 集成 |

---

## 10. 关键文件索引

| 组件 | 文件路径 |
|------|----------|
| AgentControl | `codex-rs/core/src/agent/control.rs` |
| AgentRegistry | `codex-rs/core/src/agent/registry.rs` |
| Mailbox | `codex-rs/core/src/agent/mailbox.rs` |
| AgentPath | `codex-rs/protocol/src/agent_path.rs` |
| Op / EventMsg | `codex-rs/protocol/src/protocol.rs` |
| 多代理指导 | `codex-rs/core/hierarchical_agents_message.md` |
