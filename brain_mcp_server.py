import logging
import os
import threading

from mcp.server.fastmcp import FastMCP

from logging_config import setup_logging
from query_engine import BrainQueryEngine

logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP("Clawdiney", port=8006, host="0.0.0.0")

# Thread-safe singleton engine initialization
_engine_lock = threading.Lock()
_engine_instance = None


def get_engine():
    """
    Thread-safe lazy initialization of BrainQueryEngine.
    Uses double-checked locking to avoid lock contention after initialization.
    """
    global _engine_instance

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
    Returns a list of connected notes based on [[WikiLinks]].
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


if __name__ == "__main__":
    import signal
    import sys

    setup_logging()

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
