import logging
import os
import threading
from pathlib import Path

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

        total_synced = sum(
            summary.get("files_synced", 0) for summary in result.values()
        )
        total_deleted = sum(
            summary.get("files_deleted", 0) for summary in result.values()
        )
        total_chunks = sum(
            summary.get("indexed_chunks", 0) for summary in result.values()
        )

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
            if Config.ENABLE_RERANK:
                warm_thread = threading.Thread(target=_warm_up_reranker, daemon=True)
                warm_thread.start()


def _warm_up_reranker() -> None:
    """Load the cross-encoder in the background so first query pays no latency."""
    try:
        from .reranker import get_reranker

        get_reranker().warm_up()
    except Exception as e:
        logger.warning(f"Reranker warm-up failed: {e}")


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
        vault_name = vault or engine.current_vault
        neighbors = engine.storage.expand_neighborhood(note_name, vault_name, depth=1)
        if not neighbors:
            logger.info(f"No connections found for: {note_name}")
            return f"No direct connections found for note: {note_name}"

        lines = []
        for item in neighbors:
            label = item["path"] or item["name"]
            if item["kind"] in ("note", "tag"):
                lines.append(f"- {label}")
            else:
                entry = f"- {item['name']} [{item['kind']}] via {item['rel_type']}"
                if item["confidence"] is not None and item["confidence"] < 1.0:
                    entry += f" (confidence {item['confidence']:.2f})"
                if item["evidence"]:
                    entry += f" — evidence: {item['evidence']}"
                lines.append(entry)
        logger.info(f"Found {len(neighbors)} related entities for: {note_name}")
        return f"Entities connected to {note_name}:\n" + "\n".join(lines)
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
    Check health status of the embedded store (brain.db), Ollama, and the
    optional cross-encoder reranker. Also shows status per configured vault.
    Use this to diagnose issues.
    """
    results = []
    all_healthy = True

    # Check brain.db
    doc_counts: dict[str, int] = {}
    try:
        from .storage import get_storage

        stats = get_storage().stats()
        counts = stats["counts"]
        doc_counts = stats["documents_per_vault"]
        results.append(
            f"brain.db: OK ({stats['db_path']}: {counts['documents']} documents, "
            f"{counts['chunks']} chunks, {counts['entities']} entities, "
            f"{counts['relations']} relations)"
        )
    except Exception as e:
        results.append(f"brain.db: FAILED - {e}")
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

    # Check reranker (optional extra; absence is not unhealthy)
    try:
        from .reranker import get_reranker

        if not Config.ENABLE_RERANK:
            results.append("Reranker: disabled (ENABLE_RERANK=false)")
        elif get_reranker().available:
            results.append("Reranker: OK (cross-encoder loaded)")
        else:
            results.append(
                "Reranker: not loaded (install extra: pip install clawdiney[rerank])"
            )
    except Exception as e:
        results.append(f"Reranker: FAILED - {e}")

    # Per-vault status
    vaults = Config.get_all_vaults()
    results.append(f"\nConfigured Vaults ({len(vaults)}):")
    for vid, vpath in vaults.items():
        engine_status = "cached" if vid in _engine_instances else "not loaded"
        docs = doc_counts.get(vid, 0)
        results.append(
            f"  - {vid}: {vpath.resolve()} [{engine_status}, {docs} documents indexed]"
        )

    status = "All services healthy" if all_healthy else "Some services unhealthy"
    return f"{status}\n\n" + "\n".join(results)


@mcp.tool()
def detect_vault() -> str:
    """
    Detect which vault corresponds to the current working directory.
    Use this to confirm which vault the search/write tools are operating on.
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
        f'Dica: use vault="{vault_id}" explicitamente se precisar forçar um vault específico.'
    )


@mcp.tool()
def get_project_card(name: str, vault: str = None) -> str:
    """
    Retrieve the full project card (Purpose, Stack, Architecture, Interfaces)
    for a project by name. Use this as the first call when working with a
    project you don't know yet.

    Args:
        name: Project name (e.g., "clawdiney")
        vault: Optional vault name (auto-detected from current directory, falls back to default)
    """
    try:
        engine = get_engine(vault=vault)
        logger.info(f"Get project card: {name}")
        candidates = engine.resolve_note(name, vault=vault)
        if not candidates:
            return f"No project card found for '{name}'. No matching notes in vault."
        exact = next(
            (
                c
                for c in candidates
                if c["filename"].lower() in (f"{name.lower()}.md", name.lower())
            ),
            None,
        )
        if exact is None and len(candidates) > 1:
            listing = "\n".join(f"- {c['path']}" for c in candidates[:10])
            return f"No exact card for '{name}'. Closest candidates:\n{listing}"
        card = exact or candidates[0]
        note = engine.get_note_by_path(card["path"], vault=vault)
        return f"Project card: {note['path']}\n\n{note['content']}"
    except Exception as e:
        logger.error(f"get_project_card failed: {e}")
        return f"Error in get_project_card: {str(e)}"


@mcp.tool()
def how_do_projects_relate(project_a: str, project_b: str, vault: str = None) -> str:
    """
    Find how two projects are connected in the knowledge graph: shared
    dependencies, datastores, patterns, or direct API calls. Returns up to
    5 shortest paths with relation types and evidence.

    Args:
        project_a: First project name
        project_b: Second project name
        vault: Optional vault name (auto-detected from current directory, falls back to default)
    """
    try:
        engine = get_engine(vault=vault)
        vault_name = vault or engine.current_vault
        storage = engine.storage

        for label, ref in (("project_a", project_a), ("project_b", project_b)):
            if storage._find_entity_id(vault_name, ref) is None:
                return (
                    f"Unknown entity for {label}: '{ref}'. "
                    f"Run the project indexer first, or check the name with resolve_note."
                )

        paths = storage.find_paths(vault_name, project_a, project_b)
        if not paths:
            return (
                f"No relationship found between '{project_a}' and '{project_b}' "
                f"within 3 hops in the knowledge graph."
            )

        lines = [f"Relationships between {project_a} and {project_b}:"]
        for i, hops in enumerate(paths, 1):
            chain = []
            for hop in hops:
                seg = f"{hop['source']} -{hop['rel_type']}-> {hop['target']} [{hop['target_kind']}]"
                if hop["confidence"] < 1.0:
                    seg += f" (confidence {hop['confidence']:.2f})"
                if hop["evidence"]:
                    seg += f" — evidence: {hop['evidence']}"
                chain.append(seg)
            lines.append(f"{i}. " + " | ".join(chain))
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"how_do_projects_relate failed: {e}")
        return f"Error in how_do_projects_relate: {str(e)}"


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
def add_learning(
    topic: str, content: str, area: str = "SOPs", vault: str = None
) -> str:
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
