# Codex 上下文管理架构

> **文档性质**：设计参考文档
> **最后更新**：2026-05-16
> **实现状态**：已实现（Codex 源码分析）

> **文档范围说明**：本文档分析 OpenAI Codex 的上下文管理架构设计，提取可借鉴的设计模式和决策，为 laffybot 上下文管理演进提供参考。
>
> **本文档不包含以下内容**：
> - Codex 具体实现代码和文件路径（参见 Codex 源码）
> - Token 估算的具体算法实现
> - Hook 系统的具体实现细节
> - 持久化层的具体实现方式
>
> **与 Laffybot 的关系**：本文档为设计参考文档，不直接指导实现。具体实现决策需结合 laffybot 架构约束和优先级。

## 概述

Codex 实现了多层上下文管理系统，解决长对话 AI Agent 的核心挑战：

| 挑战 | Codex 解决方案 |
|------|---------------|
| 上下文窗口管理 | 动态追踪 token 使用量，在模型限制内适配历史 |
| 上下文压缩 | 多策略压缩系统（本地/远程），保留关键信息 |
| 上下文注入 | 类型化片段系统，支持差异计算和识别 |
| 上下文差异计算 | 参考上下文快照机制，减少冗余注入 |
| 上下文持久化 | 会话状态和消息历史分离存储 |

## 架构层次

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Session Layer                                   │
│  Session (会话状态)  →  TurnContext (轮次配置)  →  Truncation (边界管理)    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Context Manager Layer                               │
│  ContextManager (历史存储 + Token 追踪 + 版本控制 + 参考上下文)             │
│  + Normalization (不变量强制) + Updates (差异生成)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Context Fragments Layer                             │
│  类型化片段：Environment | Goal | Permissions | UserInstructions | Skills   │
│  特性：带标记识别 + 角色定义 + 内容渲染                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Compaction System                                   │
│  触发器：Auto (token 限制) | Manual (用户请求) | Mid-turn (轮中)             │
│  策略：本地压缩 (摘要替换) | 远程压缩 (API 支持)                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 核心设计模式

### 1. 上下文管理器 (ContextManager)

**职责**：
- **历史存储**：维护有序的消息、工具调用和输出列表
- **Token 追踪**：估算和追踪 token 使用量，支持容量控制
- **历史版本控制**：修改时递增版本号，支持缓存失效判断
- **参考上下文**：维护基准上下文快照，用于计算轮次间差异

**设计要点**：
- 版本号机制：历史重写时递增，支持高效缓存失效
- 参考快照：存储前一轮的基准上下文，后续轮次仅发送差异
- 支持历史回滚（移除最近 N 轮）和整体替换（压缩场景）

### 2. 上下文片段 (Context Fragments)

**设计模式**：Trait 定义的可注入上下文片段

**核心 Trait 定义**：`ContextualUserFragment`

Trait 定义了四个核心常量和一个方法：
- **ROLE**：消息角色（user 或 developer）
- **START_MARKER**：XML 起始标记，用于识别已注入片段
- **END_MARKER**：XML 结束标记
- **body()**：生成片段正文内容

**片段接口契约**：
- `render()` 方法拼接 START_MARKER + body() + END_MARKER
- `into()` 方法将片段转换为 `ResponseItem::Message`
- `matches_text()` 静态方法检测文本是否为该类型片段

**片段类型**：

| 片段 | 用途 | 角色 | 标记 |
|------|------|------|------|
| EnvironmentContext | 工作区、Shell、网络配置 | user | `<environment_context>` |
| GoalContext | 运行时目标引导 | user | `<goal_context>` |
| PermissionsInstructions | 审批策略、沙箱规则 | developer | 无标记（纯文本） |
| UserInstructions | 开发者偏好（AGENTS.md） | user | `# AGENTS.md instructions for...` |
| SkillInstructions | 可用技能/能力 | user | `<skill>` |
| CollaborationModeInstructions | 模式特定行为 | developer | 无标记 |
| HookAdditionalContext | Hook 提供的自定义上下文 | user | 无标记 |
| ModelSwitchInstructions | 模型切换指令 | developer | `<model_switch>` |
| RealtimeStartInstructions | 实时模式启动 | developer | 无标记 |
| RealtimeEndInstructions | 实时模式结束 | developer | 无标记 |
| PersonalitySpecInstructions | 模型个性配置 | developer | 无标记 |

**设计要点**：
- XML 标记识别：支持后续过滤、解析和差异计算
- 类型安全注入：避免字符串拼接错误，编译期检查角色一致性
- 无标记片段：直接注入内容，不参与差异计算，适用于一次性指令
- 差异计算时仅比较有标记片段，无标记片段始终视为变化

### 3. 上下文规范化 (Normalization)

**目的**：确保发送给模型的历史满足不变量

**核心函数**：

| 函数 | 职责 |
|------|------|
| `ensure_call_outputs_present` | 为无输出的调用生成合成输出（值为 "aborted"） |
| `remove_orphan_outputs` | 移除没有对应调用的孤儿输出 |
| `remove_corresponding_for` | 移除项目时同步移除其配对项 |
| `strip_images_when_unsupported` | 模型不支持图像时替换为占位文本 |

**不变量约束**：
1. **调用/输出配对**：每个函数调用必须有对应输出（FunctionCall → FunctionCallOutput）
2. **孤儿移除**：没有对应调用的输出被移除（包括 ToolSearch、CustomTool、LocalShell）
3. **图像剥离**：模型不支持图像时移除图像内容，替换为 "image content omitted because you do not support image input"

**调用时机**：在 `ContextManager.for_prompt()` 方法中，构建发送给模型的提示词前强制执行

**设计要点**：
- 规范化在内存中进行，不修改持久化历史
- 合成输出标记为 "aborted"，便于调试识别
- 移除孤儿输出时记录错误日志，帮助定位上游问题

### 4. 上下文更新 (Updates)

**设计模式**：基于差异的增量更新

**核心机制**：`reference_context_item` 参考上下文快照

参考上下文是一个 `TurnContextItem` 结构，存储上一轮的基准状态：
- 工作目录、Shell 配置
- 权限配置、审批策略
- 协作模式、个性设置
- 实时模式状态
- 模型标识

**更新生成流程**：

```
当前 TurnContext
      │
      ├─→ 与 reference_context_item 比较
      │
      ├─→ 环境变化? → EnvironmentContext.diff_from_turn_context_item()
      │
      ├─→ 权限变化? → PermissionsInstructions.render()
      │
      ├─→ 协作模式变化? → CollaborationModeInstructions.render()
      │
      ├─→ 实时模式变化? → RealtimeStartInstructions / RealtimeEndInstructions
      │
      ├─→ 模型切换? → ModelSwitchInstructions.render()
      │
      └─→ 个性变化? → PersonalitySpecInstructions.render()
```

**更新类型**：
- 环境更新（工作区、Shell、网络变化）
- 权限更新（权限配置变化）
- 协作模式更新（模式切换）
- 实时模式更新（开启/关闭）
- 个性更新（模型个性变化）
- 模型切换更新（模型标识变化）

**注入策略**：

| 场景 | reference_context_item | 行为 |
|------|------------------------|------|
| 首轮 | None | 注入完整初始上下文 |
| 稳态 | 存在 | 仅注入差异更新项 |
| 压缩后 | 被清除 | 下轮重新注入完整初始上下文 |
| 回滚后 | 可能被清除 | 视情况重新注入 |

**设计要点**：
- 仅在上下文实际变化时才生成更新项，减少提示词冗余
- `build_initial_context()` 负责首轮完整注入
- `build_settings_update_items()` 负责稳态差异计算
- 压缩操作会清除参考上下文，强制下轮完整注入

### 5. 上下文压缩系统 (Compaction)

#### 压缩触发器

| 触发器 | 原因 | 阶段 |
|--------|------|------|
| Auto | Token 接近限制（`auto_compact_token_limit`） | PreTurn, MidTurn |
| Manual | 用户请求（`/compact` 命令） | StandaloneTurn |

#### 压缩策略选择

```
should_use_remote_compact_task()
      │
      ├─→ 提供商支持远程压缩? → 远程压缩
      │     ├─ RemoteCompactionV2 特性启用? → V2 远程压缩
      │     └─ 否则 → V1 远程压缩
      │
      └─→ 不支持? → 本地压缩
```

**本地压缩**：
- 运行预压缩 Hook（允许修改或中止压缩）
- 构建压缩提示词并发送给模型（使用 Responses API）
- 获取摘要后构建新历史（保留用户消息，插入摘要）
- 替换历史并更新版本号
- 清除参考上下文（强制下轮重新注入）
- 运行后压缩 Hook

**远程压缩**：
- 适用于支持压缩 API 的模型提供商
- 调用专用压缩 API 而非通用对话 API
- 压缩后同样清除参考上下文

#### 初始上下文注入策略

| 场景 | 策略 | 说明 |
|------|------|------|
| 轮前/手动压缩 | DoNotInject | 清除参考上下文，下轮重新注入 |
| 轮中压缩 | BeforeLastUserMessage | 在最后用户消息前注入上下文 |

**轮中压缩的特殊设计**：模型被训练为期望压缩摘要是历史中的最后一项，因此在替换历史中，初始上下文注入在最后一条用户消息之前。

#### 压缩后历史重建

压缩产生 `CompactedItem`，包含：
- `replacement_history`：替换后的完整历史
- `message`：压缩摘要文本

恢复会话时（Resume），通过 `rollout_reconstruction` 回放 `RolloutItem` 重建历史：
- 遇到 `CompactedItem` 时使用 `replacement_history` 替代之前的全部历史
- 压缩操作清除已存在的 `reference_context_item`
- 后续的 `TurnContextItem` 可重新建立参考基线

### 6. 轮次上下文 (TurnContext)

**职责**：包含单轮对话所需的所有配置和状态

**核心内容**：
- 模型信息与提供商（ModelInfo, SharedModelProvider）
- 环境配置（工作区、Shell、多环境支持）
- 权限配置（审批策略、沙箱策略、网络代理）
- 协作模式与个性
- 工具配置与特性开关
- 截断策略
- 技能加载结果
- 扩展数据

**与 TurnContextItem 的关系**：

`TurnContext` 是运行时结构，`TurnContextItem` 是其可序列化快照，用于：
- 持久化到 Rollout 日志
- 作为 `reference_context_item` 存储在 Session 状态中
- 恢复会话时重建差异计算基线

**关键方法**：

| 方法 | 职责 |
|------|------|
| `to_turn_context_item()` | 生成可序列化快照 |
| `with_model()` | 创建切换模型后的新 TurnContext |
| `model_context_window()` | 获取有效的上下文窗口大小 |

**设计要点**：
- 每个 Turn 创建一个新的 TurnContext 实例
- TurnContext 不包含对话历史（历史由 ContextManager 管理）
- TurnContext 通过 `Session.make_turn_context()` 工厂方法创建

### 7. 实时上下文 (Realtime Context)

**用途**：为实时模式构建启动上下文

**Token 预算分配**：

| 区域 | 预算 | 用途 |
|------|------|------|
| 当前线程 | 1,200 | 活跃线程中的最近消息 |
| 最近工作 | 2,200 | 按项目分组的最近线程摘要 |
| 工作区映射 | 1,600 | 目录树、文件结构 |
| 备注 | 300 | 上下文来源元数据 |

**设计要点**：
- 各区域独立截断，互不影响
- 优先保留当前线程和最近工作
- 从线程存储加载历史线程信息

### 8. 轮次边界管理 (Thread Rollout Truncation)

**用途**：基于用户轮次边界管理历史

**核心操作**：
- 识别用户消息边界位置（`is_user_turn_boundary()`）
- 应用回滚标记以反映有效历史
- 截断至最近 N 个分叉轮次

**用户轮次边界定义**：
- `role == "user"` 且内容不是 `contextual_user_message_content`
- `role == "assistant"` 且内容是 `inter_agent_instruction_content`（跨 Agent 指令）

**设计要点**：
- 回滚标记会影响边界计算
- `drop_last_n_user_turns()` 用于实现用户回滚操作
- 回滚时同步移除轮次前方的上下文更新消息

### 9. 初始上下文构建 (build_initial_context)

**职责**：为首轮或参考上下文缺失时构建完整上下文注入

**构建流程**：

```
build_initial_context(turn_context)
      │
      ├─→ developer_sections（聚合为单条 developer 消息）
      │     ├─ 模型切换指令
      │     ├─ 权限指令
      │     ├─ 开发者指令（AGENTS.md 等）
      │     ├─ 协作模式指令
      │     ├─ 实时模式指令
      │     ├─ 个性配置指令
      │     ├─ Apps 指令
      │     ├─ 技能指令
      │     ├─ 插件指令
      │     └─ 扩展贡献者指令
      │
      ├─→ separate_developer_sections（独立 developer 消息）
      │     └─ Guardian 策略提示（独立于聚合 bundle）
      │
      └─→ contextual_user_sections（聚合为单条 user 消息）
            ├─ 用户指令（AGENTS.md）
            └─ 环境上下文
```

**设计要点**：
- 多个 developer 段落聚合为一条消息，减少消息数量
- Guardian 策略提示作为独立 developer 消息，便于审计
- 环境上下文作为 contextual user 消息注入，支持差异计算
- 扩展系统可通过 `ContextContributor` 接口注入自定义上下文

## 数据流

### 正常轮次流程

```
用户输入
   ↓
创建 TurnContext（加载配置、模型信息、权限）
   ↓
构建初始上下文（首轮）或记录上下文更新（后续轮）
   ↓
记录用户消息，应用截断策略
   ↓
检查 Token 使用量，触发压缩（如需要）
   ↓
构建提示词（规范化历史、添加基础指令和工具）
   ↓
发送给模型，处理响应
   ↓
记录助手消息和工具输出
   ↓
更新 Token 信息和参考上下文
   ↓
发送轮次完成事件
```

### 压缩流程

```
触发检测（自动/手动/轮中）
   ↓
运行预压缩 Hook
   ↓
构建压缩提示词
   ↓
请求模型摘要（本地/远程）
   ↓
构建新历史（保留用户消息，插入摘要）
   ↓
替换历史，更新版本号和参考上下文
   ↓
重新计算 Token 使用量
   ↓
运行后压缩 Hook
   ↓
发送压缩事件
```

## 设计模式总结

### 1. 片段模式 (Fragment Pattern)

**目的**：类型安全的可识别上下文注入

**核心要素**：
- Trait 定义片段接口（角色、标记、内容）
- XML 标记识别已注入片段，支持后续过滤和差异计算
- `into()` 方法将片段转换为 `ResponseItem::Message`

### 2. 差异模式 (Diff Pattern)

**目的**：在多轮对话中最小化冗余上下文

**核心要素**：
- `reference_context_item` 存储上一轮的基准状态快照
- 稳态时 `build_settings_update_items()` 仅生成差异项
- 首轮或压缩后 `build_initial_context()` 完整注入
- 差异计算通过比较 `TurnContextItem` 字段实现

### 3. 规范化模式 (Normalization Pattern)

**目的**：确保发送给模型的历史满足不变量

**核心要素**：
- 在 `for_prompt()` 中执行规范化
- 调用/输出配对检查（FunctionCall、ToolSearch、CustomTool、LocalShell）
- 孤儿输出移除
- 模型不支持的内容类型剥离（图像）

### 4. Token 预算模式 (Token Budget Pattern)

**目的**：在上下文区域间分配 Token

**核心要素**：
- `TokenUsageInfo` 追踪使用量和上下文窗口
- `estimate_token_count()` 基于字节启发式估算
- `auto_compact_token_limit` 触发自动压缩
- 实时模式各区域独立预算分配

### 5. 版本控制模式 (Versioning Pattern)

**目的**：支持缓存失效和历史追踪

**核心要素**：
- `history_version` 在历史重写时递增
- 支持高效缓存失效判断
- 便于调试和状态追踪

### 6. 参考上下文基线模式 (Reference Context Baseline Pattern)

**目的**：支持差异计算和会话恢复

**核心要素**：
- 每轮结束存储 `TurnContextItem` 到 Rollout 日志
- 稳态时作为差异计算的基准
- 恢复会话时从 Rollout 回放重建基线
- 压缩或回滚操作可能清除基线

## 与 Laffybot 当前实现对比

### Laffybot 当前实现现状

| 功能 | Laffybot 现状 | Codex 方案 |
|------|--------------|-----------|
| 上下文构建 | ✅ SimpleContextBuilder | ContextManager + 片段系统 |
| Token 计数 | ✅ UsageBasedTokenCounter | 多策略 Token 估算 |
| 容量控制 | ✅ 基于用户-助手消息对截断 | Token 预算分配 + 区域独立截断 |
| 系统提示 | ✅ Jinja2 模板化 | 类型化片段注入 |
| 上下文压缩 | ❌ 未实现 | 多策略压缩系统 |
| 差异计算 | ❌ 未实现 | 参考上下文快照机制 |
| 历史规范化 | ❌ 未实现 | 不变量强制机制 |
| 版本控制 | ❌ 未实现 | 历史版本号机制 |

### 架构差异分析

**Laffybot 当前架构**：
- 单一 ContextBuilder 负责所有上下文构建
- 简单的历史截断策略（基于消息对）
- 无上下文差异计算机制
- 无历史规范化机制

**Codex 架构特点**：
- 分层架构：Session → ContextManager → Fragments → Compaction
- 多模式上下文注入（片段系统）
- 差异计算减少冗余
- 历史规范化保证不变量

## 对 Laffybot 的设计启示

### 高优先级借鉴

#### 1. 历史规范化机制

**借鉴价值**：高

**原因**：
- 当前 laffybot 缺少历史不变量检查
- 工具调用/输出配对问题可能导致模型错误
- 实现成本低，收益明显

**建议**：在 `ContextBuilder.build_messages` 前添加规范化步骤

#### 2. Token 预算分配

**借鉴价值**：高

**原因**：
- 当前简单截断策略可能丢失重要上下文
- 区域独立截断更灵活
- 实现成本中等

**建议**：为系统提示、历史消息、当前输入分配独立预算

### 中优先级借鉴

#### 3. 类型化片段系统

**借鉴价值**：中

**原因**：
- 当前 Jinja2 模板已满足基本需求
- 片段系统增加类型安全但复杂度较高
- 需评估收益与成本

**建议**：在需要动态上下文注入时考虑

#### 4. 版本控制机制

**借鉴价值**：中

**原因**：
- 支持缓存失效判断
- 便于调试和状态追踪
- 实现成本低

**建议**：在历史管理中添加版本号

### 低优先级借鉴

#### 5. 上下文压缩系统

**借鉴价值**：低（当前阶段）

**原因**：
- 实现复杂度高
- 需要模型支持摘要能力
- 当前简单截断在多数场景足够

**建议**：在长对话场景成为瓶颈时再考虑

#### 6. 差异计算机制

**借鉴价值**：低（当前阶段）

**原因**：
- Laffybot 上下文变化较少
- 实现复杂度较高
- 收益取决于上下文注入频率

**建议**：在实现类型化片段系统后再考虑

#### 7. 实时上下文模式

**借鉴价值**：低（当前阶段）

**原因**：
- 需要线程存储支持
- Laffybot 当前无此需求
- 实现成本高

**建议**：在需要跨会话上下文时考虑

## 设计决策建议

### 近期改进方向

1. **添加历史规范化**：在 `build_messages` 前检查工具调用/输出配对
2. **改进 Token 预算**：为不同上下文区域分配独立预算
3. **添加版本控制**：在历史修改时递增版本号

### 中期改进方向

1. **评估片段系统**：分析动态上下文注入需求
2. **改进压缩策略**：从简单截断升级为智能压缩

### 长期改进方向

1. **差异计算机制**：减少多轮对话中的冗余上下文
2. **实时上下文模式**：支持跨会话上下文共享

## 相关文档

- [会话管理](../../session-manager-design.md) - Laffybot 会话生命周期
- [上下文构建器](../../context-builder-design.md) - Laffybot 上下文构建
- [Agent Runner](../../agent-runner-streaming-design.md) - Laffybot Agent 执行
