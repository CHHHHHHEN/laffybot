from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from rag_mcp_server.config import RAGConfig
from rag_mcp_server.file_watcher import FileWatcher
from rag_mcp_server.logger import get_logger

RAG_SEARCH_DESCRIPTION = """
搜索项目文档知识库，返回相关文档片段。

适用场景：
- 用户询问项目架构、设计决策或实现细节
- 需要查找特定功能或模块的文档说明
- 需要了解项目的配置或使用方法

参数：
- query: 搜索查询，应具体明确，如"context builder 的实现方式"
- top_k: 返回结果数量，默认 5

返回：包含 content、metadata（来源路径）、score 的文档片段列表
"""

RAG_INDEX_DESCRIPTION = """
索引指定路径的文档到知识库。

参数：
- paths: 要索引的文档目录路径列表

返回：成功索引的文档片段数量
"""

RAG_STATUS_DESCRIPTION = """
获取当前知识库索引状态。

返回：包含索引文件数、文档片段数、向量存储路径等状态信息
"""

RAG_WATCH_DESCRIPTION = """
启用或禁用文件变更监控。当监控路径下的文件发生变更时，自动触发增量索引。

参数：
- paths: 监控的文档路径列表
- enabled: 是否启用监控

返回：监控状态信息
"""


class RAGEngine:
    def __init__(self, config: RAGConfig) -> None:
        self.config = config
        self._logger = get_logger("rag_mcp_server.engine")
        self._index: Any = None
        self._vector_store: Any = None
        self._embed_model: Any = None
        self._db_path = str(Path(config.vector_store_path) / "ingestion.db")
        self._ingestion_db: Any = None
        self._watcher = FileWatcher(debounce_ms=config.watch.debounce_ms)
        self._init_embedding()
        self._init_vector_store()
        self._load_index()

    def _init_embedding(self) -> None:
        if self.config.embedding_api_base:
            from rag_mcp_server.embeddings import OpenAICompatibleEmbedding

            self._embed_model = OpenAICompatibleEmbedding(
                model=self.config.embedding_model,
                api_base=self.config.embedding_api_base,
                api_key=self.config.embedding_api_key,
            )
        else:
            from llama_index.embeddings.openai import OpenAIEmbedding

            kwargs: dict[str, Any] = {
                "model": self.config.embedding_model,
            }
            if self.config.embedding_api_key:
                kwargs["api_key"] = self.config.embedding_api_key

            self._embed_model = OpenAIEmbedding(**kwargs)

    def _init_vector_store(self) -> None:
        import chromadb
        from llama_index.vector_stores.chroma import ChromaVectorStore

        db = chromadb.PersistentClient(path=self.config.vector_store_path)
        collection = db.get_or_create_collection(self.config.collection_name)
        self._vector_store = ChromaVectorStore(chroma_collection=collection)

    def _load_index(self) -> None:
        from llama_index.core import VectorStoreIndex

        try:
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=self._vector_store,
                embed_model=self._embed_model,
            )
        except Exception as exc:
            self._logger.warning("No existing index found: %s", exc)
            self._index = None

    @property
    def _ingestion(self) -> Any:
        if self._ingestion_db is None:
            from rag_mcp_server.integrity import IngestionHistoryDB

            self._ingestion_db = IngestionHistoryDB(self._db_path)
        return self._ingestion_db

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        from llama_index.core.retrievers import QueryFusionRetriever
        from llama_index.retrievers.bm25 import BM25Retriever

        if not self._index:
            return []

        vector_retriever = self._index.as_retriever(
            similarity_top_k=self.config.dense_top_k,
        )
        bm25_retriever = BM25Retriever.from_defaults(
            index=self._index,
            similarity_top_k=self.config.sparse_top_k,
        )

        fusion = QueryFusionRetriever(
            retrievers=[vector_retriever, bm25_retriever],
            similarity_top_k=top_k,
            num_queries=1,
            mode="reciprocal_rerank",
            use_async=True,
        )

        nodes = await fusion.aretrieve(query)

        if self.config.rerank.provider == "sentence_transformer":
            from llama_index.core.postprocessor import SentenceTransformerRerank

            reranker = SentenceTransformerRerank(
                model=self.config.rerank.model,
                top_k=self.config.rerank.top_k,
            )
            nodes = reranker.postprocess_nodes(nodes, query_str=query)

        results = []
        for node_with_score in nodes:
            node = node_with_score.node
            results.append(
                {
                    "content": node.get_content(),
                    "metadata": {
                        "source_path": node.metadata.get("file_path", ""),
                        "heading": node.metadata.get("heading", ""),
                    },
                    "score": node_with_score.score or 0.0,
                }
            )

        return results

    async def _aindex_dir(self, path: str) -> int:
        from llama_index.core import VectorStoreIndex
        from llama_index.core.node_parser import MarkdownNodeParser
        from llama_index.readers.file import SimpleDirectoryReader

        p = Path(path)
        if not p.exists():
            self._logger.error("Path does not exist: %s", path)
            return 0

        reader = SimpleDirectoryReader(
            input_dir=str(p),
            recursive=True,
        )
        documents = reader.load_data()

        parser = MarkdownNodeParser()
        nodes = parser.get_nodes_from_documents(documents)

        if self._index is None:
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=self._vector_store,
                embed_model=self._embed_model,
            )
            await self._index.ainsert_nodes(nodes)
        else:
            await self._index.ainsert_nodes(nodes)

        for node in nodes:
            source = node.metadata.get("file_path", "")
            self._ingestion.record(
                file_path=source or path,
                status="success",
                chunk_count=1,
            )

        return len(nodes)

    async def aindex(self, paths: list[str]) -> int:
        total = 0
        for p in paths:
            total += await self._aindex_dir(p)
        return total

    def get_status(self) -> dict[str, Any]:
        summary = self._ingestion.get_summary()
        return {
            "indexed_files": summary["total_files"],
            "total_chunks": summary["total_chunks"],
            "vector_store_path": self.config.vector_store_path,
            "collection_name": self.config.collection_name,
            "embedding_model": self.config.embedding_model,
        }

    def start_watcher(self, paths: list[str]) -> None:
        self._watcher.start(
            paths=paths,
            on_created=self._on_file_created,
            on_modified=self._on_file_modified,
            on_deleted=self._on_file_deleted,
        )

    def stop_watcher(self) -> None:
        self._watcher.stop()

    def _on_file_created(self, path: str) -> None:
        self._logger.info("[watcher] triggering reindex: %s", path)
        try:
            asyncio.run(self._aindex_dir(str(Path(path).parent)))
        except Exception as exc:
            self._logger.error("[watcher] reindex failed: %s", exc)

    def _on_file_modified(self, path: str) -> None:
        parent = Path(path).parent
        if self._ingestion.has_changed(path):
            self._logger.info("[watcher] triggering reindex: %s", path)
            try:
                asyncio.run(self._aindex_dir(str(parent)))
            except Exception as exc:
                self._logger.error("[watcher] reindex failed: %s", exc)
        else:
            self._logger.debug("[watcher] file unchanged, skipping: %s", path)

    def _on_file_deleted(self, path: str) -> None:
        self._logger.info("[watcher] file deleted: %s", path)
        self._ingestion.remove(path)

    def close(self) -> None:
        self.stop_watcher()
        if self._ingestion_db is not None:
            self._ingestion_db.close()
            self._ingestion_db = None
        if hasattr(self._embed_model, "close"):
            self._embed_model.close()


def create_mcp_server(
    config: RAGConfig,
    engine: RAGEngine | None = None,
) -> FastMCP:
    if engine is None:
        engine = RAGEngine(config)

    mcp = FastMCP("rag-server")

    @mcp.tool(description=RAG_SEARCH_DESCRIPTION)  # type: ignore[untyped-decorator]
    async def rag_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        logger = get_logger("rag_mcp_server")
        logger.info("rag_search started: query=%s, top_k=%d", query, top_k)

        if not query or not query.strip():
            return []

        try:
            results = await engine.search(query, top_k)
            logger.info("rag_search completed: results=%d", len(results))
            return results
        except Exception as exc:
            logger.error("rag_search failed: %s", exc)
            raise

    @mcp.tool(description=RAG_INDEX_DESCRIPTION)  # type: ignore[untyped-decorator]
    async def rag_index(paths: list[str]) -> int:
        logger = get_logger("rag_mcp_server")
        logger.info("rag_index started: paths=%s", paths)

        if not paths:
            return 0

        try:
            count = await engine.aindex(paths)
            logger.info("rag_index completed: indexed=%d", count)
            return count
        except Exception as exc:
            logger.error("rag_index failed: %s", exc)
            raise

    @mcp.tool(description=RAG_STATUS_DESCRIPTION)  # type: ignore[untyped-decorator]
    async def rag_status() -> dict[str, Any]:
        return engine.get_status()

    @mcp.tool(description=RAG_WATCH_DESCRIPTION)  # type: ignore[untyped-decorator]
    async def rag_watch(paths: list[str], enabled: bool) -> dict[str, Any]:
        logger = get_logger("rag_mcp_server")
        logger.info("rag_watch: paths=%s, enabled=%s", paths, enabled)

        if enabled:
            engine.start_watcher(paths)
        else:
            engine.stop_watcher()

        return {
            "enabled": enabled,
            "paths": engine._watcher.watched_paths if enabled else [],
        }

    return mcp
