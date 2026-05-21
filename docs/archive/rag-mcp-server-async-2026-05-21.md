# Plan: RAG MCP Server 完全异步化

## 问题描述

`rag_index` 工具在 async MCP 工具函数中直接调用同步的 `engine.index()`，阻塞整个 asyncio 事件循环。导致：
- Agent 调用 `rag_index` 索引文件时服务器卡死
- SSE 连接无法接收新消息
- 其他工具调用无法处理

## 问题链路

```
rag_index (async tool)
    ↓
engine.index() (同步, 阻塞事件循环)
    ↓
_index_dir() (同步)
    ↓
VectorStoreIndex(nodes=nodes, embed_model=...) (同步)
    ↓
_embed_model._get_text_embedding() (同步 HTTP)
    ↓
httpx.Client.post() (同步, 阻塞直到响应)
```

与 `rag_search` 对比：`rag_search` 使用 `await engine.search()`，而 `engine.search()` 是真正的 `async def`，内部调用 `await fusion.aretrieve(query)`，不阻塞事件循环。

## 确认的技术细节

通过调研 llama_index 0.14.22 的异步 API，确认以下支持：

| 组件 | 异步方法 | 说明 |
|------|---------|------|
| `VectorStoreIndex` | `ainsert_nodes()` | 异步插入节点，完整调用链路: `ainsert_nodes` → `_async_add_nodes_to_index` → `_aget_node_with_embedding` → `async_embed_nodes` → `embed_model.aget_text_embedding_batch` → `_aget_text_embeddings` |
| `ChromaVectorStore` | `async_add()` | 异步添加到向量存储 |
| `IngestionPipeline` | `arun()` | 异步执行整个 pipeline |
| `BaseEmbedding` | `_aget_text_embeddings()` | 抽象方法，默认 `asyncio.gather` 调用 `_aget_text_embedding` |
| `BaseEmbedding` | `_aget_text_embedding()` | 抽象方法，默认实现是 `return self._get_text_embedding(text)`（同步回退） |

关键发现：`_aget_text_embedding` 的默认实现是调用同步版本的 `_get_text_embedding`。所以即使 llama_index 的异步方法调用了 `_aget_text_embedding`，如果没有覆写它，仍然会退回到同步调用。必须同时在 `OpenAICompatibleEmbedding` 中覆写 `_aget_text_embedding` 和 `_aget_text_embeddings` 为真正的异步实现。

## 实施计划

### 涉及文件

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `rag_mcp_server/embeddings.py` | 中等 | 添加 AsyncClient，实现异步 HTTP；抽公共 HTTP 方法减少维护面 |
| `rag_mcp_server/workflow.py` | 中等 | 替换 index/_index_dir 为 aindex/_aindex_dir，watcher 改用 async |

### Step 1: 修改 `embeddings.py`

**目标**: 为 `OpenAICompatibleEmbedding` 添加真正的异步 HTTP 支持。

**改动内容**:

1. **`__init__`**: 在现有同步 `httpx.Client` 旁，新增一个 `httpx.AsyncClient` 实例，使用相同的 `http_timeout`。同步和异步 client 各自独立，避免线程安全问题。

2. **`_acall_api()`**: 新增异步方法，功能与同步 `_call_api()` 一致——拼接请求 URL、构造 headers、POST 到 `/embeddings` 端点——但使用 `self._async_client` 发起 HTTP 请求。错误处理（连接错误、超时、HTTP 状态码、JSON 解析、结果完整性检查）保持与同步版本相同的逻辑。

   为了减少同步/异步 HTTP 调用的代码重复，将以下逻辑抽取为公共方法供 `_call_api` 和 `_acall_api` 共用：
   - URL 拼接、headers 构造、payload 构建 → `_build_embedding_request(texts)`
   - HTTP 响应状态码检查 → `_check_response(resp, url)`
   - JSON 解析、结果完整性检查 → `_parse_embedding_response(texts, data)`

   这样每个 HTTP 方法只保留"用对应 client 发请求"这一步不同，其余逻辑共享同一份代码。

3. **覆写三个异步方法**：`_aget_text_embedding`、`_aget_text_embeddings`、`_aget_query_embedding`，使其调用 `_acall_api()` 而非回退到同步 `_get_text_embedding`。其中 `_aget_text_embeddings` 直接 batch 调用 `_acall_api`（避免逐个 await），`_aget_text_embedding` 和 `_aget_query_embedding` 委托给 `_acall_api([text])` 后取首个结果。

4. **`close()`**: `close()` 保持关闭同步 client。异步 `AsyncClient` 的生命周期由进程退出时自动回收，无需额外清理。（httpx 0.28.1 不关闭 `AsyncClient` 不会产生警告或资源泄漏。）

**设计决策**:
- 同步方法（`_call_api`, `_get_text_embedding`）必须保留，因为 `_get_text_embedding` 是 `BaseEmbedding` 的 `@abstractmethod`。但实际运行时只走异步路径，同步方法仅作为抽象接口的薄实现存在
- 异步方法使用独立 `AsyncClient`，不共享 client，避免线程安全问题
- HTTP 公共逻辑（请求构建、响应解析、错误检查）抽取为共享方法，`_call_api` 和 `_acall_api` 各自只封装发请求这一步

### Step 2: 修改 `workflow.py`

**目标**: 添加异步索引方法，使 `rag_index` 工具完全异步化。

**改动内容**:

1. **`RAGEngine._aindex_dir()`**: 新增异步方法，替换 `_index_dir()`。与 `_index_dir()` 流程一致但替换网络 I/O 部分：
   - 同步保留：路径校验、`SimpleDirectoryReader.load_data()`（本地文件 I/O，速度快）、`MarkdownNodeParser` 文档分割（纯 CPU 计算）
   - 异步化：若 `self._index` 为 None 则通过 `VectorStoreIndex.from_vector_store()` 初始化；之后调用 `await self._index.ainsert_nodes(nodes)` 替代同步 `insert_nodes`，触发 Embedding API 调用时不会阻塞事件循环
   - 插入成功后遍历 nodes 调用 `self._ingestion.record()` 记录索引历史（同步 SQLite，速度快）

2. **`RAGEngine.aindex()`**: 新增异步方法，替换 `index()`。遍历 paths，对每个 path `await self._aindex_dir(p)` 并累加结果。

3. **修改 `rag_index` 工具**: 将 `engine.index(paths, force=force)` 改为 `await engine.aindex(paths)`。同时移除工具签名的 `force` 参数（原属死代码），其余日志、异常处理保持不变。

4. **更新 watcher 回调**: 将 `_on_file_created` 和 `_on_file_modified` 中的 `self._index_dir(...)` 改为 `asyncio.run(self._aindex_dir(...))`。watchdog 在独立线程运行，没有 running event loop，`asyncio.run()` 安全可用。

5. **删除无用同步代码**: 确认 `_index_dir()` 和 `index()` 零调用者后，直接删除这两个方法。

### 不动的内容

- `rag_search` 已正确使用异步，无需修改
- `rag_status`、`rag_watch` 工具函数无需修改
- `RAGEngine.__init__` 中的初始化逻辑无需修改
- 配置文件和启动脚本无需修改

### 注意

- 删除同步 `_index_dir()` 和 `index()` 时，注意 `index()` 的 `force` 参数在同步版本中就未使用，属于已有死代码。异步 `aindex()` 的签名也不再保留 `force` 参数，一并清理。

### 调用链路（修改后）

MCP 工具调用路径：

```
rag_index (async tool)
    ↓ await
engine.aindex() (async def)
    ↓ await
_aindex_dir() (async def)
    ├── SimpleDirectoryReader.load_data()  (同步, 本地文件)
    ├── MarkdownNodeParser.get_nodes_from_documents()  (同步, CPU)
    └── await VectorStoreIndex.ainsert_nodes()  (异步)
             ↓
        _async_add_nodes_to_index()
             ↓ await
        _aget_node_with_embedding()
             ↓ await
        async_embed_nodes()
             ↓ await
        embed_model.aget_text_embedding_batch()
             ↓ asyncio.gather
        _aget_text_embeddings()  (覆写为真正的异步)
             ↓ await
        httpx.AsyncClient.post()  (异步 HTTP，不阻塞)
```

Watcher 触发路径：

```
watchdog 线程 → _on_file_created / _on_file_modified
    ↓ asyncio.run()
_aindex_dir()  →  同上后半段（嵌入 → 索引）
```

## 验收标准

1. **非阻塞索引**: 调用 `rag_index` 索引文件时不阻塞事件循环 — 同时发起 `rag_search` 请求应能正常返回
2. **Watcher 正常工作**: 文件变更通过 `asyncio.run(aindex_dir())` 触发增量索引，不抛异常
3. **HTTP 错误传播**: 异步 Embedding 路径的错误处理（连接失败、超时、401、404 等）与同步路径行为一致

## 验证

1. `uv run ruff check rag_mcp_server/` — 语法检查通过
2. `uv run mypy rag_mcp_server/` — 类型检查通过
3. 启动 RAG MCP 服务器，调用 `rag_index` 索引文件，确认不再卡住
4. 确认 laffybot 能正常连接并调用所有 MCP 工具
