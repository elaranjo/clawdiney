import logging
import os
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from config import Config
from logging_config import setup_logging
from query_engine import BrainQueryEngine

logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP("Clawdiney", port=8006, host="0.0.0.0")

# Thread-safe singleton engine initialization
_engine_lock = threading.Lock()
_engine_instance = None

# Auto-sync state tracking
_auto_sync_started = False
_auto_sync_completed = threading.Event()


def _perform_auto_sync() -> None:
    """
    Perform incremental sync on startup to catch any changes made while MCP was offline.
    Runs in background thread to avoid blocking MCP requests.
    """
    global _auto_sync_started

    try:
        from brain_indexer import (
            create_chroma_client,
            create_collection,
            create_neo4j_driver,
        )
        from incremental_indexer import incremental_sync

        vault_root = Path(Config.VAULT_PATH).expanduser().resolve()
        logger.info(f"Checking for vault changes in: {vault_root}")

        collection = create_collection(create_chroma_client())
        driver = create_neo4j_driver()

        result = incremental_sync(
            vault_root=vault_root,
            collection=collection,
            neo4j_driver=driver,
        )

        if result["files_synced"] > 0 or result["files_deleted"] > 0:
            logger.info(
                f"Auto-sync complete: {result['files_synced']} files synced, "
                f"{result['files_deleted']} deleted, {result['indexed_chunks']} chunks"
            )
        else:
            logger.info("Vault is up to date. No sync needed.")

        driver.close()
    except Exception as e:
        logger.error(f"Auto-sync failed: {e}")
        # Don't re-raise - allow MCP to start even if sync fails
    finally:
        _auto_sync_completed.set()


def _ensure_auto_sync():
    """
    Ensure auto-sync has been started (runs in background if not).
    Does not block - returns immediately.
    """
    global _auto_sync_started

    with _engine_lock:
        if not _auto_sync_started:
            _auto_sync_started = True
            # Run auto-sync in background thread
            sync_thread = threading.Thread(target=_perform_auto_sync, daemon=True)
            sync_thread.start()


def get_engine():
    """
    Thread-safe lazy initialization of BrainQueryEngine.
    Uses double-checked locking to avoid lock contention after initialization.
    Triggers auto-sync in background on first call (non-blocking).
    """
    global _engine_instance

    # Ensure auto-sync is running in background
    _ensure_auto_sync()

    # Fast path - check without lock
    if _engine_instance is not None:
        return _engine_instance

    # Slow path - check with lock
    with _engine_lock:
        if _engine_instance is None:
            try:
                _engine_instance = BrainQueryEngine()
            except Exception as e:
                raise Exception(
                    f"Failed to initialize BrainQueryEngine: {str(e)}"
                ) from e

    return _engine_instance


def _format_candidates(query, candidates):
    if not candidates:
        return f"No notes found for '{query}'."

    lines = [f"Candidates for '{query}':"]
    for candidate in candidates:
        lines.append(f"- {candidate['path']}")
    return "\n".join(lines)


def _format_chunks(chunks):
    if not chunks:
        return "No chunks found."

    lines = [f"Chunks for {chunks[0]['path']}:"]
    for chunk in chunks:
        lines.append(f"- [{chunk['chunk_index']}] {chunk['header']}")
    return "\n".join(lines)


# --- MCP Tools ---


@mcp.tool()
def search_brain(query: str) -> str:
    """
    Search Clawdiney for architectural patterns, SOPs, and design system components.
    Use this whenever you need to verify a standard or find existing implementation patterns.
    """
    try:
        engine = get_engine()
        logger.info(
            f"Search query: {query[:50]}..."
            if len(query) > 50
            else f"Search query: {query}"
        )
        return f"Brain Search Results for '{query}':\n\n{engine.query(query)}"
    except Exception as e:
        logger.error(f"search_brain failed: {e}")
        return f"Error in search_brain: {str(e)}"


@mcp.tool()
def explore_graph(note_name: str) -> str:
    """
    Explore the knowledge graph to find notes related to a specific topic.
    Returns a list of connected notes via:
    - Direct wikilinks: (:Note)-[:LINKS_TO]->(:Note)
    - Shared tags: (:Note)-[:HAS_TAG]->(:Tag)<-[:HAS_TAG]-(:Note)

    The tag-based approach scales O(n) instead of O(n²) for large vaults.
    """
    try:
        engine = get_engine()
        logger.info(f"Explore graph: {note_name}")
        related = engine.get_related_notes(note_name)
        if not related:
            logger.info(f"No connections found for: {note_name}")
            return f"No direct connections found for note: {note_name}"
        logger.info(f"Found {len(related)} related notes for: {note_name}")
        return f"Notes connected to {note_name}:\n" + "\n".join(
            [f"- {r}" for r in related]
        )
    except Exception as e:
        logger.error(f"explore_graph failed: {e}")
        return f"Error in explore_graph: {str(e)}"


@mcp.tool()
def resolve_note(name: str) -> str:
    """
    Resolve a note name to canonical vault-relative paths.
    Use this when search_brain surfaces a relevant note but the name is ambiguous.
    """
    try:
        engine = get_engine()
        logger.info(f"Resolve note: {name}")
        return _format_candidates(name, engine.resolve_note(name))
    except Exception as e:
        logger.error(f"resolve_note failed: {e}")
        return f"Error in resolve_note: {str(e)}"


@mcp.tool()
def get_note_chunks(filename: str) -> str:
    """
    List chunk headers for a note.
    Use this after resolve_note when you want a structured preview without reading the full file.
    """
    try:
        engine = get_engine()
        logger.info(f"Get chunks: {filename}")
        return _format_chunks(engine.get_note_chunks(filename))
    except Exception as e:
        logger.error(f"get_note_chunks failed: {e}")
        return f"Error in get_note_chunks: {str(e)}"


@mcp.tool()
def health_check() -> str:
    """
    Check health status of all backend services (ChromaDB, Neo4j, Ollama).
    Use this to diagnose connection issues.
    """
    results = []
    all_healthy = True

    # Check ChromaDB
    try:
        from brain_indexer import create_chroma_client, create_collection
        client = create_chroma_client()
        collection = create_collection(client)
        count = collection.count()
        results.append(f"✅ ChromaDB: OK ({count} vectors)")
    except Exception as e:
        results.append(f"❌ ChromaDB: FAILED - {e}")
        all_healthy = False

    # Check Neo4j
    try:
        from brain_indexer import create_neo4j_driver
        driver = create_neo4j_driver()
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as count")
            count = result.single()["count"]
        driver.close()
        results.append(f"✅ Neo4j: OK ({count} nodes)")
    except Exception as e:
        results.append(f"❌ Neo4j: FAILED - {e}")
        all_healthy = False

    # Check Ollama
    try:
        import ollama
        client = ollama.Client()
        models = client.list()
        model_count = len(models.get("models", []))
        results.append(f"✅ Ollama: OK ({model_count} models)")
    except Exception as e:
        results.append(f"❌ Ollama: FAILED - {e}")
        all_healthy = False

    status = "✅ All services healthy" if all_healthy else "⚠️ Some services unhealthy"
    return f"{status}\n\n" + "\n".join(results)


if __name__ == "__main__":
    import signal
    import sys

    setup_logging()

    # Validate Ollama models on startup
    logger.info("Validating Ollama models...")
    ollama_warnings = Config.validate_ollama_models()
    if ollama_warnings:
        for warning in ollama_warnings:
            logger.warning(warning)
    else:
        logger.info("Ollama models validated successfully")

    def cleanup(signum=None, frame=None):
        """Clean up resources on shutdown."""
        logger.info("Shutting down MCP server...")
        if _engine_instance is not None:
            _engine_instance.close()
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mount_path = os.environ.get("MCP_MOUNT_PATH")
    logger.info(f"Starting MCP server with transport={transport}")
    # mount_path is optional, only pass if set
    run_kwargs = {"transport": transport}  # type: ignore[arg-type]
    if mount_path:
        run_kwargs["mount_path"] = mount_path
    mcp.run(**run_kwargs)  # type: ignore[arg-type]
