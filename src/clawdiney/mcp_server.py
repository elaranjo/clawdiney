import logging
import os
import threading
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import Config
from .logging_config import setup_logging
from .query_engine import BrainQueryEngine

logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP("Clawdiney", port=8006, host="0.0.0.0")

# Thread-safe per-vault engine cache
_engine_lock = threading.Lock()
_engine_instances: dict[str, BrainQueryEngine] = {}

# Auto-sync state tracking
_auto_sync_started = False
_auto_sync_completed = threading.Event()


def _perform_auto_sync() -> None:
    """
    Perform incremental sync on startup to catch any changes made while MCP was offline.
    Syncs all configured vaults. Runs in background thread to avoid blocking MCP requests.
    """
    global _auto_sync_started

    try:
        from .incremental_indexer import incremental_sync_all_vaults

        vaults = Config.get_all_vaults()
        logger.info(f"Checking for vault changes in {len(vaults)} vault(s)...")

        result = incremental_sync_all_vaults()

        total_synced = result.get("files_synced", 0)
        total_deleted = result.get("files_deleted", 0)
        total_chunks = result.get("indexed_chunks", 0)

        if total_synced > 0 or total_deleted > 0:
            logger.info(
                f"Auto-sync complete: {total_synced} files synced, "
                f"{total_deleted} deleted, {total_chunks} chunks"
            )
        else:
            logger.info("All vaults are up to date. No sync needed.")
    except Exception as e:
        logger.error(f"Auto-sync failed: {e}")
    finally:
        _auto_sync_completed.set()


def _ensure_auto_sync():
    global _auto_sync_started
    with _engine_lock:
        if not _auto_sync_started:
            _auto_sync_started = True
            sync_thread = threading.Thread(target=_perform_auto_sync, daemon=True)
            sync_thread.start()



def _detect_vault_from_cwd() -> str | None:
    """Detecta o vault correspondente ao diretório de trabalho atual."""
    cwd = Path.cwd().resolve()
    vaults = Config.get_all_vaults()
    parts = list(cwd.parts)
    for part in reversed(parts):
        if part in vaults:
            logger.info(f"Vault autodetected from CWD: '{part}' (cwd={cwd})")
            return part
    return None


def get_engine(vault: str | None = None) -> BrainQueryEngine:
    """
    Thread-safe lazy initialization of BrainQueryEngine per vault.
    Uses double-checked locking to avoid lock contention after initialization.
    Triggers auto-sync in background on first call (non-blocking).

    When vault=None: auto-detects vault from current working directory,
    falling back to default vault if no match found.
    """
    global _engine_instances

    if vault is None:
        vault_id = _detect_vault_from_cwd() or Config.get_default_vault()
    else:
        vault_id = vault

    _ensure_auto_sync()

    if vault_id in _engine_instances:
        return _engine_instances[vault_id]

    with _engine_lock:
        if vault_id not in _engine_instances:
            try:
                _engine_instances[vault_id] = BrainQueryEngine(vault=vault_id)
            except Exception as e:
                raise Exception(
                    f"Failed to initialize BrainQueryEngine for vault '{vault_id}': {str(e)}"
                ) from e

    return _engine_instances[vault_id]


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
def search_brain(query: str, vault: str = None) -> str:
    """
    Search Clawdiney for architectural patterns, SOPs, and design system components.
    Use this whenever you need to verify a standard or find existing implementation patterns.

    Args:
        query: Search query
        vault: Optional vault name to scope the search (auto-detected from current directory, falls back to default)
    """
    try:
        engine = get_engine(vault=vault)
        logger.info(
            f"Search query: {query[:50]}..."
            if len(query) > 50
            else f"Search query: {query}"
        )
        vault_label = engine.current_vault
        return f"Brain Search Results for '{query}' [vault: {vault_label}]:\n\n{engine.query(query, vault_override=vault)}"
    except Exception as e:
        logger.error(f"search_brain failed: {e}")
        return f"Error in search_brain: {str(e)}"


@mcp.tool()
def explore_graph(note_name: str, vault: str = None) -> str:
    """
    Explore the knowledge graph to find notes related to a specific topic.
    Returns a list of connected notes via:
    - Direct wikilinks: (:Note)-[:LINKS_TO]->(:Note)
    - Shared tags: (:Note)-[:HAS_TAG]->(:Tag)<-[:HAS_TAG]-(:Note)

    Args:
        note_name: Name of the note to explore
        vault: Optional vault name (auto-detected from current directory, falls back to default)
    """
    try:
        engine = get_engine(vault=vault)
        logger.info(f"Explore graph: {note_name}")
        related = engine.get_related_notes(note_name, vault=vault)
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
def resolve_note(name: str, vault: str = None) -> str:
    """
    Resolve a note name to canonical vault-relative paths.
    Use this when search_brain surfaces a relevant note but the name is ambiguous.

    Args:
        name: Note name or path fragment to resolve
        vault: Optional vault name (auto-detected from current directory, falls back to default)
    """
    try:
        engine = get_engine(vault=vault)
        logger.info(f"Resolve note: {name}")
        return _format_candidates(name, engine.resolve_note(name, vault=vault))
    except Exception as e:
        logger.error(f"resolve_note failed: {e}")
        return f"Error in resolve_note: {str(e)}"


@mcp.tool()
def get_note_chunks(filename: str, vault: str = None) -> str:
    """
    List chunk headers for a note.
    Use this after resolve_note when you want a structured preview without reading the full file.

    Args:
        filename: Note filename or path
        vault: Optional vault name (auto-detected from current directory, falls back to default)
    """
    try:
        engine = get_engine(vault=vault)
        logger.info(f"Get chunks: {filename}")
        return _format_chunks(engine.get_note_chunks(filename))
    except Exception as e:
        logger.error(f"get_note_chunks failed: {e}")
        return f"Error in get_note_chunks: {str(e)}"


@mcp.tool()
def health_check() -> str:
    """
    Check health status of all backend services (ChromaDB, Neo4j, Ollama).
    Also shows status per configured vault.
    Use this to diagnose connection issues.
    """
    results = []
    all_healthy = True

    # Check ChromaDB
    try:
        from .indexer import create_chroma_client, create_collection

        client = create_chroma_client()
        collection = create_collection(client)
        count = collection.count()
        results.append(f"ChromaDB: OK ({count} vectors)")
    except Exception as e:
        results.append(f"ChromaDB: FAILED - {e}")
        all_healthy = False

    # Check Neo4j
    try:
        from .indexer import create_neo4j_driver

        driver = create_neo4j_driver()
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as count")
            count = result.single()["count"]
        driver.close()
        results.append(f"Neo4j: OK ({count} nodes)")
    except Exception as e:
        results.append(f"Neo4j: FAILED - {e}")
        all_healthy = False

    # Check Ollama
    try:
        import ollama

        client = ollama.Client()
        models = client.list()
        model_count = len(models.get("models", []))
        results.append(f"Ollama: OK ({model_count} models)")
    except Exception as e:
        results.append(f"Ollama: FAILED - {e}")
        all_healthy = False

    # Per-vault status
    vaults = Config.get_all_vaults()
    results.append(f"\nConfigured Vaults ({len(vaults)}):")
    for vid, vpath in vaults.items():
        engine_status = "cached" if vid in _engine_instances else "not loaded"
        results.append(f"  - {vid}: {vpath.resolve()} [{engine_status}]")

    status = "All services healthy" if all_healthy else "Some services unhealthy"
    return f"{status}\n\n" + "\n".join(results)



@mcp.tool()
def detect_vault() -> str:
    """
    Detecta qual vault corresponde ao diretório de trabalho atual.
    Use para confirmar em qual vault as ferramentas de busca/escrita estão operando.
    """
    vault_id = _detect_vault_from_cwd() or Config.get_default_vault()
    vaults = Config.get_all_vaults()
    vpath = vaults.get(vault_id, "unknown")

    try:
        from .vault_config import load_vault_config
        vc = load_vault_config(Path(str(vpath)))
        linked = vc.linked_vaults if vc.linked_vaults else []
    except Exception:
        linked = []

    cwd = os.getcwd()
    linked_str = ", ".join(linked) if linked else "nenhum (isolado)"

    return (
        f"Diretório atual: {cwd}\n"
        f"Vault detectado: {vault_id}\n"
        f"Vaults linkados (fallback): {linked_str}\n"
        f"Total de vaults disponíveis: {len(vaults)}\n\n"
        f"Dica: use vault=\"{vault_id}\" explicitamente se precisar forçar um vault específico."
    )


# --- MCP Write Tools ---


@mcp.tool()
def write_note(path: str, content: str, mode: str = "create", vault: str = None) -> str:
    """
    Create or update a note in the Obsidian vault.

    Args:
        path: Vault-relative path (e.g., "30_Resources/SOPs/SOP_NewPattern.md")
        content: Markdown content to write
        mode: "create" (fail if exists), "overwrite" (replace), or "append" (add to end)
        vault: Optional vault name (auto-detected from current directory, falls back to default)

    Examples:
        write_note("30_Resources/SOPs/SOP_MyPattern.md", "# SOP\\n\\nContent here")
        write_note("10_Projects/Project_X.md", "\\n## Update\\n- Progress", mode="append")
    """
    try:
        from .vault_writer import get_writer

        writer = get_writer(vault_name=vault)
        result = writer.write_note(path, content, mode)

        if result["success"]:
            chunks = result.get("chunks_indexed", 0)
            return f"Note written: {result['message']}\\nIndexed {chunks} chunks."
        else:
            return f"Error: {result['message']}"
    except Exception as e:
        logger.error(f"write_note failed: {e}")
        return f"Error in write_note: {str(e)}"


@mcp.tool()
def append_to_daily(content: str, vault: str = None) -> str:
    """
    Append content to today's daily note (50_Daily/YYYY-MM-DD.md).
    Creates the file if it doesn't exist.

    Args:
        content: Markdown content to append
        vault: Optional vault name (auto-detected from current directory, falls back to default)

    Examples:
        append_to_daily("## Meeting Notes\\n- Discussed X\\n- Decided Y")
        append_to_daily("## Learnings\\n- New pattern discovered")
    """
    try:
        from .vault_writer import get_writer

        writer = get_writer(vault_name=vault)
        result = writer.append_to_daily(content)

        if result["success"]:
            return f"Daily note updated: {result['message']}"
        else:
            return f"Error: {result['message']}"
    except Exception as e:
        logger.error(f"append_to_daily failed: {e}")
        return f"Error in append_to_daily: {str(e)}"


@mcp.tool()
def add_learning(topic: str, content: str, area: str = "SOPs", vault: str = None) -> str:
    """
    Save a learning or insight to the appropriate vault location.

    Automatically determines the best folder based on the area parameter.

    Args:
        topic: Short topic name (becomes filename, e.g., "Backend_Pattern")
        content: Learning content in markdown format
        area: Category folder: "SOPs", "Architecture", "DesignSystem", "Projects", "Areas", "Learnings"
        vault: Optional vault name (auto-detected from current directory, falls back to default)

    Examples:
        add_learning("Backend_Pattern", "# SOP\\n\\nStandard backend pattern...", area="SOPs")
        add_learning("Microservice_X", "## Architecture Decision\\n\\nChose X because...", area="Architecture")
    """
    area_folders = {
        "SOPs": "30_Resources/SOPs",
        "Architecture": "30_Resources/Architecture",
        "DesignSystem": "30_Resources/DesignSystem",
        "Projects": "10_Projects",
        "Areas": "20_Areas",
        "Learnings": "30_Resources/Learnings",
    }

    folder = area_folders.get(area, "30_Resources/Learnings")
    note_path = f"{folder}/{topic}.md"

    try:
        from .vault_writer import get_writer

        writer = get_writer(vault_name=vault)
        result = writer.write_note(note_path, content, mode="create")

        if result["success"]:
            chunks = result.get("chunks_indexed", 0)
            return (
                f"Learning saved to {note_path}\\n"
                f"Indexed {chunks} chunks.\\n\\n"
                f"You can now search for this content with search_brain()."
            )
        else:
            return f"Error: {result['message']}"
    except Exception as e:
        logger.error(f"add_learning failed: {e}")
        return f"Error in add_learning: {str(e)}"


@mcp.tool()
def delete_note(path: str, vault: str = None) -> str:
    """
    Delete a note from the vault and remove it from the index.

    Args:
        path: Vault-relative path (e.g., "30_Resources/SOPs/Old_SOP.md")
        vault: Optional vault name (auto-detected from current directory, falls back to default)

    Examples:
        delete_note("30_Resources/SOPs/Deprecated_Pattern.md")
    """
    try:
        from .vault_writer import get_writer

        writer = get_writer(vault_name=vault)
        result = writer.delete_note(path)

        if result["success"]:
            return f"Note deleted: {result['message']}"
        else:
            return f"Error: {result['message']}"
    except Exception as e:
        logger.error(f"delete_note failed: {e}")
        return f"Error in delete_note: {str(e)}"


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
        global _engine_instances
        for vid, engine in _engine_instances.items():
            logger.info(f"Closing engine for vault: {vid}")
            engine.close()
        _engine_instances.clear()
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mount_path = os.environ.get("MCP_MOUNT_PATH")
    logger.info(f"Starting MCP server with transport={transport}")
    run_kwargs = {"transport": transport}
    if mount_path:
        run_kwargs["mount_path"] = mount_path
    mcp.run(**run_kwargs)
