# 上下文压缩方案

## 设计目标

在容量限制下，将早期历史消息压缩为摘要，彻底替代当前 FIFO 粗暴移除策略。保留关键信息的同时延长对话有效轮数。

**非目标**：
- 不引入远程压缩 API（仅本地模型摘要）
- 不实现差异计算/参考上下文快照
- 不实现实时上下文模式
- 不修改消息存储 Schema

## 架构概述

系统提供**两层防御**：工具输出裁剪（Pruning）和语义摘要压缩（Compaction），在压缩前先裁剪独立工具输出的冗余内容，减少需压缩的数据量。

```
阶段〇（同步，_apply_capacity_control 入口）：
   prune_tool_outputs(messages) → pruned_messages
   职责：裁剪历史中工具消息的过长输出内容
   触发条件：工具消息输出超过字符限制
   不执行 LLM 调用

阶段一（同步，SimpleContextBuilder 内）：
   detect_compressible_region(pruned_messages) → region_info | None
   职责：检查是否需要压缩，标记可压缩区域
   触发条件：token 使用率 > threshold 且存在 compressible region
   不执行 LLM 调用

阶段二（异步，SessionManager 内，与主 LLM 请求并发）：
   LLMSummarizer.summarize(messages_in_region) → summary_text
   职责：发起非流式 LLM 摘要请求
   不阻塞主流程，结果用于替换存储中的原始消息

阶段三（异步，摘要完成后）：
   store.replace_compressed_region(session_id, region_info, summary_text)
   职责：用摘要消息替换被压缩的消息
   不影响当前轮的消息构建（下轮生效）
```

数据流：

```
_build_messages
  └─ _apply_capacity_control
       ├─ prune_tool_outputs (sync)
       │    裁剪工具消息输出至 TOOL_OUTPUT_MAX_CHARS
       └─ detect_compressible_region (sync)
            检测是否需要压缩，返回 region_info

send_message
  ├─ save user message
  ├─ messages, region_info = await _build_messages(...)  ← 返回 region_info
  ├─ create Provider
  ├─ if region_info is not None:
  │     asyncio.create_task(fire LLM summary)  ← 并发，不等待
  ├─ run main agent flow
  └─ when summary completes:
        store.replace_compressed_region()       ← 替换历史
```

**关键决策**：
- 工具输出裁剪（同步）在 `_apply_capacity_control` 入口执行，先裁剪再检测
- 裁剪只修改消息内容，不删除消息，不涉及存储写入
- 压缩检测（同步）在 `SimpleContextBuilder` 中，不引入 Provider 依赖
- LLM 摘要执行（异步）在 `SessionManager` 中，复用已创建的 Provider
- 摘要结果不影响当前轮，下轮构建消息时读取到的是替换后的历史
- 启用后压缩替代 FIFO 截断；压缩失败时保持原始历史不变，后续请求重新评估
- `ContextBuilder` 抽象接口新增 `RegionInfo` 类型依赖，签名调整为返回 `tuple`

## 组件分解

### 1. CompressionDetector（压缩检测器）

```
CompressionDetector
├── detect(messages) → RegionInfo | None  # 检查是否满足触发条件，标记可压缩区域
└── config                                # 压缩配置
```

单一职责：同步检查消息列表，判断是否需要压缩，返回可压缩区域信息（消息 ID 列表、消息数量）。纯函数，无存储感知，无 LLM 调用。

`RegionInfo` 包含：compressible 消息的 ID 列表、token 占比。

### 2. ToolOutputPruner（工具输出裁剪器）

```
ToolOutputPruner
├── prune(messages) → list[dict]        # 同步裁剪工具消息输出内容
├── config                              # 裁剪配置（最大字符数、受保护工具）
```

单一职责：同步扫描消息列表，对工具调用结果（tool/function role 消息）的 content 进行字符截断。纯函数，无存储感知，无 LLM 调用。

裁剪策略：
- 只在 `content` 字符数超过 `TOOL_OUTPUT_MAX_CHARS` 时执行截断
- 截断后追加 `"\n... (truncated, original N chars)"` 标记
- 不裁剪系统提示、用户消息或助手消息中的代码输出
- 受保护的工具类型（如 `skill`）不做裁剪
- 裁剪在内存中进行，不修改持久化消息

### 3. LLMSummarizer（摘要执行器）

```
LLMSummarizer
├── __init__(provider, model)            # 注入 Provider 和模型
├── summarize(messages) → str            # 发起非流式 LLM 摘要请求，返回摘要文本
```

单一职责：接收消息列表，调用 LLM 生成摘要文本。不感知存储、不关心消息列表来源。`summarize()` 不抛出异常，失败时返回空字符串。

**摘要 prompt 设计**：

固定结构模板：
```
Goal: <原始目标>
Constraints & Preferences: <约束和偏好>
Progress: <已完成 / 进行中 / 阻塞>
Key Decisions: <关键决策>
Next Steps: <下一步计划>
Critical Context: <关键上下文信息>
Relevant Files: <相关文件列表>
```

设计要点：
- 保持模板结构不变，使用简洁要点而非段落
- 要求模型以保留关键事实、工具结果、用户决策为主要目标
- 不含角色注入或系统级指令

**摘要消息再压缩**：允许。摘要消息在后续轮次中与其他消息同等参与 compressible 区域计算。

**不出现在设计中**：
- 不做摘要质量验证（信任 LLM 输出）
- 不使用流式 API（摘要场景非流式足够）

### 4. 压缩配置

扩展 `ContextConfig`，新增字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_compression` | bool | true | 全局开关，默认开启 |
| `compress_threshold_ratio` | float | 0.8 | token 使用率超此阈值触发 |
| `compress_preserve_pairs` | int | 3 | 压缩时完整保留的最近消息对数 |
| `compress_preserve_recent_tokens` | int | 动态预算 | 尾轮保留的 token 预算上限，防止单轮超大消息耗尽预算 |
| `compress_reserved_tokens` | int | 20000 | 压缩预留 buffer，防止压缩执行过程中自身触发溢出 |
| `compress_max_summary_tokens` | int | 512 | 摘要消息预留的 token 预算 |
| `compress_model` | str \| None | None | 摘要专用模型，None 时复用会话模型 |
| `compress_tool_output_max_chars` | int | 2000 | Pruning 阶段工具输出最大字符数，超出部分裁剪 |
| `compress_protected_tools` | list[str] | `["skill"]` | 受保护的工具类型，其输出不参与裁剪 |

### 5. 关键常量

| 常量 | 值 | 用途 |
|------|-----|------|
| `TOOL_OUTPUT_MAX_CHARS` | 2,000 | Pruning 时工具输出的最大字符数（超出裁剪） |
| `MIN_PRESERVE_RECENT_TOKENS` | 2,000 | 尾轮保留预算下限 |
| `MAX_PRESERVE_RECENT_TOKENS` | 8,000 | 尾轮保留预算上限 |
| `COMPRESS_RESERVED_BUFFER` | 20,000 | 压缩预留 buffer，防止压缩过程中触发溢出 |

### 6. 存储层扩展（压缩摘要持久化）

**职责**：持久化压缩摘要，替换被压缩的原始消息。

在 LLM 摘要完成后，由异步任务调用 store 方法以单事务原子替换：

```
store.get_messages_by_ids(session_id, message_ids) → list[dict]

store.replace_compressed_region(session_id, message_ids, summary_text) → bool
```

- 单事务：DELETE 被压缩的消息 + INSERT 一条摘要消息
- 摘要消息 role="assistant"，metadata 中添加 `{"is_summary": true, "summarized_count": N}`
- 摘要消息不计入 `user_message_count`，避免影响标题生成和统计
- `message_count` 同步按净变化更新，保持会话总消息数一致
- 摘要消息的 timestamp 设为被压缩消息中最新的一条，确保时间线连续
- 返回 bool 表示是否成功（失败可能是 session 已删除）

**不出现在设计中**：不要求原地修改、不记录被压缩消息的原文。

## 集成点

### SimpleContextBuilder 修改

在 `build_messages` 返回值中附加压缩检测结果。方式：新增可选返回值字段 `region_info`，类型 `RegionInfo | None`。

```
build_messages
  ├─ 渲染系统提示
  ├─ 添加历史消息
  ├─ 添加当前消息
  └─ _apply_capacity_control
      ├─ prune_tool_outputs(messages)
      ├─ CompressionDetector.detect() → region_info | None
      │   始终保留：系统提示 + 最近 compress_preserve_pairs 对
      └─ 返回 (messages, region_info)
```

**设计要点**：
- `_apply_capacity_control` 移除旧 FIFO 截断逻辑，改为仅执行 pruning + detection，返回 `tuple[list[dict], RegionInfo | None]`
- `build_messages` 返回类型也相应调整
- `ContextBuilder` 抽象接口签名同步更新（新增 `RegionInfo` 类型依赖）
- `session_manager._build_messages()` 接收 region_info 并透传给 `send_message`

**不引入**：
- 不恢复 FIFO 截断作为保底
- 不修改 `ContextBuilder` 核心职责（仍为消息组装 + 容量控制）
- 不引入 Provider 依赖

### SessionManager 修改

在 `send_message` 流程中，LLM 摘要执行作为并发任务：

```
send_message
  ├─ save user message
  ├─ messages, region_info = await _build_messages(...)  ← 返回 region_info
  ├─ create Provider
  ├─ if region_info is not None:
  │     summarizer = LLMSummarizer(provider, compress_model or session.model_name)
  │     asyncio.create_task(
  │         _fire_summary_and_replace(session_id, region_info, summarizer)
  │     )
  ├─ create AgentRunner(provider)
  ├─ run main agent flow
  └─ ...

_fire_summary_and_replace(session_id, region_info, summarizer):
  ├─ messages = store.get_messages_by_ids(session_id, region_info.message_ids)
  ├─ summary = await summarizer.summarize(messages)
  ├─ if summary:
  │     store.replace_compressed_region(session_id, region_info.message_ids, summary)
  └─ (异常被函数内部捕获，WARNING 日志)
```

**设计要点**：
- `asyncio.create_task` 启动的异步任务在事件循环中运行，不阻塞主流程
- `_fire_summary_and_replace` 内部捕获所有异常，确保不传播
- `region_info` 包含消息 ID 列表，而非索引，避免并发插入导致索引偏移
- 若并发摘要完成前用户发了新消息，`replace_compressed_region` 的事务只替换 region 内的消息，不影响新消息

**不引入**：
- 不修改 SSE 事件流
- 不修改 `SessionManager.send_message` 的异常处理路径

### ContextConfig 修改

新增配置字段（见上），默认 `enable_compression=True`，压缩作为唯一容量控制路径。

## 错误处理

| 错误场景 | 行为 | 日志级别 |
|----------|------|----------|
| Compressor 内部异常（如区域识别失败） | 捕获异常，标记无压缩区域；当前请求正常发送，后续请求重新评估 | WARNING |
| 存储替换失败（如消息已被删除） | 静默忽略，压缩后的消息列表仍然正确 | WARNING |
| LLM 摘要失败（超时/异常） | 摘要结果为空，当前轮消息不变；后续请求重新评估 | WARNING |
| 压缩 LLM 自身溢出（摘要 token 超限） | 摘要结果为空，当前轮消息不变；后续请求重新评估 | WARNING |
| compressible 区域为空 | 不执行压缩，当前消息列表完整发送 | DEBUG |
| Pruning 时消息不存在 | 静默跳过，不影响消息构建 | DEBUG |

所有错误路径均不抛出异常，确保压缩不会导致请求失败。错误处理分别在 `CompressionDetector`（同步检测异常）和 `LLMSummarizer`（异步摘要异常）内部完成，不向外部传播。

压缩失败时当前轮消息可能超出上下文窗口——由 Provider 返回的错误（如 context_length_exceeded）在上层统一转为用户可见错误，不在此处处理。

## 边界情况

| 场景 | 预期行为 |
|------|----------|
| 消息总数 ≤ compress_preserve_pairs * 2 | 不压缩（compressible 区域为空），消息完整发送 |
| compressible 区域 token 使用率未达 threshold | 不压缩，消息完整发送 |
| 压缩标记后摘要失败（超时/异常） | 摘要为空，不替换历史；后续请求再次检测触发压缩 |
| 配置启用后因其他原因无法压缩 | 消息列表完整发送，不截断 |
| 压缩摘要消息被后续再次压缩 | 允许，摘要消息视为普通消息参与 compressible 计算 |
| 单条消息超大 | 压缩不拆分单条消息；若超限超出上下文窗口，由 Provider 错误上层处理 |
| 单轮工具输出超大 | Pruning 裁剪至 TOOL_OUTPUT_MAX_CHARS 后再参与容量计算 |
| 受保护工具（skill）的大输出 | 不被裁剪，以完整内容参与压缩区域选择 |
| 当前轮消息超限被 Provider 拒绝 | Provider 返回 context_length_exceeded 错误，由上层转换为用户可见消息 |

## 实现顺序

1. **扩展 ContextConfig**：新增压缩和裁剪配置字段，移除旧的 `min_preserve_pairs` 依赖（迁移至 `compress_preserve_pairs`）
2. **定义 RegionInfo 类型**：在 `laffybot/context/types.py` 中
3. **修改 ContextBuilder 抽象接口**：`build_messages` 返回类型改为 `tuple[list[dict], RegionInfo | None]`
4. **实现 ToolOutputPruner**：纯同步工具输出裁剪函数
5. **实现 CompressionDetector**：纯同步检测函数，依赖 `RegionInfo`
6. **实现 LLMSummarizer**：接收 Provider + model，调用 `chat_completion`
7. **重写 _apply_capacity_control**：移除 FIFO 截断，改为先 pruning 后 detection
8. **实现存储替换**：`SessionStore.get_messages_by_ids` 与 `SessionStore.replace_compressed_region` 单事务原子操作
9. **修改 SessionManager**：并发摘要执行任务 `_fire_summary_and_replace`
10. **验证**：重建后上下文消息完整传递，不静默丢弃历史

## 交付清单

- [ ] `ContextConfig` 新增压缩/裁剪配置字段；移除 `min_preserve_pairs`（由 `compress_preserve_pairs` 替代）
- [ ] `_apply_capacity_control` 移除 FIFO 截断，改为仅执行 pruning + detection
- [ ] `ToolOutputPruner` 实现（`laffybot/context/compressor.py`），纯同步函数
- [ ] `CompressionDetector` 实现（`laffybot/context/compressor.py`），纯同步函数
- [ ] `LLMSummarizer` 实现（`laffybot/context/compressor.py`），接收 Provider + model，使用结构化摘要模板
- [ ] `SimpleContextBuilder.build_messages` 返回 `tuple[list[dict], RegionInfo | None]`
- [ ] `ContextBuilder` 抽象接口签名同步更新
- [ ] `SessionStore` 新增 `get_messages_by_ids` 方法，并让 `get_messages()` 返回消息 `id`
- [ ] `SessionStore` 新增 `replace_compressed_region` 方法（单事务原子替换）
- [ ] `SessionManager._fire_summary_and_replace` 并发异步任务实现
- [ ] 所有错误路径不抛出异常，消息列表始终完整传递（不静默丢弃）
- [ ] Provider context_length_exceeded 错误由上层统一转换为用户可见消息

## 参考文档

- [Codex 上下文管理架构](docs/third-party/codex/codex-context-manage.md) — 参考其压缩触发器和本地压缩策略设计
- [ContextBuilder 设计文档](docs/context-builder-design.md) — 当前架构基础，压缩作为阶段 4 实现
- [OpenCode 上下文管理设计](docs/third-party/opencode/opencode-context-management.md) — 参考其 Pruning 策略、尾轮 token 预算、结构化摘要模板和关键常量设计
