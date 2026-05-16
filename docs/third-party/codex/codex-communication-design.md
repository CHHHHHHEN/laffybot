# Codex 通信设计

本文档描述 OpenAI Codex 中的通信架构设计，包括客户端-代理通信、代理间通信、以及进程输出广播机制。

---

## 1. 设计目标

Codex 通信架构旨在实现：

- **双向异步通信**：客户端与代理间的非阻塞交互
- **请求-响应关联**：每个操作可追踪其产生的事件
- **代理间直接通信**：支持多代理协作场景
- **进程输出共享**：多消费者订阅同一进程输出

---

## 2. 整体架构

Codex 采用 **SQ/EQ (Submission Queue / Event Queue) 模式** 作为核心通信机制，辅以 **Broadcast Channel** 用于特定场景。

### 2.1 通信模式对比

| 模式 | 用途 | 通信方向 | 消费者数量 |
|------|------|----------|------------|
| SQ/EQ | 客户端-代理交互 | 双向 | 单消费者 |
| Mailbox | 代理间通信 | 单向 | 单消费者 |
| Broadcast | 进程输出、线程生命周期 | 单向 | 多消费者 |

### 2.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        ThreadManager                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  thread_created_tx (Broadcast)                          │ │
│  │    └─→ 订阅者: 线程创建监听器                             │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  CodexThread                                             │ │
│  │    └─→ Codex                                             │ │
│  │          ├─→ tx_sub (Submission Channel)  ←── 客户端     │ │
│  │          └─→ rx_event (Event Channel)     ──→ 客户端     │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 用户与 Agent 通信

### 3.1 用户输入类型

用户输入 (`UserInput`) 支持多种内容类型：

| 类型 | 用途 |
|------|------|
| `Text` | 文本输入，支持富文本标记（如图片占位符） |
| `Image` | 预编码的 data URI 图片 |
| `LocalImage` | 本地图片路径，提交时转换为 base64 |
| `Skill` | 技能选择（名称 + SKILL.md 路径） |
| `Mention` | 结构化提及（如 `app://connector-id`） |

### 3.2 提交操作类型

用户向 Agent 提交操作有三种形式：

| 操作 | 说明 | 适用场景 |
|------|------|----------|
| `UserTurn` | 完整回合输入，携带完整上下文配置 | 新回合开始 |
| `UserInput` | 简单输入，使用会话默认配置 | 快速输入 |
| `UserInputWithTurnContext` | 输入 + 上下文覆盖，原子更新 | 配置变更后输入 |

**`UserTurn` 携带的上下文配置**：

| 配置项 | 说明 |
|--------|------|
| `cwd` | 工作目录 |
| `approval_policy` | 命令审批策略 |
| `sandbox_policy` | 沙箱策略 |
| `permission_profile` | 权限配置 |
| `model` | 模型选择 |
| `effort` | 推理强度 |
| `collaboration_mode` | 协作模式 |
| `environments` | 环境选择 |

### 3.3 通信流程

```
┌─────────────────────────────────────────────────────────────────┐
│                          用户 → Agent                           │
│                                                                 │
│  客户端                                                          │
│    │                                                            │
│    │  submit(Op::UserTurn { items, cwd, policy, ... })          │
│    ├───────────────────────────────────────────────────────────→│
│    │                                                            │
│    │                                              Session        │
│    │                                                │            │
│    │                                                │ 1. 创建 TurnContext
│    │                                                │ 2. 更新 SessionSettings
│    │                                                │ 3. 处理用户输入
│    │                                                │ 4. 启动任务
│    │                                                │            │
│    │  Event { id, msg: TurnStarted }                             │
│    │←───────────────────────────────────────────────────────────│
│    │                                                            │
│    │  Event { id, msg: AgentMessage }                           │
│    │←───────────────────────────────────────────────────────────│
│    │                                                            │
│    │  Event { id, msg: McpToolCallBegin }                       │
│    │←───────────────────────────────────────────────────────────│
│    │                                                            │
│    │  Event { id, msg: McpToolCallEnd }                         │
│    │←───────────────────────────────────────────────────────────│
│    │                                                            │
│    │  Event { id, msg: TurnComplete }                           │
│    │←───────────────────────────────────────────────────────────│
│    │                                                            │
│    │  next_event()                                               │
│    ├───────────────────────────────────────────────────────────→│
│    │                                                            │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 Turn 生命周期

每个用户回合 (`Turn`) 的生命周期：

| 阶段 | 事件 | 说明 |
|------|------|------|
| 开始 | `TurnStarted` | 回合开始，携带 `turn_id` |
| 执行 | `AgentMessage`, `McpToolCallBegin/End`, ... | Agent 处理过程 |
| 完成 | `TurnComplete` | 回合结束，携带最终消息和耗时 |

**设计决策**：

- 每个回合绑定唯一的 `sub_id`（提交 ID）
- 所有事件携带 `sub_id`，便于客户端关联
- 回合结束后 Agent 进入空闲状态，等待下一输入

### 3.5 Steering（中途输入）

Agent 支持在活跃回合中接收额外用户输入，称为 **Steering**。

**使用场景**：
- 用户补充信息
- 回答 Agent 的提问
- 修正 Agent 的理解

**设计约束**：
- 仅在 `Regular` 类型回合中可用
- `Review` 和 `Compact` 回合不支持 Steering
- 输入被追加到回合的待处理队列

**错误场景**：

| 错误 | 说明 |
|------|------|
| `NoActiveTurn` | 无活跃回合，输入被返回 |
| `ActiveTurnNotSteerable` | 回合类型不支持 Steering |
| `ExpectedTurnMismatch` | 指定的回合 ID 与当前不匹配 |

### 3.6 事件持久化

所有事件在发送给客户端前，先持久化到 Rollout 存储：

| 步骤 | 说明 |
|------|------|
| 1. 持久化 | 将 `EventMsg` 写入 Rollout 文件 |
| 2. 追踪 | 记录到线程追踪系统 |
| 3. 投递 | 通过 `tx_event` 通道发送给客户端 |

**设计理由**：
- 支持会话恢复和重放
- 便于调试和审计
- 保证事件不丢失

---

## 4. SQ/EQ 模式

### 4.1 设计原理

SQ/EQ 模式实现客户端与代理间的双向异步通信：

- **Submission Queue (SQ)**：客户端提交操作 (`Op`) 到代理
- **Event Queue (EQ)**：代理产生事件 (`Event`) 返回客户端

每个 `CodexThread` 拥有独立的 SQ 和 EQ 通道，实现线程级别的隔离。

### 4.2 提交操作 (`Op`)

客户端通过 `submit()` 方法提交操作：

| 操作类型 | 用途 |
|----------|------|
| `UserTurn` | 用户回合输入 |
| `UserInput` | 用户原始输入 |
| `InterAgentCommunication` | 代理间通信 |
| `Interrupt` | 中断当前任务 |
| `ExecApproval` | 命令审批响应 |
| `Shutdown` | 关闭代理 |

**设计决策**：

- 每个提交自动分配唯一 ID（UUID v7）
- 支持可选的分布式追踪上下文 (`W3cTraceContext`)
- 提交失败时返回 `InternalAgentDied` 错误

### 4.3 事件消息 (`Event`)

代理产生的事件结构：

| 字段 | 说明 |
|------|------|
| `id` | 关联的提交 ID |
| `msg` | 事件消息体 (`EventMsg`) |

**事件类型**：

| 类别 | 事件 |
|------|------|
| 生命周期 | `TurnStarted`, `TurnComplete`, `ShutdownComplete` |
| 消息 | `AgentMessage`, `UserMessage` |
| 工具调用 | `McpToolCallBegin/End`, `ExecCommandBegin/End` |
| 审批 | `ExecApprovalRequest`, `GuardianAssessment` |
| 协作 | `CollabAgentSpawnBegin/End` |

### 4.4 请求-响应关联

每个 `Op` 提交时生成唯一 `id`，后续产生的所有 `Event` 都携带此 `id`，实现请求-响应链路追踪。

**设计理由**：

- 客户端可关联事件与具体操作
- 支持并发提交的场景
- 便于调试和日志分析

---

## 5. 代理间通信

### 5.1 Mailbox 机制

每个代理拥有一个 `Mailbox`，用于接收其他代理发送的消息。

**设计决策**：

- 使用无界通道 (`mpsc::unbounded_channel`) 实现
- 单调递增序列号追踪消息顺序
- 支持 `trigger_turn` 标记触发代理执行

### 5.2 消息结构

代理间消息 (`InterAgentCommunication`) 包含：

| 字段 | 说明 |
|------|------|
| `author` | 发送方路径 |
| `recipient` | 接收方路径 |
| `other_recipients` | 抄送列表 |
| `content` | 消息内容 |
| `trigger_turn` | 是否触发执行 |

### 5.3 通信流程

```
Agent A                          EventQueue                    Agent B
   │                                │                            │
   │  Op::InterAgentCommunication   │                            │
   ├───────────────────────────────→│                            │
   │                                │  投递至 Mailbox             │
   │                                ├───────────────────────────→│
   │                                │                            │
   │                                │        MailboxReceiver     │
   │                                │        (drain & process)   │
```

**设计理由**：

- 直接寻址：发送方必须知道接收方的 `AgentPath`
- 非阻塞：消息投递不阻塞发送方
- 顺序保证：同一发送方的消息按序到达

---

## 6. Broadcast 机制

### 6.1 设计场景

Broadcast Channel 用于**一对多**通信场景：

| 场景 | 通道 | 消息类型 |
|------|------|----------|
| 线程创建通知 | `thread_created_tx` | `ThreadId` |
| 进程输出共享 | `output_tx` | `Vec<u8>` |

### 6.2 线程创建广播

`ThreadManager` 维护 `thread_created_tx: broadcast::Sender<ThreadId>`，当新线程创建时广播通知。

**消费者**：需要监听线程创建的组件（如 UI、监控服务）

**设计约束**：

- 容量固定（1024），消费者滞后时丢弃旧消息
- 消费者可随时订阅，无需提前注册

### 6.3 进程输出广播

`UnifiedProcess` 使用 broadcast 通道共享进程输出：

**设计决策**：

- 多消费者可同时订阅同一进程的 stdout/stderr
- 支持消费者滞后时继续读取（`Lagged` 错误处理）
- 进程结束后通道关闭

---

## 7. 通道类型选择

### 7.1 通道类型对比

| 通道类型 | 用途 | 特点 |
|----------|------|------|
| `mpsc` | SQ/EQ、Mailbox | 多生产者单消费者 |
| `broadcast` | 进程输出、线程通知 | 多生产者多消费者 |
| `watch` | AgentStatus | 单生产者多消费者，保留最新值 |

### 7.2 选择原则

| 场景 | 推荐通道 | 理由 |
|------|----------|------|
| 请求-响应模式 | `mpsc` | 单消费者处理，保证顺序 |
| 状态广播 | `watch` | 消费者只需最新值 |
| 事件流 | `broadcast` | 多消费者，容忍丢失 |

---

## 8. 错误处理

### 8.1 通道关闭

当通道发送失败时，返回 `InternalAgentDied` 错误，表示代理已终止。

**客户端处理**：

- 检测代理生命周期
- 清理相关资源
- 通知用户

### 8.2 消费者滞后

Broadcast 通道消费者滞后时返回 `RecvError::Lagged`。

**处理策略**：

- 继续读取，忽略丢失消息
- 记录警告日志
- 不中断处理流程

---

## 9. 设计原则

| 原则 | 实现方式 |
|------|----------|
| 隔离性 | 每线程独立通道，避免交叉污染 |
| 可追踪性 | 提交 ID 关联请求-响应 |
| 非阻塞 | 异步通道，不阻塞主流程 |
| 容错性 | 通道关闭时优雅降级 |
| 可扩展性 | 支持多消费者场景 |

---

## 10. 关键文件索引

| 组件 | 文件路径 |
|------|----------|
| Op / Event | `codex-rs/protocol/src/protocol.rs` |
| CodexThread | `codex-rs/core/src/codex_thread.rs` |
| Codex (SQ/EQ) | `codex-rs/core/src/session/mod.rs` |
| Mailbox | `codex-rs/core/src/agent/mailbox.rs` |
| ThreadManager | `codex-rs/core/src/thread_manager.rs` |
| UnifiedProcess | `codex-rs/core/src/unified_exec/process.rs` |
