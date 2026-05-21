# RAG MCP Server 设计

> **状态**：已实现（2026-05-21）
> **实现记录**：`docs/archive/rag-mcp-server-design-2026-05-21.md`

---

## 一、设计目标

将项目文档通过 RAG（检索增强生成）技术索引，以 MCP 服务器形式暴露检索能力，使 Agent 能够主动检索项目知识库。

### 预期目标

1. Agent 可通过工具调用检索项目文档，获取相关上下文
2. RAG 服务独立部署，与 laffybot 核心解耦
3. 支持增量索引，文档变更后可更新向量库
4. 复用现有 MCP 集成架构，无需修改 laffybot 核心

## 二、架构概览

```
RAG MCP Server
    ├── MCP Server (FastMCP)
    │   ├── rag_search  — 检索知识库
    │   ├── rag_index   — 索引文档
    │   ├── rag_status  — 索引状态
    │   └── rag_watch   — 文件变更监控
    │
    ├── LlamaIndex 核心
    │   ├── VectorStoreIndex
    │   ├── QueryFusionRetriever (Hybrid Search + RRF)
    │   ├── BM25Retriever (Sparse)
    │   ├── SentenceTransformerRerank (可选)
    │   ├── MarkdownNodeParser
    │   └── SimpleDirectoryReader
    │
    ├── ChromaDB (向量存储)
    └── 自建模块
        ├── FileWatcher       — 文件变更监控
        ├── IngestionHistoryDB — 文件完整性校验
        ├── config.py         — 配置管理
        └── logger.py         — 分级日志
```

### 数据流

**检索**：Agent → rag_search → Hybrid Search (Dense + Sparse) → RRF 融合 → 可选 Rerank → 返回结果

**索引**：rag_index / 文件变更 → DocumentLoader → Splitter → Embedding（异步 HTTP） → ChromaDB

整个索引链路现已完全异步化：Embedding HTTP 调用使用 `httpx.AsyncClient`，通过 `VectorStoreIndex.ainsert_nodes()` → `_aget_text_embeddings()` → `AsyncClient.post()` 路径，不阻塞 asyncio 事件循环。Watcher 触发的索引通过 `asyncio.run()` 在 watchdog 线程中执行。

## 三、组件职责

### RAGEngine

核心引擎，管理索引生命周期和检索流程。初始化时加载 ChromaDB 中已有的索引，若不存在则等待首次索引。

### FileWatcher

基于 `watchdog` 的文件变更监控。在后台线程运行，检测到文件创建/修改/删除后触发增量索引。使用防抖机制避免频繁触发。

### IngestionHistoryDB

基于 SQLite + SHA256 的文件完整性校验库。记录每个文件的哈希值，变更检测时判断是否需要重新索引。

### MCP 工具

| 工具 | 参数 | 返回 | 描述 |
|------|------|------|------|
| `rag_search` | `query`, `top_k` | 文档片段列表 | Hybrid Search，RRF 融合 |
| `rag_index` | `paths` | 索引片段数 | 加载文档 → 分割 → 向量化 → 存储（完全异步，不阻塞事件循环） |
| `rag_status` | - | 索引状态 | 文件数、片段数、存储路径 |
| `rag_watch` | `paths`, `enabled` | 监控状态 | 启用/禁用文件变更监控 |

### 工具描述引导

每个 MCP 工具的 `description` 字段包含 Agent 引导说明：
- 适用场景说明（何时应调用此工具）
- 参数含义和使用示例
- 返回格式说明

## 四、技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| MCP 框架 | FastMCP | 支持 SSE/stdio 传输，多层工具注册 |
| 核心框架 | LlamaIndex | 内置 Hybrid Search、RRF、Rerank |
| 向量存储 | ChromaDB | 本地持久化，零依赖部署 |
| Embedding | OpenAI text-embedding-3-small | 复用 laffybot 现有 API Key |
| 检索策略 | Hybrid Search + RRF | Dense (语义) + Sparse (关键词) 融合 |
| 文件监控 | watchdog | 跨平台文件系统事件监听 |

## 五、检索策略

Hybrid Search 使用 `QueryFusionRetriever` 以 `reciprocal_rerank` 模式融合两路检索结果：

1. **Dense 检索**：`VectorRetriever`，基于 Embedding 相似度
2. **Sparse 检索**：`BM25Retriever`，基于关键词匹配
3. **RRF 融合**：Reciprocal Rank Fusion，将两路结果排序融合
4. **可选 Rerank**：`SentenceTransformerRerank`（Cross-Encoder）精排

## 六、集成方式

RAG MCP Server 作为独立 Python 包（`rag-mcp-server/`），通过 laffybot 现有的 MCP 配置机制集成：

- **SSE 模式**：独立 HTTP 服务，laffybot 通过 SSE Transport 连接
- **API Key 传递**：laffybot 通过 MCP 配置的 `env` 字段注入 `OPENAI_API_KEY`
- **工具注册**：连接后自动注册到 `ToolRegistry`，Agent 可见

## 七、配置

核心配置项通过 `config/settings.yaml` 管理，支持环境变量覆盖：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `embedding_model` | `text-embedding-3-small` | Embedding 模型 |
| `vector_store_path` | `./rag_vectors` | 向量存储路径 |
| `collection_name` | `laffybot_docs` | ChromaDB 集合名 |
| `chunk_size` | 512 | 文档分割大小 |
| `dense_top_k` | 20 | Dense 检索候选数 |
| `sparse_top_k` | 20 | Sparse 检索候选数 |
| `rerank.provider` | `none` | Rerank 类型 |
| `watch.enabled` | `true` | 文件变更监控 |
| `sse_port` | 8000 | SSE 服务端口 |

## 八、边界情况与错误处理

| 场景 | 行为 |
|------|------|
| 空查询 | 返回空列表 |
| 向量库不存在 | 初始化空索引，首次索引时创建 |
| Embedding API 超时 | 返回错误，日志记录 ERROR |
| 检索无结果 | 返回空列表，日志记录 DEBUG |
| 文档路径不存在 | 跳过该路径，日志记录 ERROR |
| 文件变更监控失败 | 记录 ERROR，不影响主服务 |
| Rerank 失败 | 返回错误，日志记录 ERROR |

所有 MCP 工具不实现 fallback/retry 逻辑，错误直接向上传播。

---

**参考文件**：
- `laffybot_agent_runtime/tools/mcp/manager.py` — MCP 服务器管理
- `laffybot/session/mcp_server_store.py` — MCP 配置持久化
- `docs/archive/rag-mcp-server-design-2026-05-21.md` — 原始设计计划
- `docs/archive/rag-mcp-server-async-2026-05-21.md` — 异步化改造实施记录
