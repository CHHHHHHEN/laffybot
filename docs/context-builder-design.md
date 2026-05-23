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
| 核心接口定义 | ✅ 已实现 | `laffybot/service/context/base.py` |
| SimpleContextBuilder | ✅ 已实现 | `laffybot/service/context/builder.py` |
| Token 计数（近似） | ✅ 已实现 | `laffybot/service/context/tokens.py` → `ApproximateTokenCounter` |
| Token 计数（Usage） | ✅ 已实现 | `laffybot/service/context/tokens.py` → `UsageBasedTokenCounter` |
| 容量控制与截断 | ✅ 已实现 | `laffybot/service/context/builder.py` → `_apply_capacity_control` |
| 系统提示模板化 | ✅ 已实现 | `laffybot/service/context/templates.py` → `SystemPromptTemplate` |
| SessionManager 集成 | ✅ 已实现 | `laffybot/service/manager.py` → `_build_messages` |
| 记忆注入（Phase 2） | ✅ 已实现 | `laffybot/service/manager.py` → `_build_messages`（通过 `**extra_vars` 注入 `memories`） |
| Token 元数据持久化 | ✅ 已实现 | `laffybot/db/session_store.py` → `save_message` |
| 智能历史压缩 | ✅ 已实现 | `laffybot/service/context/compressor.py` → 工具输出裁剪 + 压缩检测 + LLM 摘要 |
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
> **实现状态**: ✅ 已实现（模板化支持 + 记忆注入）| **参考**: `laffybot/service/context/templates.py`

- 身份定义 ✅
- 技能说明 ✅
- 记忆/知识库加载 ✅ 已实现（通过 `**extra_vars` → `memories` 变量注入模板）

**实现说明**：
- 使用 Jinja2 模板引擎支持动态系统提示
- 支持变量注入：`session_id`、`model`、`created_at`、`current_time`
- 支持自定义模板变量（通过 `ContextConfig.template_variables`）

### 2. 历史消息组装
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/builder.py:build_messages`

- 加载会话历史 ✅
- 应用容量控制 ✅
- 格式转换 ✅

### 3. 上下文构建
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/builder.py:build_messages`

- 合并系统提示、历史消息、当前输入 ✅
- 返回完整的消息列表 ✅

### 4. Token 计数与容量控制
> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/tokens.py`, `laffybot/service/context/builder.py:_apply_capacity_control`

- 统计上下文 token 数量 ✅
- 应用容量限制策略 ✅
- 智能截断历史消息 ✅（基于用户-助手消息对的截断）

## 接口设计

### ContextBuilder 接口

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/base.py:ContextBuilder`

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

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/tokens.py`

### 设计原则

**核心决策：采用轻量级 token 计数方案，避免引入重量级依赖（如 tiktoken）。** ✅ 已实现

这一决策基于以下考量：
- 减少外部依赖，降低部署复杂度
- 容量控制不需要精确 token 数，近似值足够用于决策
- Provider 返回的 usage 信息可提供精确数据（优先使用）

### 计数方法

#### 方法一：Provider Usage 信息（优先）

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/tokens.py:UsageBasedTokenCounter`

**数据来源：** `LLMResponse.usage` 字段

**实现方式：**
1. **消息存储时记录 token 数** ✅
   - 在 `SessionStore.save_message()` 时，从 `LLMResponse.usage` 提取 token 数
   - 存储格式：在消息元数据中添加 `input_tokens` 和 `output_tokens` 字段
   - **实现参考**: `laffybot/db/session_store.py:save_message` 接受 `input_tokens` 和 `output_tokens` 参数
   - **数据库字段**: `messages` 表包含 `input_tokens INTEGER` 和 `output_tokens INTEGER` 列
   - 示例：`{"role": "assistant", "content": "...", "input_tokens": 150, "output_tokens": 80}`

2. **历史消息 token 统计** ✅
   - 遍历历史消息，累加 `input_tokens` 和 `output_tokens` 字段
   - 对于缺失 token 信息的消息，使用近似计算补充
   - **实现参考**: `laffybot/service/context/tokens.py:UsageBasedTokenCounter.count_message_tokens`

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

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/tokens.py:ApproximateTokenCounter`

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
- **实现参考**: `laffybot/service/context/tokens.py:ApproximateTokenCounter.CJK_PATTERN`

**注意事项：**
- 近似计算仅用于容量控制决策，不保证精确性
- 不用于计费或精确的 token 统计报告
- 保守估算可能导致提前截断，但可避免超出上下文限制

### 容量控制策略

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/builder.py:_apply_capacity_control`, `laffybot/service/context/compressor.py`

**配置参数：** ✅ 已实现（`laffybot/config.py:ContextConfig`）
- `max_tokens: int | None` - 上下文最大 token 数量（包含系统提示、历史和当前消息）
- `max_messages: int | None` - 历史消息最大数量限制
- `enable_compression: bool` - 全局压缩开关（默认开启）
- `compress_threshold_ratio: float` - token 使用率阈值（默认 0.8）
- `compress_preserve_pairs: int` - 完整保留的最近消息对数（默认 3）
- `compress_tool_output_max_chars: int` - 工具输出最大字符数（默认 2000）

**容量控制策略：** ✅ 已实现
- 始终保留系统提示和当前用户消息
- 阶段 0：工具输出裁剪（同步）—— 裁剪过长工具输出
- 阶段 1：压缩检测（同步）—— 检测是否需要语义压缩
- 不再执行 FIFO 截断，压缩失败时保持原始历史不变

**决策流程：** ✅ 已实现
```
1. 工具输出裁剪（prune_tool_outputs）
2. 压缩检测（CompressionDetector.detect）
3. 若区域可压缩 → 返回 RegionInfo，由 SessionManager 异步执行 LLM 摘要
4. 压缩结果不影响当前轮，下轮生效
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

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/templates.py:SystemPromptTemplate`

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

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/context/compressor.py`

**设计目标：**
在容量限制下，将早期历史消息压缩为摘要，替代 FIFO 粗暴移除策略。保留关键信息的同时延长对话有效轮数。

**实现架构**：

系统提供两层防御：

1. **工具输出裁剪（Pruning）**：同步裁剪工具消息的过长输出内容
2. **语义摘要压缩（Compaction）**：异步调用 LLM 生成历史摘要

```
阶段〇（同步，_apply_capacity_control 入口）：
   prune_tool_outputs(messages) → pruned_messages
   裁剪历史中工具消息的过长输出内容

阶段一（同步，CompressionDetector）：
   detect(pruned_messages) → RegionInfo | None
   检查是否需要压缩，标记可压缩区域

阶段二（异步，SessionManager 内，与主 LLM 请求并发）：
   LLMSummarizer.summarize(messages_in_region) → summary_text
   发起非流式 LLM 摘要请求

阶段三（异步，摘要完成后）：
   store.replace_compressed_region(session_id, region_info, summary_text)
   用摘要消息替换被压缩的消息
```

**关键设计决策：**
- 工具输出裁剪（同步）在 `_apply_capacity_control` 入口执行，先裁剪再检测
- 裁剪只修改消息内容，不涉及存储写入
- 压缩检测（同步）在 `SimpleContextBuilder` 中，不引入 Provider 依赖
- LLM 摘要（异步）在 `SessionManager` 中，复用已创建的 Provider
- 摘要结果不影响当前轮，下轮构建消息时读取到的是替换后的历史
- 压缩失败时保持原始历史不变，后续请求重新评估

**实现组件**：

| 组件 | 文件 | 职责 |
|------|------|------|
| `ToolOutputPruner` | `compressor.py` | 同步裁剪工具消息输出内容至 `compress_tool_output_max_chars` |
| `CompressionDetector` | `compressor.py` | 同步检测是否需要压缩，返回 `RegionInfo` |
| `LLMSummarizer` | `compressor.py` | 接收 Provider + model，调用非流式 `chat_completion` 生成结构化摘要 |
| `RegionInfo` | `types.py` | 数据类，包含可压缩消息 ID 列表和 token 占比 |

**配置参数（ContextConfig）：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_compression` | bool | true | 全局开关 |
| `compress_threshold_ratio` | float | 0.8 | token 使用率超此阈值触发 |
| `compress_preserve_pairs` | int | 3 | 压缩时完整保留的最近消息对数 |
| `compress_preserve_recent_tokens` | int | 动态预算 | 尾轮保留的 token 预算上限 |
| `compress_reserved_tokens` | int | 20000 | 压缩预留 buffer |
| `compress_max_summary_tokens` | int | 512 | 摘要消息预留的 token 预算 |
| `compress_model` | str | None | 摘要专用模型，None 时复用会话模型 |
| `compress_tool_output_max_chars` | int | 2000 | Pruning 阶段工具输出最大字符数 |
| `compress_protected_tools` | list[str] | ["skill"] | 受保护的工具类型 |

**摘要 prompt 结构**：
```
Goal: <原始目标>
Constraints & Preferences: <约束和偏好>
Progress: <已完成 / 进行中 / 阻塞>
Key Decisions: <关键决策>
Next Steps: <下一步计划>
Critical Context: <关键上下文信息>
Relevant Files: <相关文件列表>
```

**存储层扩展**：
- `get_messages_by_ids(session_id, message_ids)` → 返回指定 ID 的消息列表
- `replace_compressed_region(session_id, message_ids, summary_text)` → 单事务原子替换
- 摘要消息 role="assistant"，metadata 包含 `{"is_summary": true, "summarized_count": N}`
- 摘要消息不计入 `user_message_count`

**错误处理**：
- 所有压缩错误路径均不抛出异常
- 压缩失败时当前轮消息可能超出上下文窗口——由 Provider 返回的错误在上层统一转换

## 与 SessionManager 协作

> **实现状态**: ✅ 已实现 | **参考**: `laffybot/service/manager.py:_build_messages`

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
- 定义 `ContextBuilder` 抽象接口 ✅ (`laffybot/service/context/base.py`)
- 将现有逻辑迁移至 `SimpleContextBuilder` 实现 ✅ (`laffybot/service/context/builder.py`)
- SessionManager 通过依赖注入使用 ContextBuilder ✅

**阶段 2：容量控制实现** ✅ 已完成
- 实现 token 计数逻辑（优先使用 usage，后备近似计算）✅
- 实现容量控制策略（max_tokens、max_messages）✅
- 实现智能截断逻辑 ✅

**阶段 3：系统提示增强** ✅ 已完成
- 支持模板化系统提示 ✅
- 支持动态变量注入 ✅
- 支持多来源加载策略 ⚠️（仅支持静态配置，动态加载未实现）

**阶段 4：智能历史压缩** ✅ 已实现
- 实现工具输出裁剪（ToolOutputPruner）✅
- 实现压缩检测（CompressionDetector）✅
- 实现 LLM 摘要压缩（LLMSummarizer）✅
- 存储层扩展（get_messages_by_ids, replace_compressed_region）✅
- SessionManager 并发摘要任务 ✅

**迁移策略：** ✅ 已采用
- 全面迁移：直接替换现有实现，不保持向后兼容 ✅
- 渐进式迁移：先提取，后增强 ✅
- 配置驱动：通过配置切换不同的 ContextBuilder 实现 ✅（支持依赖注入）

Implementation record: see `docs/archive/context-compression-2026-05-16.md`
