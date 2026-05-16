# ContextBuilder 架构设计文档

> **文档范围说明**：本文档专注于 ContextBuilder 的架构设计、接口定义和核心职责。
> 
> **本文档不包含以下内容**：
> - 测试策略和测试用例（参见测试代码）
> - 性能监控和指标采集（参见运维文档）
> - 具体实现细节（参见源代码实现）

## 实现状态总览

| 功能模块 | 实现状态 | 实现文件 |
|---------|---------|----------|
| 核心接口定义 | ✅ 已实现 | `laffybot/context/base.py` |
| SimpleContextBuilder | ✅ 已实现 | `laffybot/context/builder.py` |
| Token 计数（近似） | ✅ 已实现 | `laffybot/context/tokens.py` → `ApproximateTokenCounter` |
| Token 计数（Usage） | ✅ 已实现 | `laffybot/context/tokens.py` → `UsageBasedTokenCounter` |
| 容量控制与截断 | ✅ 已实现 | `laffybot/context/builder.py` → `_apply_capacity_control` |
| 系统提示模板化 | ✅ 已实现 | `laffybot/context/templates.py` → `SystemPromptTemplate` |
| SessionManager 集成 | ✅ 已实现 | `laffybot/session/manager.py` → `_build_messages` |
| 记忆注入（Phase 2） | ✅ 已实现 | `laffybot/session/manager.py` → `_build_messages`（通过 `**extra_vars` 注入 `memories`） |
| Token 元数据持久化 | ✅ 已实现 | `laffybot/session/store.py` → `save_message` |
| 智能历史压缩 | ❌ 未实现 | 设计中，当前使用简单截断 |
| 知识库加载 | ❌ 未实现 | 设计中 |

## 概述

ContextBuilder 是 Laffybot 的上下文构建组件，负责将提示工程的复杂性集中在单一组件，构建 LLM 所需的完整上下文。

## 架构位置

```
┌─────────────────────────────────────────────────────┐
│                SessionManager                        │
│  ┌──────────────────────────────────────────────┐  │
│  │  1. 获取 Session                              │  │
│  │  2. 查询历史 → session.get_history()         │  │
│  │  3. 构建上下文 → ContextBuilder.build()      │  │  ← 本文档核心
│  │  4. 执行 LLM                                  │  │
│  │  5. 保存结果                                  │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**设计决策：**
- **职责分离**：存储层只关心消息的增删查改；构建层只关心如何组装 LLM 所需的完整上下文
- **可替换性**：调整提示策略不影响会话存储格式
- **可测试性**：可独立进行单元测试
- **无缓存策略**：每次请求都重新构建完整上下文，不实现上下文缓存机制（简化实现，避免缓存一致性复杂性）

## 核心职责

### 1. 系统提示管理
> **实现状态**: ✅ 已实现（模板化支持 + 记忆注入）| **参考**: `laffybot/context/templates.py`

- 身份定义 ✅
- 技能说明 ✅
- 记忆/知识库加载 ✅ 已实现（通过 `**extra_vars` → `memories` 变量注入模板）

**实现说明**：
- 使用 Jinja2 模板引擎支持动态系统提示
- 支持变量注入：`session_id`、`model`、`created_at`、`current_time`
- 支持自定义模板变量（通过 `ContextConfig.template_variables`）

### 2. 历史消息组装
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/builder.py:build_messages`

- 加载会话历史 ✅
- 应用容量控制 ✅
- 格式转换 ✅

### 3. 上下文构建
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/builder.py:build_messages`

- 合并系统提示、历史消息、当前输入 ✅
- 返回完整的消息列表 ✅

### 4. Token 计数与容量控制
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/tokens.py`, `laffybot/context/builder.py:_apply_capacity_control`

- 统计上下文 token 数量 ✅
- 应用容量限制策略 ✅
- 智能截断历史消息 ✅（基于用户-助手消息对的截断）

## 接口设计

### ContextBuilder 接口

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/base.py:ContextBuilder`

#### build_messages
构建完整的消息上下文。

**实际签名（已实现）：**
```python
async def build_messages(
    self,
    session_id: str,
    system_prompt: str | None,
    history: list[dict[str, Any]],
    current_message: str,
    model: str | None = None,
    created_at: datetime | None = None,
    **extra_vars: Any,
) -> list[dict[str, Any]]
```

**设计签名（原设计）：**
```python
def build_messages(
    self,
    session: Session,
    current_message: str,
) -> list[dict[str, Any]]
```

**差异说明**：实际实现将 `session` 对象拆分为多个参数，提高了灵活性，允许调用方按需传入历史消息。

**参数：**
- `session_id` - 会话标识符（用于模板变量）
- `system_prompt` - 系统提示（可选，可被会话覆盖）
- `history` - 历史消息列表
- `current_message` - 当前用户输入
- `model` - 模型名称（用于模板变量）
- `created_at` - 会话创建时间（用于模板变量）
- `**extra_vars` - 额外模板变量（如 `memories`），透传到系统提示模板渲染

**返回：** 完整的消息列表（系统提示 + 历史 + 当前消息）

**消息格式：**
```python
[
    {"role": "system", "content": "系统提示..."},
    {"role": "user", "content": "历史用户消息"},
    {"role": "assistant", "content": "历史助手回复"},
    ...
    {"role": "user", "content": "当前用户输入"}
]
```

### 构建流程

```
1. 加载系统提示
   ├─ 身份定义
   ├─ 技能说明
   └─ 记忆/知识库

2. 加载历史消息
   ├─ 调用 session.get_history()
   └─ 应用容量控制

3. 添加当前消息

4. Token 计数与容量控制
   ├─ 统计当前上下文 token 数
   ├─ 判断是否超出容量限制
   └─ 必要时截断历史消息

5. 返回完整上下文
```

## Token 计数策略

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/tokens.py`

### 设计原则

**核心决策：采用轻量级 token 计数方案，避免引入重量级依赖（如 tiktoken）。** ✅ 已实现

这一决策基于以下考量：
- 减少外部依赖，降低部署复杂度
- 容量控制不需要精确 token 数，近似值足够用于决策
- Provider 返回的 usage 信息可提供精确数据（优先使用）

### 计数方法

#### 方法一：Provider Usage 信息（优先）

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/tokens.py:UsageBasedTokenCounter`

**数据来源：** `LLMResponse.usage` 字段

**实现方式：**
1. **消息存储时记录 token 数** ✅
   - 在 `SessionStore.save_message()` 时，从 `LLMResponse.usage` 提取 token 数
   - 存储格式：在消息元数据中添加 `input_tokens` 和 `output_tokens` 字段
   - **实现参考**: `laffybot/session/store.py:save_message` 接受 `input_tokens` 和 `output_tokens` 参数
   - **数据库字段**: `messages` 表包含 `input_tokens INTEGER` 和 `output_tokens INTEGER` 列
   - 示例：`{"role": "assistant", "content": "...", "input_tokens": 150, "output_tokens": 80}`

2. **历史消息 token 统计** ✅
   - 遍历历史消息，累加 `input_tokens` 和 `output_tokens` 字段
   - 对于缺失 token 信息的消息，使用近似计算补充
   - **实现参考**: `laffybot/context/tokens.py:UsageBasedTokenCounter.count_message_tokens`

3. **当前消息 token 估算** ✅
   - 当前用户消息：使用近似计算（尚未发送给 LLM）
   - 系统提示：使用近似计算（静态内容可预计算并缓存）

**Usage 字段结构：**
- `prompt_tokens`：输入 token 数
- `completion_tokens`：输出 token 数
- `total_tokens`：总 token 数

**消息元数据扩展：**
在消息中添加 `input_tokens` 和 `output_tokens` 字段，用于历史消息的 token 统计

#### 方法二：近似计算（后备）

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/tokens.py:ApproximateTokenCounter`

**适用场景：**
- Provider 不返回 usage 信息
- 消息历史中缺失 token 记录
- 当前用户消息（尚未发送）

**计算规则：** ✅ 已实现
- **英文/拉丁语系**：`tokens ≈ char_count / 4`（基于英文平均 token 长度）
- **中文/非拉丁语系**：`tokens ≈ char_count / 2`（更保守估算）
- **混合内容**：检测主要语言后选择对应系数

**语言检测策略：** ✅ 已实现
- 使用正则表达式检测 CJK 字符范围：`\u4e00-\u9fff`（中文）、`\u3040-\u30ff`（日文）、`\uac00-\ud7af`（韩文）
- 按字符比例加权计算 token 数
- **实现参考**: `laffybot/context/tokens.py:ApproximateTokenCounter.CJK_PATTERN`

**注意事项：**
- 近似计算仅用于容量控制决策，不保证精确性
- 不用于计费或精确的 token 统计报告
- 保守估算可能导致提前截断，但可避免超出上下文限制

### 容量控制策略

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/builder.py:_apply_capacity_control`

**配置参数：** ✅ 已实现（`laffybot/config.py:ContextConfig`）
- `max_tokens: int | None` - 上下文最大 token 数量（包含系统提示、历史和当前消息）
- `max_messages: int | None` - 历史消息最大数量限制
- `min_preserve_pairs: int` - 最小保留用户-助手消息对数（默认 3）

**截断策略：** ✅ 已实现
- 始终保留系统提示和当前用户消息
- 从最旧的历史消息开始截断（按用户-助手消息对移除）
- 支持配置最小保留消息数（确保对话连贯性）

**决策流程：** ✅ 已实现
```
1. 检查当前上下文 token 数
2. 若超出 max_tokens：
   a. 移除最旧的用户-助手消息对
   b. 重新计算 token 数
   c. 重复直到满足容量限制或达到最小保留数
3. 若超出 max_messages：
   a. 移除最旧的用户-助手消息对
   b. 重复直到满足消息数量限制
```

## 设计优势

### 单一职责
只关心如何组装 LLM 所需的完整上下文，不涉及存储和执行逻辑。

### 可替换性
- 更换存储后端不影响提示构建逻辑
- 调整提示策略不影响会话存储格式
- 支持不同的提示模板和策略

### 可测试性
可独立进行单元测试，验证：
- 系统提示正确加载
- 历史消息正确组装
- 容量控制正确应用
- 输出格式符合预期

### 便于维护
提示工程的复杂性集中管理：
- 便于版本控制
- 支持 A/B 测试
- 易于调试和优化

## 扩展点

### 系统提示来源
- 静态配置文件 ✅（通过 `ContextConfig.system_prompt`）
- 动态数据库加载 ❌（设计中）
- 外部 API 获取 ❌（设计中）

### 系统提示模板化

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/context/templates.py:SystemPromptTemplate`

**模板引擎支持：** ✅ 已实现
- 支持 Jinja2 模板语法
- 模板变量使用双花括号语法：`{{ variable }}`
- 支持条件分支和循环逻辑

**动态变量注入：** ✅ 已实现
- 会话级变量：`session_id`、`model`、`created_at` ✅
- 环境变量：`current_time` ✅
- 记忆变量：`memories`（由 SessionManager 注入，含 memory_id、content、tags、session_title）✅
- 自定义变量：通过 `ContextConfig.template_variables` 注入 ✅
- 用户级变量：`user_id`、`user_name` ❌（设计中）

**模板来源：**
- 内嵌字符串模板 ✅（通过 `ContextConfig.system_prompt_template`）
- 外部模板文件 ❌（设计中）
- 数据库存储的模板 ❌（设计中）

**模板渲染流程：** ✅ 已实现
```
1. 加载模板定义
2. 收集变量上下文
3. 渲染模板
4. 缓存渲染结果（可选）❌ 未实现缓存
```

### 智能历史压缩

> **实现状态**: ❌ 未实现 | **当前行为**: 简单截断最旧消息对

**设计目标：**
在容量限制下，优先保留关键信息，而非简单截断最旧消息。

**当前实现说明**：
- 当前使用简单的 FIFO 截断策略
- 按"用户-助手消息对"为单位移除最旧历史
- 保证 `min_preserve_pairs` 数量的最近对话不被截断
- **参考**: `laffybot/context/builder.py:_apply_capacity_control`

#### 压缩配置

**触发条件配置：**
- `trigger_threshold`：容量使用率阈值（默认 0.8，即 80%）❌ 未实现
- `min_preserve_pairs`：最少保留对话轮数（默认 3 轮，即 6 条消息）✅ 已实现

**压缩策略配置：**
- `preserve_recent_messages`：完整保留的最近消息数（默认 6 条）❌ 未实现
- `compression_ratio`：压缩目标比例（默认 0.3，即压缩至原大小的 30%）❌ 未实现

**关键信息识别配置：**
- `preserve_tool_calls`：是否保留工具调用及结果（默认 True）❌ 未实现
- `preserve_errors`：是否保留错误和重试记录（默认 True）❌ 未实现
- `preserve_decisions`：是否保留用户决策确认（默认 True）❌ 未实现

#### 压缩策略详解

**策略一：关键信息识别与保留** ❌ 未实现

消息优先级分类：
- **高优先级（必须保留）**：
  - 工具调用及其结果（包含重要状态信息）
  - 错误和重试记录（调试和问题追踪）
  - 用户决策确认（明确的关键选择）
  - 最近 N 条消息（保持对话连贯性）

- **中优先级（摘要保留）**：
  - 常规对话内容
  - 信息查询和回复
  - 状态更新通知

- **低优先级（可移除）**：
  - 闲聊和寒暄
  - 重复性问题
  - 已被后续消息替代的过时信息

**策略二：分层压缩** ❌ 未实现

```
完整上下文结构：
┌─────────────────────────────────────┐
│ 系统提示（始终保留）                  │  ✅ 已实现
├─────────────────────────────────────┤
│ 最近 N 条消息（完整保留）             │  ❌ 未实现 ← preserve_recent_messages
├─────────────────────────────────────┤
│ 关键信息消息（完整保留）              │  ❌ 未实现 ← 工具调用、错误、决策
├─────────────────────────────────────┤
│ 中间历史消息（摘要压缩）              │  ❌ 未实现 ← 压缩为摘要形式
├─────────────────────────────────────┤
│ 最旧历史消息（完全移除）              │  ✅ 已实现 ← 当前截断策略
├─────────────────────────────────────┤
│ 当前用户消息（始终保留）              │  ✅ 已实现
└─────────────────────────────────────┘
```

**策略三：摘要生成** ❌ 未实现

摘要生成方式：
- **规则提取**（轻量级）：提取关键实体、时间、状态变化 ❌ 未实现
- **LLM 摘要**（可选）：使用 LLM 生成语义摘要（需额外调用）❌ 未实现

摘要消息格式：
- `role`：使用 "system" 标识摘要消息
- `content`：摘要文本内容，以 "[摘要]" 前缀标识
- `is_summary`：标记为摘要消息
- `summarized_messages`：被摘要的消息数量
- `key_entities`：提取的关键实体列表

#### 压缩触发条件 ❌ 未实现

**触发条件一：容量阈值** ❌ 未实现
```
当前 token 数 / max_tokens > trigger_threshold (默认 0.8)
```

**触发条件二：消息数量限制** ✅ 已实现
```
历史消息数 > max_messages
```
**实现参考**: `laffybot/context/builder.py:_exceeds_message_limit`

**触发条件三：冗余检测**（可选）
- 连续多轮相似问题
- 重复的查询操作
- 可合并的状态更新

#### 压缩执行流程 ❌ 未实现（当前仅实现简单截断）

```
1. 检查触发条件 ✅（简单截断已实现）
   ├─ 若未触发，返回原始消息列表 ✅
   └─ 若触发，进入压缩流程 ✅（简单截断）

2. 分类消息 ❌（未实现，当前直接按顺序截断）
   ├─ 识别高优先级消息（工具调用、错误、决策）❌
   ├─ 识别低优先级消息（闲聊、重复）❌
   └─ 标记最近 N 条消息为保留 ❌

3. 计算压缩目标 ❌
   ├─ 目标 token 数 = 当前 token 数 × compression_ratio ❌
   └─ 确保保留消息数 >= min_preserve_pairs × 2 ✅

4. 执行压缩 ✅（简单截断）
   ├─ 完整保留：高优先级 + 最近 N 条 ❌
   ├─ 摘要压缩：中间历史消息 ❌
   └─ 完全移除：低优先级 + 最旧消息 ✅（当前实现）

5. 验证压缩结果 ✅
   ├─ 检查 token 数是否满足目标 ✅
   ├─ 检查保留消息数是否满足最小要求 ✅
   └─ 返回压缩后的消息列表 ✅
```

#### 压缩效果评估

**评估指标：**
- Token 压缩率：`(原始 token - 压缩后 token) / 原始 token`
- 信息保留度：关键信息是否完整保留
- 对话连贯性：最近对话是否完整

**评估方式：**
- 单元测试验证压缩逻辑
- 集成测试验证对话质量
- 用户反馈评估实际效果

> **设计约束**：本项目不支持多模态内容（图片、音频等），上下文仅处理纯文本消息。

> **设计约束**：除非明确要求，不实现任何降级策略。上下文构建失败时直接抛出异常，由上层（SessionManager）统一处理错误。

> **范围说明**：本计划不包含可观测性增强（如上下文构建日志、调试导出等），该部分属于运维监控范畴。

## 与 SessionManager 协作

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/session/manager.py:_build_messages`

SessionManager 在执行流程中调用 ContextBuilder：

```
SessionManager.send_message()
    ├─ 获取 Session
    ├─ 查询历史（session.get_history()）
    ├─ 构建上下文（context_builder.build_messages()）  ← ContextBuilder ✅
    ├─ 执行 LLM（AgentRunner.run_stream()）
    └─ 保存结果（session.save()）
```

**协作契约：** ✅ 已实现
- SessionManager 提供 Session 对象和当前消息
- ContextBuilder 返回完整的消息列表
- 双方通过清晰接口协作，互不依赖内部实现

**实现细节：**
- `SessionManager.__init__` 接受可选的 `context_builder` 参数（依赖注入）
- 默认使用 `SimpleContextBuilder` 实例
- `_build_messages` 方法委托给 `self._context_builder.build_messages()`

## 实现路径

### 当前状态

> **状态**: ✅ 已完成阶段 1-3

上下文构建逻辑已从 `SessionManager._build_messages()` 提取至独立的 `SimpleContextBuilder` 类。

### 提取计划

**阶段 1：接口设计与依赖注入** ✅ 已完成
- 定义 `ContextBuilder` 抽象接口 ✅ (`laffybot/context/base.py`)
- 将现有逻辑迁移至 `SimpleContextBuilder` 实现 ✅ (`laffybot/context/builder.py`)
- SessionManager 通过依赖注入使用 ContextBuilder ✅

**阶段 2：容量控制实现** ✅ 已完成
- 实现 token 计数逻辑（优先使用 usage，后备近似计算）✅
- 实现容量控制策略（max_tokens、max_messages）✅
- 实现智能截断逻辑 ✅

**阶段 3：系统提示增强** ✅ 已完成
- 支持模板化系统提示 ✅
- 支持动态变量注入 ✅
- 支持多来源加载策略 ⚠️（仅支持静态配置，动态加载未实现）

**阶段 4：智能历史压缩** ❌ 未实现
- 实现语义摘要压缩策略 ❌
- 实现关键信息提取与保留 ❌
- 实现分层压缩（完整保留 / 摘要 / 移除）❌

**迁移策略：** ✅ 已采用
- 全面迁移：直接替换现有实现，不保持向后兼容 ✅
- 渐进式迁移：先提取，后增强 ✅
- 配置驱动：通过配置切换不同的 ContextBuilder 实现 ✅（支持依赖注入）
