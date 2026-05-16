# 记忆系统实现路线

> **实现状态**：Phase 0 ✅ 已完成，Phase 1 ✅ 已完成，Phase 2 ✅ 已完成
> **最后更新**：2026-05-16
>
> **文档范围说明**：本文档规划将 Codex 两阶段记忆管道选择性迁移到 Laffybot 的实现路线。阅读前请先了解 `docs/third-party/codex/codex-memory-system-design.md`。
>
> **本文档不包含以下内容**：
> - 具体代码实现和文件路径
> - Prompt 模板的具体内容
> - 数据库 Schema 定义
> - 测试策略

## 迁移范围

### 采纳的设计

| Codex 设计 | 采纳程度 | 说明 |
|-----------|---------|------|
| 两阶段管道（提取 + 整合） | 完整采纳 | 保留 Phase 1 提取 + Phase 2 整合分离模式 |
| No-Op 门控 | 完整采纳 | 仅在记忆可改善未来行为时才保存 |
| 记忆质量标准（高信号/低信号分类） | 完整采纳 | 保持证据驱动的记忆质量要求 |
| 证据优先级（用户消息 > 工具输出 > Assistant 动作） | 完整采纳 | 指导提取时的信息权重 |
| 使用频率 + 最近性排序 | 完整采纳 | Phase 2 选择算法直接沿用 |
| 遗忘窗口（max_unused_days） | 完整采纳 | 低频/过时记忆自动淘汰 |
| 记忆分类存储 | 完整采纳 | 按 tags 字段分类，数据库单表存储（替代 Codex 的文件分层方案） |
| 使用反馈回路 | 采纳，推迟到 Phase 3 | 先在内存中跟踪，后续持久化 |

### 适配的设计

| Codex 设计 | Laffybot 适配方案 |
|-----------|------------------|
| Rollout 概念 | 映射为 Session。取 Session 的消息历史作为提取源，不做跨 Rollout 检索 |
| 并行 Phase 1 提取 | 简化为串行：单个 Session 完成后提取，不做批量并行 |
| Git 工作区基线 | 简化为文件修改时间戳。以文件最后修改时间判断是否需要重新整合 |
| MCP 服务器 | 适配为 HTTP API 端点，挂载到 `laffybot/api/routes.py` 对应路由组下 |
| 开发指令注入（memory_summary 自动注入） | 通过 ContextBuilder 的系统提示模板变量注入 |
| 渐进式披露 | 分两步实现：Phase 2 全量注入摘要，Phase 3 优化为按需搜索 |
| 租约机制 | 无需租约。单实例串行处理无需分布式锁 |
| 内存模式状态机 | 简化：`enabled` 字段仅作信息记录，运行时的启用由提取模型是否已配置决定；后续可按需引入完整状态管理 |

### 暂不实现

| Codex 功能 | 理由 |
|-----------|------|
| Skills 目录 | Laffybot 尚无流程复用需求；可在记忆系统成熟后补充 |
| Extensions 扩展记忆源 | Laffybot 无第三方扩展生态，无 Ad-hoc 更新需求 |
| 整合 Agent（沙箱约束） | Laffybot 无子 Agent 架构，不需要隔离执行 |
| 速率限制门控 | Laffybot 使用用户自托管模型，配额充足 |
| 冷却期 | 串行单次处理无需冷却 |
| 脱敏处理 | Laffybot 当前不采集敏感信息；可由 Prompt 约束代替 |

## 架构概览

```
Session 完成 ──► Phase 1 提取 ──► 数据库 (memories 表)
                                      │
新 Session 启动 ──► Phase 2 整合 ──► 选中 Top-N ──► 注入系统提示 ──► Agent 执行
                                      │
                                     Phase 3 反馈 ──► 更新排序权重
```

**数据流**：

1. Session 正常完成后，异步触发 Phase 1：将 Session 消息历史提取为结构化记忆，写入 `memories` 数据库表
2. 新 Session 启动时，触发 Phase 2：从已有记忆中选择 Top-N，生成紧凑摘要，通过 ContextBuilder 注入系统提示
3. Agent 执行后，记忆引用信息回写排序指标（Phase 3）

**状态与错误路径**：

- 提取失败（LLM 调用失败、存储写入失败）：记录日志，不阻塞 Session 流程
- Phase 2 无可用记忆：空注入，Session 正常执行
- 存储容量满：按遗忘窗口淘汰最旧记忆，再写入新记忆

## 存储结构

```
数据库 (SQLite)
└── memories 表
    ├── memory_id      TEXT PK (UUID)
    ├── session_id     TEXT NOT NULL (FK → sessions)
    ├── content        TEXT NOT NULL
    ├── tags           TEXT (JSON 数组)
    ├── created_at     TEXT (ISO 时间戳)
    ├── updated_at     TEXT
    ├── usage_count    INTEGER DEFAULT 0
    └── last_usage     TEXT
```

> Phase 0 的文件系统存储已在 Phase 1 中废弃，所有记忆操作通过 `MemoryStore` 数据库层完成。

## 实现阶段

### 依赖关系

```
Phase 0 ───────────► Phase 1 ──► Phase 2 ──► Phase 3
  存储基础              提取         注入         优化
```

- **Phase 0 ~ Phase 2** 构成最小可用记忆系统（MVP），交付后可上线
- **Phase 3** 为体验优化，在 MVP 使用后迭代

### Phase 0：存储基础 ✅ 已实现

**目标**：建立记忆系统所需的配置项和数据库层骨架。

**任务**：

- 定义记忆系统配置模型 `MemoryConfig`
- 增加记忆系统相关配置项（提取模型默认值、最大记忆数、遗忘天数等）
- 新增 `laffybot/memory/` 组件包，定义模块边界

**完成后产出**：
- 配置项可读写
- 模块骨架可通过依赖注入挂载到 SessionManager

**依赖**：无

---

### Phase 1：记忆提取 ✅ 已实现

**目标**：从已完成 Session 中提取结构化记忆，持久化到数据库。

**提取触发时机**：Session 正常完成后（`send_message` 的 `done` 事件后），以 `asyncio.create_task` 异步触发，不阻塞后续请求。此模式与现有 Auto-Title 触发机制一致。

**提取流程**（高层描述）：

- 检查 Session 是否满足提取条件（消息数足够、未被提取过）
- 整理 Session 消息历史（保留 user/assistant/tool 消息）
- 调用 LLM 提取结构化记忆，核心方向为"可复用的跨会话知识"（用户偏好、项目约定、工具使用模式）
- 应用 No-Op 门控：若记忆对未来 Agent 表现无改善，则丢弃
- 通过后写入 `memories` 数据库表

**不应触发提取的场景**：
- 提取模型未配置（既不在 config.yaml 中也不在 UI 中）
- Session 消息数过少（无完整 user/assistant 对话轮次）

**完成后产出**：
- 完成后的 Session 由异步任务提取记忆并写入 `memories` 数据库表
- 记忆记录含 session_id、content、tags、创建时间、使用计数等字段
- 提取模型独立于总结模型，通过 UI 配置
- 前端提供记忆管理页面（列表/详情/来源追溯/删除）

**依赖**：Phase 0

---

### Phase 2：上下文注入 ✅ 已实现

**目标**：在新建 Session 时将记忆注入上下文，使 Agent 知道先前会话的知识。

**注入方式**：通过 ContextBuilder 的系统提示模板变量注入。`SystemPromptTemplate.render()` 已支持 `**extra_vars`，新增 `memories` 变量即可，无需修改现有接口。

**注入逻辑**：

- Session 启动时检查可用记忆
- 按使用频率 + 最近性选择 Top-N
- 生成紧凑摘要注入系统提示
- 控制记忆部分的 Token 预算，不影响核心提示和历史

**记忆查询接口**（Phase 1 已实现）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/memories` | 列出记忆（支持分页、搜索） |
| GET | `/api/v1/memories/{id}` | 单条记忆详情，包含来源 Session 标题等信息 |
| GET | `/api/v1/memories/{id}/source` | 获取该记忆所来源 Session 的消息历史 |
| DELETE | `/api/v1/memories/{id}` | 删除单条记忆 |

**完成后产出**：
- 新建 Session 的上下文中包含先前会话的记忆摘要
- 前端或 API 可通过搜索接口检索历史记忆

**依赖**：Phase 1（至少有一条记忆）

---

### Phase 3：优化迭代

**目标**：提升记忆的质量和效率，引入反馈循环。

**任务**：

- **选择算法升级**：引入类型区分（用户偏好、项目知识、环境配置等），支持按类型选择性加载
- **渐进式披露**：从全量注入改为分层——先注入摘要索引，Agent 按需搜索详细内容
- **使用反馈回路**：跟踪 Agent 实际引用了哪些记忆，更新 `usage_count` 和 `last_usage`，让高频记忆更易被选中
- **遗忘机制**：按 `max_unused_days` 配置自动标记/淘汰过期记忆

**完成后产出**：
- 记忆质量自我优化（好记忆更突出，坏记忆被遗忘）
- 记忆按需披露，不浪费 Token

**依赖**：Phase 2

## 集成点

### ContextBuilder

- 新增系统提示模板变量 `{{ memories }}`。`SystemPromptTemplate.render()` 已支持 `**extra_vars`，但 `ContextBuilder.build_messages()` 当前不接收 `extra_vars`；Phase 2 需扩展其接口以透传记忆数据到模板渲染
- 容量控制为记忆预留 Token 预算：优先保证系统提示和历史消息，记忆部分可被截断

### SessionManager

- `send_message()` 完成后新增异步触发：在现有 Auto-Title 触发逻辑后追加记忆提取触发
- `send_message()` 开始前的消息构建流程中，同步加载当前 Phase 2 产出到模板变量
- 通过依赖注入引入 MemoryManager 实例

### 配置系统

新增记忆系统配置（Pydantic 模型）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `enabled` | 信息性标记，实际启用由提取模型是否已配置决定 | `False` |
| `extract_model` | 提取模型默认值 | 仅由 UI 设置（AppSettingStore），`MemoryConfig` 中该字段当前不参与运行时提取判断；提取流程通过 `get_extract_model()` 读取 UI 配置，未配置时静默跳过 |
| `max_session_summaries` | 最大记忆数 | `50` |
| `max_unused_days` | 遗忘窗口 | `30` |
| `top_n_for_injection` | 注入时选 N 条 | `5` |
| `max_memory_tokens` | 记忆部分 Token 上限 | `1000` |

## 错误处理与边界情况

| 场景 | 行为 |
|------|------|
| 提取模型未配置（config.yaml 和 UI 均未设置） | `_trigger_extract` 记录 debug 日志后静默跳过，不调用 LLM |
| LLM 调用失败（网络超时、模型不可用） | 记录 warning 日志后静默退出，不重试（同 auto-title 模式）；Session 正常流程不受影响 |
| 记忆数据库写入失败（磁盘满等） | 记录日志，不阻塞 Session 流程 |
| 提取结果被 No-Op 门控丢弃 | 记录 debug 日志，不写入数据库 |
| Phase 2 无可用记忆 | 空注入，Session 正常执行 |
| 同时触发多个提取（多个 Session 同时完成） | 每个提取独立串行执行，不加锁；Phase 2 读取时忽略未完成的提取 |
| Session 已被提取过 | 查询 `memories` 表中该 session_id 的记录，已存在则跳过 |

## 设计决策

| 决策点 | 选择 | 替代方案 | 理由 |
|--------|------|---------|------|
| 提取时机 | Session 完成后异步触发 | 定时任务、启动时扫描 | 时机明确，与现有 Auto-Title 模式一致 |
| 存储介质 | 数据库（SQLite `memories` 表） | 文件系统、纯 SQLite | 与 session/message 同库，简化备份和运维；外键约束保证数据完整性 |
| 注入方式 | 系统提示模板变量 | 消息前缀、Tool 注入 | 改动最小（仅需新增 extra_var），不增加消息数 |
| 选择算法 | usage_count + last_usage | 向量相似度 | 无需外部依赖，实现简单 |
| 提取模型 | 可配置，**独立于 summary_model** | 与 summary_model 共用 | 提取任务需较强指令遵循能力，独立配置更灵活 |
| 运行时启用 | 隐式：提取模型已配置即表示启用 | config.yaml `enabled` 显式开关 | 用户配置提取模型后立即生效，无需重启 |
| Phase 1 串行 | 一次处理一个 Session | 批量并行 | 会话量级低，串行更简单 |
| Phase 2 查询接口 | 先实现搜索，后续按需拆分 | 立即实现 list/read/search 三个端点 | 减少 MVP 接口 surface |
