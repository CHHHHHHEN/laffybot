# OpenCode 上下文管理-上下文压缩设计文档

> **文档性质**：设计文档 / 逆向分析
> **最后更新**：2026-05-16
> **实现状态**：已实现
> **源码位置**：`third-party/opencode/packages/opencode/src/session/`

> **文档范围说明**：本文档专注于 OpenCode 的会话上下文管理机制——包括溢出检测、Compaction（压缩）、尾轮保留策略和历史工具输出裁剪（Pruning）。
>
> **本文档不包含以下内容**：
> - 消息模型的具体数据结构定义
> - Session/Message 的持久化细节
> - 测试策略和测试用例

## 概述

OpenCode 的上下文管理机制解决 Agent 对话上下文超出模型上下文窗口的问题。核心策略是：检测溢出 → 调用轻量模型对历史对话生成结构化摘要 → 将摘要作为"压缩后的历史"注入上下文 → 保留最近的若干轮对话原文以确保当前的执行连续性。

系统提供三层防御：**历史工具输出裁剪（Pruning）**、**上下文压缩（Compaction）**、以及**溢出模式（Overflow Mode）**。

## 架构位置

```
Session Prompt Loop
       │
       ├── isOverflow() 检测 ──→ 触发 Compaction
       │                          │
       │                          ├── create() ──→ 插入 CompactionPart 用户消息
       │                          │
       │                          └── process() ──→ LLM 生成结构化摘要
       │                                              │
       │                                              ├── Tail Selection（尾轮保留）
       │                                              ├── Summary Generation
       │                                              └── Auto-Continue（可选）
       │
       └── prune() ──→ 后台裁剪旧工具输出
                        │
                        └── 跳过最近 2 轮 + 已 compact 消息
```

### 依赖关系

| 组件 | 依赖 | 方向 |
|------|------|------|
| `SessionCompaction` | `Session`, `Config`, `Provider`, `Agent`, `Plugin`, `SessionProcessor`, `Bus`, `RuntimeFlags` | 聚合多个 Service |
| `SessionProcessor` | `LLM`, `SessionSummary` | 处理流式响应并设置 needsCompaction |
| `SessionPrompt` | `SessionCompaction` | 编排 loop 调用 compaction |
| `overflow.ts` | 无 Service 依赖（纯函数） | 被 compaction.ts 和 processor.ts 引用 |

### 设计决策

- **Compaction 使用独立 Agent/模型**：配有一个专门的 `compaction` agent（可在配置中指定模型），与主对话模型分离，避免占用主模型配额
- **摘要驱动而非截断**：不是简单丢弃旧消息，而是用 LLM 将历史压缩为结构化摘要，保留语义信息
- **非阻塞后台执行**：Pruning 完全后台异步执行（`forkIn(scope)`），Compaction 在主循环中同步执行但结果不阻塞用户响应
- **Plugin 可扩展**：通过 `"experimental.session.compacting"` 和 `"experimental.compaction.autocontinue"` 插件钩子，允许第三方修改或替换 Compaction 行为

## 核心职责

### 1. 溢出检测（Overflow Detection）

**位置**：`session/overflow.ts`

在每次 Step Finish 事件发生后计算当前消息的 token 总量，与模型可用上下文窗口比较：

- **可用窗口** = `min(model.limit.context, model.limit.input) - reserved`
- **reserved** = 配置值 `compaction.reserved` 或 `min(20000, maxOutputTokens)`——为 Compaction 自身保留的 token 缓冲区
- **溢出条件**：`tokens.total >= 可用窗口`

溢出检测路径：
1. `SessionProcessor` 在 `finish-step` 事件中调用 `overflow.isOverflow()` → 设置 `needsCompaction = true` → LLM stream 被 `takeUntil` 截断 → 返回 `"compact"`
2. `SessionPrompt` loop 在每次迭代后检查 `compaction.isOverflow()` → 插入自动 Compaction

### 2. 上下文压缩（Compaction）

**位置**：`session/compaction.ts`

Compaction 的核心是将对话历史压缩为结构化摘要。流程如下：

1. **创建 Compaction 消息**：`create()` 在 Session 中插入一条 role=user 的消息，携带 `CompactionPart`（标记 type=compaction，记录自动/手动模式、溢出标志）
2. **选择要压缩的消息**：`select()` 方法实现**尾轮保留策略**：
   - 识别所有 user turn（排除之前已 compact 的消息）
   - 取最后 N 轮（`compaction.tail_turns`，默认 2）
   - 计算最近的 N 轮 token 总量，若超出保留预算（`preserve_recent_tokens`），对最旧的一轮做 `splitTurn()` 截断
   - 返回 `head`（需要压缩的历史）和 `tail_start_id`（保留的起始消息ID）
3. **生成摘要**：将 `head` 消息转换为模型消息格式（去除媒体文件、裁剪工具输出至 2000 字符），调用 compaction agent 的 LLM 生成结构化摘要
4. **Auto-Continue**：若 `auto=true` 且 LLM 返回 `"continue"`，自动插入一条 "Continue if you have next steps..." 消息，触发下一轮对话
5. **Overflow Mode**：当因媒体附件过大导致 Provider 拒绝请求时，`overflow=true` 的 Compaction 会额外找到一条正常的用户消息进行重放（replay），并清除媒体文件

**Summary Template（摘要模板）**：

固定结构：Goal → Constraints & Preferences → Progress (Done / In Progress / Blocked) → Key Decisions → Next Steps → Critical Context → Relevant Files。Compaction Agent 被要求保持此结构不变，使用简洁的要点而非段落。

### 3. 工具输出裁剪（Pruning）

**位置**：`session/compaction.ts` — `prune()` 方法

Pruning 作为后台任务在每次 loop 迭代结束时触发。策略：

- 从最新消息反向扫描，跳过最近 2 轮用户对话
- 跳过已包含 summary 的 assistant 消息（即已 compact）
- 累计找到的工具调用的 output token，保留 `PRUNE_PROTECT`（40K）token 的最近工具输出
- 对超出保护额度的旧工具输出：标记其 `time.compacted` 并持久化
- 受保护的工具（`skill`）永不裁剪
- 实际裁剪阈值：必须累计超过 `PRUNE_MINIMUM`（20K）token 才执行

### 4. 会话摘要（Session Summary）

**位置**：`session/summary.ts`

与 Context Management 相关但独立——记录会话维度的代码变更摘要（增删行数、文件数），通过 `Snapshot.diffFull()` 计算每一步之间的文件 diff，写入 `session_diff` 存储。不直接参与上下文压缩，但作为 UI 展示的依据。

## 数据流

### 自动 Compaction 触发流

```
Provider 返回 Step Finish
        │
        ▼
SessionProcessor.finish-step
        │
        ├── 汇总 tokens 和 cost
        ├── 记录 step-finish part
        └── isOverflow() 检测
                 │
            true ▼
        needsCompaction = true
        Stream.takeUntil 截断
        processor.process() 返回 "compact"
        │
        ▼
SessionPrompt loop 接收 "compact"
        │
        ├── compaction.create() ──→ 插入 CompactionPart 用户消息
        │
        ▼ (loop 继续)
    compaction.process()
        │
        ├── 获取 compaction agent 和模型
        ├── select() → tail preservation
        ├── 构建模型消息（stripMedia, toolOutputMaxChars）
        ├── 调用 compaction LLM → 结构化摘要
        │
        ├── result="continue" + auto=true
        │       └── 插入 auto-continue 消息 → 下一轮对话
        │
        └── result="stop"/
            result="compact"(溢出)
                └── 停止 loop
```

### Overflow Mode 流

```
Provider 拒绝请求（媒体文件过大等原因）
        │
        ▼
processor.process() 返回 "compact" (message.finish 为 undefined)
        │
        ▼
compaction.create(overflow=true)
        │
        ▼
compaction.process(overflow=true)
        │
        ├── 找到最近一个不含 compaction 的用户消息进行 replay
        ├── 从 replay 消息前截断消息历史
        ├── 执行 LLM compaction
        ├── auto-continue 消息提示 "媒体附件过大..."
        └── 跳过媒体文件的重放
```

## 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `compaction.auto` | bool | `true` | 上下文满时是否自动触发 Compaction |
| `compaction.prune` | bool | `true` | 是否启用历史工具输出裁剪 |
| `compaction.tail_turns` | int | `2` | Compaction 中保留的最近用户轮数（含对应的 assistant/tool 响应） |
| `compaction.preserve_recent_tokens` | int | `max(2000, min(8000, 可用窗口 × 25%))` | 保留的最近轮次 token 预算上限 |
| `compaction.reserved` | int | `min(20000, maxOutputTokens)` | Compaction 预留的 token 缓冲区，防止溢出时无法执行 compaction |

## 关键常量

| 常量 | 值 | 用途 |
|------|-----|------|
| `PRUNE_MINIMUM` | 20,000 | Pruning 实际执行的最小 token 阈值 |
| `PRUNE_PROTECT` | 40,000 | Pruning 保护的最新工具输出 token 量 |
| `TOOL_OUTPUT_MAX_CHARS` | 2,000 | Compaction 时工具输出的最大字符数（超出裁剪） |
| `MIN_PRESERVE_RECENT_TOKENS` | 2,000 | 尾轮保留预算下限 |
| `MAX_PRESERVE_RECENT_TOKENS` | 8,000 | 尾轮保留预算上限 |
| `COMPACTION_BUFFER` | 20,000 | 溢出计算中预留的 buffer |

## 错误处理

| 场景 | 表现 | 日志级别 |
|------|------|----------|
| Compaction LLM 返回 `"compact"`（自身溢出） | 设置为 ContextOverflowError，返回 `"stop"` | error |
| 找不到 parent 用户消息 | 抛出 Error（调用方处理） | - |
| Plugin 拦截 compaction | 通过 `compacting.prompt` 替换 prompt | - |
| Pruning 时消息不存在（NotFoundError） | `catchIf` 处理后返回 undefined，跳过 | info |
| 自动继续被 Plugin 拒绝 | `"experimental.compaction.autocontinue"` 返回 `{ enabled: false }` | - |

## 并发安全

- **Compaction** 在 Session Prompt Loop 中顺序执行，同一 session 不会并发
- **Pruning** 使用 `forkIn(scope)` 在后台异步执行，通过 `scope` 管理生命周期
- **消息更新** 通过 `session.updatePart()` / `session.updateMessage()` 写入，依赖底层 Storage 的事务保证

## 实现范围约束

### 本版本包含

- 自动溢出检测和 Compaction 触发
- 结构化摘要生成（预设模板，compaction agent）
- 尾轮保留策略（可配置轮数和 token 预算）
- 历史工具输出裁剪（后台异步执行）
- Overflow Mode（媒体文件过大时的回退策略）
- Plugin 扩展点（compacting 和 autocontinue）
- 配置化（auto / prune / tail_turns / preserve_recent_tokens / reserved）

### 本版本不包含

- 分层上下文（如 sliding window + summary 混合策略）
- 多模型上下文分配（不同消息使用不同模型的上下文窗口）
- 跨 session 上下文共享
- 自定义摘要模板的配置接口（模板内嵌在代码中）

## 与其他组件的关系

| 关系 | 说明 |
|------|------|
| **SessionPrompt** | Compaction 的调用者，在 loop 中检测溢出并编排 compaction 生命周期 |
| **SessionProcessor** | 流式处理过程中设置 `needsCompaction` 标志，截断 LLM stream |
| **Agent** | Compaction 使用专用 agent（`"compaction"`），可独立配置模型 |
| **Plugin** | 通过 `"experimental.session.compacting"` 和 `"experimental.compaction.autocontinue"` 钩子影响 compaction 行为 |
| **Session** | 提供消息/part 的 CRUD 操作，compaction 的结果通过标准 session 消息机制持久化 |
| **Bus / EventV2** | 发布 Compaction Started/Ended 事件，供 UI 和其他组件消费 |
