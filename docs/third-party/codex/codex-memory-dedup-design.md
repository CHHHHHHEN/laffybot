# Codex 记忆去重机制设计

> **文档性质**：设计参考文档
> **最后更新**：2026-05-17
> **实现状态**：已实现（Codex 源码分析）

> **文档范围说明**：本文档分析 OpenAI Codex 记忆系统中防止重复提取的机制设计，包括**同一 Rollout 重复处理**和**不同 Rollout 相似内容**两个层面的去重策略，为 laffybot 记忆系统提供防重复设计的参考模式。
>
> **本文档不包含以下内容**：
> - Codex 具体实现代码和文件路径（参见 Codex 源码）
> - SQL 语句的完整实现
> - 重试算法的具体实现细节
> - 性能优化策略
>
> **与 Laffybot 的关系**：本文档为设计参考文档，不直接指导实现。具体实现决策需结合 laffybot 架构约束和优先级。

## 概述

Codex 记忆系统通过**多层防重复机制**解决两类去重问题：

| 去重类型 | 问题描述 | 核心机制 |
|---------|---------|---------|
| **同一 Rollout 重复处理** | 相同 Rollout 被多次提取 | 租约 + 水位线 + 主键约束 |
| **不同 Rollout 相似内容** | 多个对话产生相似记忆 | No-Op 门控 + Agent 去重指令 + Git Diff 检测 |

### 同一 Rollout 防重复层次

| 防重复层次 | 机制 | 作用域 |
|-----------|------|--------|
| 并发层 | 租约 (Lease) | 防止多 worker 同时处理同一任务 |
| 版本层 | 水位线 (Watermark) | 追踪已处理的数据版本 |
| 存储层 | 主键约束 | 确保每个线程只有一条输出记录 |
| 状态层 | memory_mode 过滤 | 只处理启用状态的线程 |
| 运行层 | 全局并发上限 | 限制同时运行的任务数量 |

### 相似内容防重复层次

| 防重复层次 | 机制 | 作用域 |
|-----------|------|--------|
| 源头层 | Phase 1 No-Op 门控 | 单个 Rollout 无价值则返回空 |
| 整合层 | Phase 2 Agent 指令 | 合并相似、去重、聚类规则 |
| 检测层 | Git Diff 无变化跳过 | 工作区无变化则跳过整合 |

## 核心问题

### 问题一：同一 Rollout 重复处理

**为什么需要防重复提取？**

1. **资源浪费**：重复调用 LLM API 提取相同的 Rollout 记忆
2. **数据冗余**：同一个 Rollout 产生多条记忆记录
3. **状态混乱**：多次处理导致 usage_count、last_usage 等指标失效
4. **一致性风险**：并发处理可能导致数据覆盖和竞态条件

### 问题二：不同 Rollout 相似内容

**为什么需要相似内容去重？**

1. **信息冗余**：多个对话反复确认同一偏好（如"使用中文回复"）
2. **检索效率下降**：大量相似记忆增加搜索和阅读成本
3. **Token 浪费**：相似内容重复注入上下文
4. **决策困惑**：多个相似但略有差异的记忆可能造成冲突

## 租约机制 (Lease)

### 设计目标

防止多个 worker 并发处理同一个 Rollout。

### 核心概念

| 概念 | 说明 |
|------|------|
| ownership_token | UUID 格式的租约所有权标识，每次 claim 生成新 token |
| lease_until | 租约过期时间戳，`now + lease_seconds` |
| worker_id | 持有租约的 worker 标识 |

### 租约生命周期

```
┌─────────────────────────────────────────────────────────────┐
│                    Job 状态转换                              │
│                                                              │
│  pending ──(claim)──→ running ──(finish)──→ completed       │
│     │                    │                                   │
│     │                    ├─(lease expire)─→ pending         │
│     │                    │                                   │
│     │                    └─(fail)─→ pending (retry_at)      │
│     │                                                        │
│     └─(retry exhausted)─→ failed                            │
└─────────────────────────────────────────────────────────────┘
```

### 租约获取结果

| 结果 | 说明 |
|------|------|
| Claimed | 成功获取租约，开始处理 |
| SkippedUpToDate | 源数据已是最新，无需处理 |
| SkippedRunning | 另一个 worker 持有有效租约 |
| SkippedRetryBackoff | 重试退避期未结束 |
| SkippedRetryExhausted | 重试次数耗尽 |

### 租约过期与抢占

**抢占条件**（任一满足即可抢占）：
- 当前没有 job 记录
- job 状态不是 `running`
- `lease_until` 为空或已过期（`lease_until <= now`）

**租约续期**：
- 整合 Agent（Phase 2）运行期间通过心跳机制续期
- 确保长时间运行的整合任务不会因租约过期被抢占

## 水位线机制 (Watermark)

### 设计目标

追踪已处理的数据版本，避免重复处理同一版本的源数据。

### 核心字段

| 字段 | 说明 |
|------|------|
| input_watermark | 当前处理中的源数据版本（等于 source_updated_at） |
| last_success_watermark | 上次成功处理的源数据版本 |

### 去重判断逻辑

```
┌─────────────────────────────────────────────────────────────┐
│                    去重检查流程                              │
│                                                              │
│  1. 检查现有输出                                            │
│     ├─ stage1_outputs.source_updated_at >= source_updated_at │
│     │  → SkippedUpToDate（已处理过更新版本）               │
│     │                                                        │
│  2. 检查上次成功水位线                                      │
│     ├─ jobs.last_success_watermark >= source_updated_at      │
│     │  → SkippedUpToDate（已成功处理）                      │
│     │                                                        │
│  3. 两者都不满足                                            │
│     └→ 需要处理，尝试获取租约                               │
└─────────────────────────────────────────────────────────────┘
```

### 时间戳语义

| 时间戳 | 来源 | 用途 |
|--------|------|------|
| source_updated_at | 源 Thread 的更新时间 | 判断数据是否变化 |
| generated_at | Stage 1 输出生成时间 | 记录处理时间 |
| last_usage | 被 Phase 2 选中的时间 | 使用频率排序 |
| last_success_watermark | Job 成功完成时记录 | 防重复处理基准 |

### 输出写入防覆盖

**条件更新**：只有当新数据的 `source_updated_at` 大于等于已有数据时才覆盖

```
INSERT INTO stage1_outputs (...)
VALUES (...)
ON CONFLICT(thread_id) DO UPDATE SET
    source_updated_at = excluded.source_updated_at,
    ...
WHERE excluded.source_updated_at >= stage1_outputs.source_updated_at
```

这确保：
- 旧版本数据不会覆盖新版本
- 同版本数据可以覆盖（幂等性）

## 存储层约束

### 主键约束

| 表 | 主键 | 防重复效果 |
|------|------|---------|
| stage1_outputs | thread_id | 每个 Thread 只有一条输出记录 |
| jobs | (kind, job_key) | 每种任务对每个 key 只有一条记录 |

### 外键约束

`stage1_outputs.thread_id` → `threads.id`（级联删除）

确保 Thread 删除时相关的记忆输出也被清理。

## 状态层过滤

### memory_mode 字段

| 值 | 说明 | 记忆处理行为 |
|------|------|-----------|
| enabled | 正常状态 | 参与 Phase 1 提取和 Phase 2 整合 |
| disabled | 禁用状态 | 完全跳过记忆生成 |
| polluted | 污染状态 | 从 Phase 2 输出中排除，触发重新整合 |

### 过滤逻辑位置

**Phase 1 任务选择**：
```
WHERE threads.memory_mode = 'enabled'
```

**Phase 2 记忆选择**：
```
WHERE t.memory_mode = 'enabled'
```

### 污染标记的影响

当 Thread 被标记为 `polluted` 时：
1. 该 Thread 的 Stage 1 输出不再被 Phase 2 选中
2. 如果该 Thread 参与了上次成功的 Phase 2 baseline，触发全局重新整合

## 运行层限制

### 全局并发上限

| 参数 | 说明 |
|------|------|
| max_running_jobs | 同时运行的 Stage 1 任务数量上限 |

### 作用机制

在租约获取时检查：

```
SELECT COUNT(*) FROM jobs 
WHERE kind = 'memory_stage1' 
  AND status = 'running' 
  AND lease_until > now
```

若当前运行任务数 ≥ max_running_jobs，则不再获取新任务。

## Phase 1 输入选择规则

### 完整过滤条件

| 序号 | 条件 | 说明 |
|------|------|------|
| 1 | memory_mode = 'enabled' | 只处理启用记忆的线程 |
| 2 | id != current_thread_id | 排除当前线程 |
| 3 | updated_at >= max_age_cutoff | 年龄窗口内（不太旧） |
| 4 | updated_at <= idle_cutoff | 已空闲足够时间（不活跃） |
| 5 | source_updated_at < thread_updated_at | 记忆已过时，需要更新 |
| 6 | last_success_watermark < thread_updated_at | 上次处理后有新数据 |

### 条件 5 和 6 的语义

```
stage1_outputs.source_updated_at < threads.updated_at_ms
  → Thread 有更新，但 Stage 1 输出还是旧的

jobs.last_success_watermark < threads.updated_at_ms
  → 上次成功处理后，Thread 又有更新
```

两者都表示记忆需要重新提取。

## 相似内容去重机制

### Phase 1 No-Op 门控

**设计目标**：在源头过滤无持久价值的 Rollout，防止低质量记忆进入系统。

**核心判断**：

> "Will a future agent plausibly act better because of what I write here?"

**应返回空结果的情况**：

| 类型 | 示例 |
|------|------|
| 一次性查询 | 随机问题，无持久洞察 |
| 通用状态更新 | 无结论的状态报告 |
| 临时事实 | 应重新查询的实时数据 |
| 常识性内容 | 明显或众所周知的信息 |
| 无新工件 | 无新产出、无可复用步骤、无事后分析 |

**机制效果**：单个 Rollout 层面的价值判断，从源头减少进入系统的记忆量。

### Phase 2 整合去重

**设计目标**：合并多个 Stage 1 输出时消除冗余，保留高价值信息。

#### 机械合并 + 智能整合

| 阶段 | 文件 | 策略 |
|------|------|------|
| 机械合并 | raw_memories.md | 按 thread_id 升序排列，不做智能去重 |
| 智能整合 | MEMORY.md / memory_summary.md | 由 Agent 根据 prompt 指令去重 |

**设计理由**：机械合并不丢失信息，智能整合由 Agent 根据上下文判断如何合并。

#### 整合 Agent 去重指令

**显式去重指令**：

- `Merge duplicates aggressively; prefer improving an existing skill.`
- `If several sources say nearly the same thing, merge by keeping one of the original phrasings plus any minimal glue needed for clarity.`

**聚类规则**：

| 规则 | 说明 |
|------|------|
| 按任务意图聚类 | 不是按关键词重叠 |
| 不同 cwd 默认分离 | 即使任务措辞相似也保持分离 |
| 宁可分离不过度聚类 | 存疑时保持边界分离 |

**防止过度合并**：

| 规则 | 说明 |
|------|------|
| 偏好不合并 | 如果不同偏好会影响不同的未来默认值，保持分离 |
| 具体胜于抽象 | 保留多个具体偏好条目，不过度压缩成模糊总结 |
| 长列表可接受 | 宁可 5-10 个具体条目，也不要几个模糊总结 |

#### 任务引用标记

每个 Task 必须引用来源的 rollout 文件：
- 确保可追溯性
- 合并时可验证来源
- 同一 rollout 多次引用必须提供不同价值

### Git Diff 无变化跳过

**设计目标**：避免无意义的重复整合。

**机制流程**：

```
1. 同步本地记忆工件（raw_memories.md、rollout_summaries/）
2. 计算 Git 工作区差异
3. 若无变化 → 跳过整合 Agent 运行
4. 若有变化 → 启动整合 Agent
```

**设计理由**：整合 Agent 运行成本高，通过 Git diff 检测可避免不必要的 LLM 调用。

### 新鲜度优先原则

**冲突解决策略**：

| 情况 | 策略 |
|------|------|
| 证据冲突且验证清晰 | 更新的内容优先 |
| 证据冲突且验证不清 | 显式保留不确定性 |
| 多个 Rollout 重叠 | 打开原始摘要文件进行冲突/过时解决 |

**时间戳信号**：`updated_at` 作为一等公民信号，更新的验证证据通常获胜。

## 重试机制

### 设计目标

处理临时失败，避免永久丢失需要处理的 Rollout。

### 核心字段

| 字段 | 说明 |
|------|------|
| retry_remaining | 剩余重试次数 |
| retry_at | 下次重试时间（指数退避） |
| last_error | 最后一次错误信息 |

### 重试策略

- **指数退避**：每次失败后等待时间递增
- **次数上限**：超过最大重试次数后标记为失败
- **水位线更新**：即使失败，如果 input_watermark 更新也允许重试

### 重试积压处理

失败的任务会被标记为"重试积压"，防止持续失败的任务占用处理队列。

## 设计原则

### 同一 Rollout 防重复

#### 1. 幂等性

同一操作多次执行产生相同结果：
- 租约获取失败 → 无副作用
- 输出写入 → 条件更新，同版本覆盖

#### 2. 乐观并发

不使用全局锁，通过条件检查保证一致性：
- 租约通过 SQL 条件竞争获取
- 输出通过 WHERE 条件条件更新

#### 3. 渐进式过滤

多层过滤从粗到细：
1. 状态过滤（memory_mode）
2. 时间过滤（年龄、空闲）
3. 版本过滤（水位线）
4. 并发过滤（租约）

#### 4. 明确的跳过理由

每种跳过情况都有明确的结果枚举：
- 便于监控和调试
- 便于统计各类型跳过的频率

### 相似内容去重

#### 1. 源头过滤

Phase 1 No-Op 门控在单个 Rollout 层面过滤无价值内容，减少进入系统的记忆量。

#### 2. 机械合并 + 智能整合

raw_memories.md 不做智能处理，保留全部信息；真正的去重由 Agent 根据上下文判断。

#### 3. 宁可分离不过度聚类

多个相似 Rollout 默认保持分离，除非有明确的任务意图对齐：
- 不按关键词重叠聚类
- 不同 cwd 上下文默认分离
- 存疑时保持边界

#### 4. 具体胜于抽象

保留多个具体偏好条目，避免压缩成模糊总结：
- 5-10 个具体条目优于几个模糊总结
- 不同偏好影响不同默认值时保持分离

#### 5. 引用可追溯

每个 Task 必须引用来源 rollout：
- 确保合并时可追溯和验证
- 同一 rollout 多次引用必须提供不同价值

## 设计启示

### 可借鉴的模式

#### 同一 Rollout 防重复

| 模式 | 适用场景 |
|------|---------|
| 租约机制 | 需要防止并发处理同一任务的场景 |
| 水位线追踪 | 需要判断数据版本是否需要处理的场景 |
| 多层过滤 | 数据量大，需要高效筛选的场景 |
| 状态标记 | 需要动态启用/禁用处理的场景 |
| 条件更新 | 需要幂等写入的场景 |

#### 相似内容去重

| 模式 | 适用场景 |
|------|---------|
| No-Op 门控 | 需要在源头过滤低质量数据的场景 |
| 机械合并 + 智能整合 | 需要保留原始信息同时进行智能处理的场景 |
| 宁可分离不过度聚类 | 数据价值不确定，宁可冗余不可丢失的场景 |
| 引用可追溯 | 需要验证合并决策的场景 |
| Git Diff 检测 | 需要避免无意义重复处理的场景 |

### 关键决策考量

#### 同一 Rollout 防重复

| 决策点 | Codex 选择 | 替代方案 |
|--------|-----------|---------|
| 并发控制 | 租约 + 乐观并发 | 全局锁 |
| 版本追踪 | 水位线 | 版本号 |
| 失败处理 | 重试 + 退避 | 立即失败 |
| 状态管理 | memory_mode 字段 | 删除记录 |

#### 相似内容去重

| 决策点 | Codex 选择 | 替代方案 |
|--------|-----------|---------|
| 去重时机 | Phase 1 门控 + Phase 2 整合 | 仅在存储时去重 |
| 去重粒度 | 任务意图级别 | 关键词级别 |
| 合并策略 | Agent prompt 指令 | 算法去重 |
| 冗余容忍 | 宁可冗余不可丢失 | 激进去重 |

### 与 Laffybot 的差异考量

| 维度 | Codex | Laffybot 潜在差异 |
|------|-------|------------------|
| 并发模型 | 多 worker 进程 | 单进程 asyncio |
| 租约粒度 | Thread 级别 | 可能是 Session 级别 |
| 持久化 | SQLite 状态 DB | 已有 SQLite 实现 |
| 触发时机 | 会话启动 | 可能有不同触发点 |

---

## 参考资料

- Codex 源码：`third-party/codex/codex-rs/state/src/runtime/memories.rs`
- Phase 2 整合逻辑：`third-party/codex/codex-rs/memories/write/src/phase2.rs`
- 整合 Agent Prompt：`third-party/codex/codex-rs/memories/write/templates/memories/consolidation.md`
- 数据库迁移：`third-party/codex/codex-rs/migrations/`
- 相关设计：[codex-memory-system-design.md](./codex-memory-system-design.md)（记忆系统整体架构）
