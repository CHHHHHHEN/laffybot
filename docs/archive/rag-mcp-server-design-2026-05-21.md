# MCP + RAG 架构设计计划

> **文档性质**：设计文档
> **创建日期**：2026-05-21
> **状态**：草案

---

## 一、设计目标

将 laffybot 项目文档通过 RAG（检索增强生成）技术索引，并以 MCP 服务器形式暴露检索能力，使 Agent 能够主动检索项目知识库。

### 预期目标

1. Agent 可通过工具调用检索项目文档，获取相关上下文
2. RAG 服务独立部署，与 laffybot 核心解耦
3. 支持增量索引，文档变更后可更新向量库
4. 复用现有 MCP 集成架构，无需修改 laffybot 核心

### 非目标

- 不替代现有记忆系统（记忆系统处理跨会话知识，RAG 处理项目文档）
- 不实现多租户隔离（单实例单知识库）
- 不实现多模态文档处理（Phase 1 仅文本文档）
- 不实现 Fallback 机制（任何组件失败直接返回错误）

---

## 二、架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         laffybot 核心                            │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────────┐  │
│  │ ToolRegistry│◄───│ McpServerManager │◄───│ MCP 配置存储    │  │
│  └─────────────┘    └──────────────────┘    └────────────────┘  │
│         │                                                    │
│         ▼ (工具调用)                                          │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ rag_search (MCP Tool)                                    │  │
│  │   - query: str                                           │  │
│  │   - knowledge_base: str | None                           │  │
│  │   - top_k: int                                           │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (MCP 协议: SSE)
┌─────────────────────────────────────────────────────────────────┐
│                      RAG MCP Server                             │
│  ┌─────────────┐    ┌──────────────────────────────────────┐   │
│  │ MCP Handler │───►│ Retrieval Pipeline                   │   │
│  └─────────────┘    │  ├─ HybridSearch (Dense + Sparse)    │   │
│        │            │  ├─ RRF Fusion                       │   │
│        │            │  └─ Rerank (Cross-Encoder / LLM)     │   │
│        │            └──────────────────────────────────────┘   │
│        │                                                         │
│        ▼ (工具实现)                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ rag_search / rag_index / rag_status                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Ingestion Pipeline                                       │   │
│  │  ├─ DocumentLoader (SimpleDirectoryReader)               │   │
│  │  ├─ Splitter (RecursiveCharacterTextSplitter)           │   │
│  │  ├─ Embedding (OpenAI)                                   │   │
│  │  ├─ VectorStore (ChromaDB)                               │   │
│  │  └─ FileChangeWatcher (增量索引)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 数据流

**检索流程**：
```
Agent 发起查询
    → ToolRegistry 路由到 rag_search
    → MCP 协议 (SSE) 转发到 RAG Server
    → HybridSearch 并行执行 Dense + Sparse 检索
    → RRF 融合排序
    → Rerank 精排 (可选 Cross-Encoder / LLM)
    → 返回 Top-K 文档片段
    → Agent 获取检索结果
```

**索引流程**：
```
触发索引（手动/API/文件变更监控）
    → MCP Handler 接收 rag_index 请求
    → DocumentLoader 扫描文档目录
    → Splitter 分割文档
    → Embedding 生成向量
    → VectorStore 存储（向量 + 原文 + 元数据）
    → FileChangeWatcher 记录文件哈希
```

---

## 三、组件设计

### 3.1 RAG MCP Server

**职责**：实现 MCP 协议，暴露 `rag_search` 工具，处理检索请求。

**接口**：

| 工具 | 参数 | 返回 | 描述 |
|------|------|------|------|
| `rag_search` | `query: str`, `top_k: int` | `results: list[Document]` | 搜索项目文档知识库 |
| `rag_index` | `paths: list[str]`, `force: bool` | `indexed_count: int` | 索引指定路径的文档 |
| `rag_status` | - | `status: IndexStatus` | 获取索引状态 |
| `rag_watch` | `paths: list[str]`, `enabled: bool` | `status: WatchStatus` | 启用/禁用文件变更监控 |

**Agent 引导机制**：

为帮助 Agent 正确使用 RAG 工具，采用以下引导策略：

1. **工具描述引导**：在 MCP 工具注册时，提供详细的 `description` 字段，包含：
   - 工具用途说明
   - 参数含义和使用示例
   - 适用场景（如："当用户询问项目架构、实现细节或文档内容时使用此工具"）
   - 返回格式说明

2. **引导内容位置**：
   - 仅在 MCP Server 的工具注册代码中（`tools/list` 返回的 `description`）
   - 不注入到 Agent 系统提示中
   - 当 RAG MCP 未接入时，Agent 不会看到此工具，自然不会尝试调用

**工具描述示例**：
```python
rag_search_description = """
搜索项目文档知识库，返回相关文档片段。

适用场景：
- 用户询问项目架构、设计决策或实现细节
- 需要查找特定功能或模块的文档说明
- 需要了解项目的配置或使用方法

参数：
- query: 搜索查询，应具体明确，如"context builder 的实现方式"
- knowledge_base: 可选，指定知识库，默认为项目文档
- top_k: 返回结果数量，默认 5

返回：包含 content、metadata（来源路径、行号）、score 的文档片段列表
"""
```

**通信协议**：
- 采用 SSE (Server-Sent Events) 作为主要通信协议
- SSE 支持远程部署、独立服务运行
- HTTP 端点暴露 MCP 协议，支持跨网络调用

**错误处理**：
- 向量存储不可用 → 返回错误，日志记录 `ERROR`
- 检索无结果 → 返回空列表，日志记录 `DEBUG`
- Embedding 失败 → 返回错误，日志记录 `ERROR`
- Rerank 失败 → 返回错误，日志记录 `ERROR`
- 文件变更监控失败 → 日志记录 `ERROR`，不影响 MCP 工具可用性（监控在后台线程运行）

### 3.2 核心组件

**技术选型**：采用 LlamaIndex 作为核心框架，充分利用其内置能力，最小化自建组件。

**LlamaIndex 内置能力**：

| 功能 | LlamaIndex 组件 | 说明 |
|------|-----------------|------|
| MCP Server | `workflow_as_mcp` | 将 Workflow 转换为 MCP server |
| Hybrid Search | `QueryFusionRetriever` | 组合多个 retriever，支持 RRF 融合 |
| BM25 检索 | `BM25Retriever` | 独立的 BM25 retriever |
| Rerank | `SentenceTransformerRerank` / `LLMRerank` | Node Postprocessor |
| 文档加载 | `SimpleDirectoryReader` | 支持多种格式 |
| 文档分割 | `MarkdownNodeParser` / `SentenceSplitter` | 智能分割 |
| 向量存储 | `ChromaVectorStore` | ChromaDB 集成 |

**自建组件**（仅 LlamaIndex 未覆盖的功能）：

| 功能 | 组件 | 说明 |
|------|------|------|
| 文件变更监控 | `FileChangeWatcher` | 基于 watchdog 实现实时索引 |
| 配置管理 | `config.py` | Pydantic 配置模型 |
| 分级日志 | `logger.py` | 可观测性支持 |

**内部架构**：

```
RAG MCP Server
    ├── MCP Server (workflow_as_mcp)
    │   └── rag_search / rag_index / rag_status / rag_watch 工具
    │
    ├── LlamaIndex Core
    │   ├── VectorStoreIndex (核心索引)
    │   ├── QueryFusionRetriever (Hybrid Search)
    │   │   ├── VectorRetriever (Dense)
    │   │   └── BM25Retriever (Sparse)
    │   ├── SentenceTransformerRerank (Rerank)
    │   ├── SimpleDirectoryReader (文档加载)
    │   ├── MarkdownNodeParser (分割)
    │   └── ChromaVectorStore (存储)
    │
    └── 自建模块
        ├── FileChangeWatcher (实时索引)
        ├── integrity.py (文件完整性校验)
        ├── config.py (配置)
        └── logger.py (日志)
```

**依赖项**：

| 包 | 版本 | 说明 |
|----|------|------|
| `llama-index-core` | >=0.10 | 核心框架 |
| `llama-index-readers-file` | >=0.1 | 文件加载器 |
| `llama-index-embeddings-openai` | >=0.1 | OpenAI Embedding |
| `llama-index-vector-stores-chroma` | >=0.1 | ChromaDB 集成 |
| `llama-index-retrievers-bm25` | >=0.1 | BM25 Retriever |
| `chromadb` | >=0.4 | 向量数据库 |
| `watchdog` | >=3.0 | 文件系统监控 |

### 3.3 Embedding 模型配置

**Phase 1 默认**：OpenAI `text-embedding-3-small`

**配置方式**：
- **主要方式**：laffybot 通过 MCP 配置传递 API Key。在 `MCPServerConfig.env` 字段中设置 `OPENAI_API_KEY`，RAG Server 从环境变量读取。
- **备用方式**：通过环境变量 `RAG_EMBEDDING_API_KEY` 单独配置（适用于独立部署场景）。

**API Key 传递流程**：
1. laffybot 从 `ProviderStore` 读取 OpenAI API Key（已加密存储）
2. 创建 MCP Server 配置时，将 API Key 注入 `env` 字段：
   ```json
   {
     "name": "rag-server",
     "transport_type": "sse",
     "url": "http://localhost:8000",
     "env": {"OPENAI_API_KEY": "<decrypted_key>"},
     "enabled": true
   }
   ```
3. RAG Server 启动时从 `process.env.OPENAI_API_KEY` 读取

**可选扩展**（Phase 2+）：
- 本地模型：`HuggingFaceEmbedding(model="BAAI/bge-small-en-v1.5")`
- Azure OpenAI：`AzureOpenAIEmbedding`

### 3.4 VectorStore 配置

**Phase 1 默认**：ChromaDB

**配置项**：
- `vector_store_path`: 向量存储路径（默认 `./rag_vectors`）
- `collection_name`: 集合名称（默认 `laffybot_docs`）

**可选扩展**（Phase 2+）：
- Qdrant：高性能，生产级
- sqlite-vss：与现有 SQLite 架构一致

### 3.5 文档格式支持

**Phase 1 支持**：
- `.md`：Markdown 文档（通过 `MarkdownNodeParser` 智能分割）
- `.txt`：纯文本
- `.pdf`：PDF 文档（通过 LlamaIndex 文件加载器）

**Phase 2+ 扩展**：
- `.py`：Python 源码（通过 `CodeSplitter`）
- `.json` / `.yaml`：配置文件

### 3.6 检索策略

**Phase 1**：Hybrid Search + Rerank（使用 LlamaIndex 内置组件）

**检索流程**：
1. 创建 Vector Retriever 和 BM25 Retriever
2. `QueryFusionRetriever` 以 `mode="reciprocal_rerank"` 融合两路结果（RRF 融合）
3. 可选 `SentenceTransformerRerank` 对融合结果精排

**QueryFusionRetriever 配置**：

| 参数 | 说明 |
|------|------|
| `retrievers` | retriever 列表（vector + bm25） |
| `similarity_top_k` | 融合后返回的结果数 |
| `mode` | `"reciprocal_rerank"` 使用 RRF 融合 |
| `num_queries` | 查询扩展数量（默认 4） |

**Rerank 配置**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `rerank.provider` | str | "none" | Rerank 类型（"none"=禁用, "sentence_transformer", "llm", "cohere"） |
| `rerank.model` | str | "cross-encoder/ms-marco-MiniLM-L-6-v2" | Cross-Encoder 模型 |
| `rerank.top_k` | int | 5 | Rerank 后返回的结果数 |

**Rerank 类型选项**：

| 选项 | LlamaIndex 组件 | 说明 |
|------|-----------------|------|
| `sentence_transformer` | `SentenceTransformerRerank` | Cross-Encoder，本地运行 |
| `llm` | `LLMRerank` | 使用 LLM 进行精排 |
| `cohere` | `CohereRerank` | Cohere API |

### 3.7 文件变更监控与实时索引

**目标**：实现实时索引，文档变更后自动更新索引。

**实现方案**：

1. **FileIntegrityChecker**：
   - 计算文件 SHA256 哈希
   - 存储到 SQLite 数据库（`data/db/ingestion_history.db`）
   - 表结构：
     ```sql
     CREATE TABLE ingestion_history (
         file_hash TEXT PRIMARY KEY,
         file_path TEXT NOT NULL,
         file_size INTEGER,
         status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'processing')),
         processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         error_msg TEXT,
         chunk_count INTEGER
     );
     ```

2. **实时索引流程**：
   - 使用 `watchdog` 库监控文件系统变更
   - 检测到文件变更（创建、修改、删除）时自动触发索引
   - 增量索引：仅处理变更的文件
   - 后台线程执行索引，不阻塞主服务

3. **文件变更监控工具**：
   - `rag_watch` 工具：启用/禁用指定路径的文件变更监控
   - 支持暂停/恢复监控
   - 记录监控状态到 `rag_status` 返回值

4. **变更事件处理**：
   - `created`: 索引新文件
   - `modified`: 检查哈希是否变化，若变化则重新索引
   - `deleted`: 从向量库中删除对应文档

**配置项**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `watch.enabled` | bool | true | 是否启用文件变更监控（实时索引） |
| `watch.paths` | list[str] | [] | 监控的文档路径 |
| `watch.debounce_ms` | int | 1000 | 防抖延迟（毫秒） |

**依赖项**：
```toml
"watchdog>=3.0",  # 文件系统监控
```

**`rag_watch` 工具说明**：
- `rag_watch` 提供运行时动态控制（启用/禁用监控），更改仅影响当前运行实例，不持久化到配置文件
- 如需持久化配置，需通过 `settings.yaml` 修改 `watch.enabled` 和 `watch.paths`

### 3.8 可观测性

**目标**：通过分级日志实现全链路可观测性，便于调试、监控和问题定位。

**日志级别规范**：

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| `DEBUG` | 详细调试信息，开发阶段使用 | 检索候选列表、文档分割细节 |
| `INFO` | 关键流程节点，生产环境默认 | 索引开始/完成、检索请求、文件变更检测 |
| `WARNING` | 非预期但可恢复的情况 | 配置项缺失使用默认值、跳过空文档 |
| `ERROR` | 错误情况，需要关注 | API 调用失败、索引失败、Rerank 失败 |

**日志输出位置**：
- SSE 模式：日志输出到 `stderr`，避免污染 MCP 协议通道
- 日志文件：`./logs/rag_mcp_server.log`（可选，通过配置启用）

**关键日志点**：

**检索链路**：
```
INFO  [request_id] rag_search started: query="...", top_k=...
DEBUG [request_id] dense retrieval: candidates=..., latency=...ms
DEBUG [request_id] sparse retrieval: candidates=..., latency=...ms
DEBUG [request_id] rrf fusion: results=..., latency=...ms
DEBUG [request_id] rerank: input=..., output=..., latency=...ms
INFO  [request_id] rag_search completed: results=..., total_latency=...ms
ERROR [request_id] rag_search failed: error="..."
```

**索引链路**：
```
INFO  [request_id] rag_index started: paths=..., force=...
DEBUG [request_id] scanning directory: found=... files
DEBUG [request_id] loading document: path=..., chunks=...
DEBUG [request_id] embedding: chunks=..., latency=...ms
DEBUG [request_id] upsert: vectors=..., latency=...ms
INFO  [request_id] rag_index completed: indexed=..., total_latency=...ms
ERROR [request_id] rag_index failed: path=..., error="..."
```

**文件变更监控**：
```
INFO  [watcher] file watcher started: paths=...
INFO  [watcher] file created: path=...
INFO  [watcher] file modified: path=...
INFO  [watcher] file deleted: path=...
INFO  [watcher] triggering reindex: path=...
ERROR [watcher] file watcher error: error="..."
```

**配置项**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `log_level` | str | "INFO" | 日志级别：DEBUG / INFO / WARNING / ERROR |
| `log_file` | str | None | 日志文件路径，None 则仅输出 stderr |
| `log_format` | str | 见下方 | 日志格式 |

**日志格式**：
```
%(asctime)s %(levelname)s [%(name)s] %(message)s
```

**实现要求**：
- 使用 Python 标准 `logging` 模块
- 支持 `request_id` 贯穿整个请求链路
- 支持结构化日志（JSON 格式可选）
- SSE 模式下禁止日志输出到 `stdout`

---

## 四、集成设计

### 4.1 与 laffybot MCP 架构集成

**现有架构**：
- `McpServerManager` 管理 MCP 服务器生命周期
- `MCPServerConfig` 定义服务器配置（stdio/sse/streamableHttp）
- 工具自动包装为 `McpToolCall` 并注册到 `ToolRegistry`

**集成方式**：
- RAG MCP Server 作为独立进程启动（stdio 模式）
- 或作为远程服务启动（sse 模式）
- 通过现有 MCP 配置界面管理（无需修改 UI）

**配置示例**：
```json
{
  "name": "rag-server",
  "transport_type": "sse",
  "url": "http://localhost:8000",
  "enabled": true
}
```

**Server 实现**：
- 使用 `workflow_as_mcp` 将 Workflow 转换为 MCP server
- 自动支持 SSE 和 stdio 传输
- 通过 `Workflow.run()` 启动服务

### 4.2 文档索引触发方式

| 触发方式 | 说明 | 适用场景 |
|---------|------|---------|
| **实时索引** | 文件变更监控自动触发 | 默认方式 |
| 手动触发 | 通过 `rag_index` 工具 | 初始索引、强制重建 |
| API 触发 | HTTP 端点 `/rag/index` | CI/CD 集成 |

**Phase 1 实现实时索引（默认启用）。**

### 4.3 检索结果格式

Agent 调用 `rag_search` 后，返回格式：

```
[
  {
    "content": "文档片段内容...",
    "metadata": {
      "source_path": "docs/context-builder-design.md",
      "heading": "Token 计数策略",
      "start_line": 163,
      "end_line": 200
    },
    "score": 0.85
  },
  ...
]
```

Agent 可根据 `source_path` 和行号定位原文，或直接使用 `content`。

---

## 五、配置设计

### 5.1 RAG Server 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `embedding_model` | str | "text-embedding-3-small" | Embedding 模型 |
| `embedding_api_key` | str | None | API Key（若使用 OpenAI，默认复用 laffybot 配置） |
| `embedding_api_base` | str | None | API Base URL |
| `vector_store_type` | str | "chroma" | 向量存储类型 |
| `vector_store_path` | str | "./rag_vectors" | 向量存储路径 |
| `collection_name` | str | "laffybot_docs" | ChromaDB 集合名称 |
| `chunk_size` | int | 512 | 文档分割大小（token） |
| `chunk_overlap` | int | 50 | 分割重叠大小（token） |
| `default_top_k` | int | 5 | 默认检索数量 |
| `dense_top_k` | int | 20 | Dense 检索候选数 |
| `sparse_top_k` | int | 20 | Sparse 检索候选数 |
| `rrf_k` | int | 60 | RRF 融合常数 |
| `rerank.provider` | str | "none" | Rerank 类型（"none"=禁用, "sentence_transformer", "llm", "cohere"） |
| `rerank.model` | str | "cross-encoder/ms-marco-MiniLM-L-6-v2" | Rerank 模型 |
| `rerank.top_k` | int | 5 | Rerank 返回结果数 |
| `watch.enabled` | bool | true | 是否启用文件变更监控（实时索引） |
| `watch.paths` | list[str] | [] | 监控路径列表 |
| `sse_host` | str | "0.0.0.0" | SSE 服务监听地址 |
| `sse_port` | int | 8000 | SSE 服务端口 |

### 5.2 依赖配置

**独立包依赖**（`rag-mcp-server`）：
- LlamaIndex 核心：`llama-index-core`, `llama-index-readers-file`, `llama-index-embeddings-openai`, `llama-index-vector-stores-chroma`, `llama-index-retrievers-bm25`
- 向量存储：`chromadb`
- 文件监控：`watchdog`

### 5.3 文档索引配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `document_paths` | list[str] | ["./docs"] | 文档目录列表（实时监控路径） |
| `include_patterns` | list[str] | ["**/*.md", "**/*.txt", "**/*.pdf"] | 包含文件模式 |
| `exclude_patterns` | list[str] | ["**/node_modules/**", "**/__pycache__/**"] | 排除文件模式 |

---

## 六、错误处理

| 场景 | 行为 | 日志级别 |
|------|------|---------|
| Embedding API 超时 | 返回错误，不重试 | ERROR |
| 向量存储连接失败 | 返回错误，不重试 | ERROR |
| 检索无结果 | 返回空列表 | DEBUG |
| 文档加载失败（文件不存在） | 返回错误 | ERROR |
| 文档分割失败 | 返回错误 | ERROR |
| Rerank 失败 | 返回错误 | ERROR |
| 文件变更监控失败 | 记录日志，不影响主服务 | ERROR |

---

## 七、边界情况

| 情况 | 处理 |
|------|------|
| 空查询字符串 | 返回空列表 |
| `top_k` 超过向量库大小 | 返回所有匹配结果 |
| 文档内容为空 | 返回错误 |
| 文档编码非 UTF-8 | 返回错误 |
| 向量维度不匹配 | 返回错误，需重建索引 |
| 知识库不存在 | 返回错误 |
| 并发索引冲突 | 返回错误，由调用方重试 |

---

## 八、实现阶段

### Phase 1：最小可用版本

**目标**：验证 Agent 能否正确调用 RAG 工具并获取相关内容。

**技术栈**：
- **MCP 协议**：SSE Transport
- **向量存储**：ChromaDB
- **Embedding**：OpenAI `text-embedding-3-small`（复用现有 API Key）
- **检索策略**：Hybrid Search (Dense + Sparse) + RRF Fusion
- **Rerank**：可选 Cross-Encoder
- **文档格式**：`.md`、`.txt`、`.pdf`

**实现范围**：
1. MCP Server（workflow_as_mcp）
    - 使用 `workflow_as_mcp` 创建 MCP server
    - 实现 `rag_search`、`rag_index`、`rag_status`、`rag_watch` 工具
    - 工具描述引导（description 字段）
    - SSE 模式下日志重定向到 stderr（避免污染 MCP 协议通道）
    - 启动时预加载重量级依赖（chromadb、onnxruntime），避免 `asyncio.to_thread()` 死锁
2. LlamaIndex 核心组件
    - `VectorStoreIndex`：核心索引管理
    - `QueryFusionRetriever`：Hybrid Search + RRF 融合
    - `BM25Retriever`：BM25 检索
    - `SentenceTransformerRerank`：Rerank（可选）
    - `SimpleDirectoryReader`：文档加载
    - `ChromaVectorStore`：向量存储
3. 自建模块
    - `FileChangeWatcher`：基于 watchdog 的实时索引
    - `integrity.py`：文件完整性校验（SHA256/SQLite）
    - `config.py`：配置管理
    - `logger.py`：分级日志
4. 配置管理
    - 支持通过 YAML 文件加载配置
    - OpenAI API Key 从环境变量读取（由 laffybot 通过 MCP `env` 字段传递）
5. laffybot 集成
    - 在 laffybot 中创建 RAG Server 的 MCP 配置（通过 API 或直接写入 `mcp_servers` 表）
    - 配置 `env` 字段包含 `OPENAI_API_KEY`（从 ProviderStore 解密获取）
    - 启用 RAG Server 后，工具自动注册到 ToolRegistry

**代码结构**：

RAG MCP Server 作为独立 Python 包（`rag-mcp-server`），与 laffybot 核心解耦：

```
rag-mcp-server/              # 独立 Python 包
├── pyproject.toml          # 独立依赖配置
├── rag_mcp_server/
│   ├── __main__.py         # 入口：启动 workflow_as_mcp server
│   ├── workflow.py         # LlamaIndex Workflow 定义
│   ├── config.py           # 配置模型（Pydantic）
│   ├── logger.py           # 分级日志
│   ├── file_watcher.py     # 文件变更监控（watchdog）
│   └── integrity.py        # 文件完整性校验（SHA256/SQLite）
└── config/
    └── settings.yaml        # 默认配置
```

**核心实现要点**：

- 使用 `workflow_as_mcp` 将 LlamaIndex Workflow 转换为 MCP Server
- `QueryFusionRetriever` 组合 Vector Retriever 和 BM25 Retriever，使用 RRF 融合
- 可选的 `SentenceTransformerRerank` 作为 Node Postprocessor
- 文件变更监控使用 `watchdog` 库，在后台线程运行，错误不影响主服务

**独立包优势**：
- 可独立安装、部署、版本管理
- 与 laffybot 核心解耦，互不影响
- 可被其他项目复用

### Phase 2：检索质量优化

---

## 九、交付清单

### Phase 1 完成标准

- [ ] RAG MCP Server 可独立启动，SSE 端点响应正常
- [ ] 独立 Python 包正确安装并配置
- [ ] `rag_search` 工具通过 MCP 注册到 laffybot，Agent 可调用
- [ ] `rag_index` 工具能索引 `docs/` 目录（.md、.txt、.pdf），返回索引文档数
- [ ] 检索结果格式正确，包含 `content`、`metadata`、`score`
- [ ] QueryFusionRetriever 融合 Dense + Sparse 结果，返回 Top-K（RRF 算法）
- [ ] BM25Retriever 关键词检索返回相关文档，score > 0
- [ ] SentenceTransformerRerank 启用后重排结果，禁用时不影响主流程
- [ ] Agent 调用工具后获取正确结果
- [ ] 文件变更监控检测到文档修改后触发增量索引
- [ ] 错误场景正确处理：API 超时返回错误，无结果返回空列表，Rerank 失败返回错误
- [ ] 配置通过 YAML 文件加载
- [ ] OpenAI API Key 通过 MCP `env` 字段传递，RAG Server 从环境变量读取
- [ ] 工具描述引导正确显示
- [ ] 分级日志输出到 stderr，SSE 模式下 stdout 无污染
- [ ] MCP 协议版本协商成功（2025-03-26）

---

## 十、参考文件

### 项目内部

- `laffybot/agent/tools/mcp/manager.py`：MCP 服务器管理
- `laffybot/agent/tools/mcp/client.py`：MCP 客户端实现
- `laffybot/api/mcp_routes.py`：MCP 配置 API
- `docs/memory-system-impl-roadmap.md`：记忆系统实现路线（参考异步触发模式）
- `docs/context-builder-design.md`：上下文构建设计（参考模板注入模式）

### 第三方参考

- `third-party/MODULAR-RAG-MCP-SERVER/`：模块化 RAG MCP Server 参考实现
  - `src/mcp_server/`：MCP 协议处理和工具注册
  - `src/ingestion/`：索引 Pipeline 和文件变更监控
  - `config/settings.yaml`：配置文件格式参考

### LlamaIndex 文档

- https://docs.llamaindex.ai/：LlamaIndex 官方文档
- https://docs.llamaindex.ai/en/stable/module_guides/mcp/：MCP 集成指南
- https://docs.llamaindex.ai/en/stable/module_guides/indexing/vector_store_index/：VectorStoreIndex 指南
- https://docs.llamaindex.ai/en/stable/examples/retrievers/reciprocal_rerank_fusion/：QueryFusionRetriever 示例
- https://docs.llamaindex.ai/en/stable/examples/retrievers/bm25_retriever/：BM25Retriever 示例
- https://docs.llamaindex.ai/en/stable/module_guides/querying/node_postprocessors/：Node Postprocessor (Rerank)

---

## 现有技术债务

以下问题为代码库中已存在的问题，不在本计划范围内，记录以供参考。

| 类别 | 位置 | 描述 |
|------|------|------|
| 可维护性 | `laffybot/api/mcp_routes.py:133-136` | UNIQUE 约束检测使用字符串匹配，模式脆弱 |
| 结构 | `laffybot/agent/tools/mcp/manager.py:115` | `tool_registry: Any` 类型标注，应使用 `ToolRegistry` |
