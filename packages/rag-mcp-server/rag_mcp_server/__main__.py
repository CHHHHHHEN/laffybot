from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG MCP Server")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="config/settings.yaml",
        help="Path to configuration YAML file",
    )
    parser.add_argument(
        "--sse-host",
        type=str,
        default=None,
        help="SSE server host (overrides config)",
    )
    parser.add_argument(
        "--sse-port",
        type=int,
        default=None,
        help="SSE server port (overrides config)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["sse", "stdio"],
        default="sse",
        help="Transport protocol (default: sse)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (overrides config)",
    )
    args = parser.parse_args()

    from rag_mcp_server.config import load_config as _load_config

    config = _load_config(args.config)

    if args.sse_host is not None:
        config.sse_host = args.sse_host
    if args.sse_port is not None:
        config.sse_port = args.sse_port
    if args.log_level is not None:
        config.log_level = args.log_level

    from rag_mcp_server.logger import setup_logging as _setup_logging

    _setup_logging(
        level=config.log_level,
        log_file=config.log_file,
    )

    logger = _setup_logging("rag_mcp_server")

    _preload_heavy_imports()

    from rag_mcp_server.workflow import RAGEngine
    from rag_mcp_server.workflow import create_mcp_server as _create_mcp_server

    logger.info("Initializing RAG engine...")
    engine = RAGEngine(config)
    mcp = _create_mcp_server(config, engine=engine)

    logger.info(
        "Starting RAG MCP Server: transport=%s host=%s port=%d",
        args.transport,
        config.sse_host,
        config.sse_port,
    )

    try:
        mcp.run(transport=args.transport, host=config.sse_host, port=config.sse_port)
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    finally:
        engine.close()


def _preload_heavy_imports() -> None:
    """Pre-load heavy third-party modules in main thread to avoid import deadlocks.

    MCP SDK uses anyio + background threads for I/O. When a tool handler
    runs asyncio.to_thread(fn), fn executes in a worker thread. If it tries
    to import chromadb (which pulls in onnxruntime, numpy, sqlite3 C extensions),
    that import can deadlock with the stdin-reader thread due to Python's
    global import lock. Pre-importing here avoids the deadlock.
    """
    import importlib

    _heavy_modules = [
        "chromadb",
        "chromadb.config",
        "llama_index.core",
        "llama_index.embeddings.openai",
        "llama_index.vector_stores.chroma",
    ]

    for mod_name in _heavy_modules:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            pass


if __name__ == "__main__":
    main()
