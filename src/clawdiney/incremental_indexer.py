"""
Incremental indexing with state tracking for Clawdiney.

Tracks file hashes to only re-index changed files.
State is persisted to .clawdiney_state.json in the vault root.
"""

import hashlib
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
from neo4j import GraphDatabase

from .config import Config
from .indexer import (
    build_note_record,
    discover_vault_files,
    sync_graph,
)

logger = logging.getLogger(__name__)

STATE_FILE = ".clawdiney_state.json"
STATE_SCHEMA_VERSION = 1


class IncrementalIndexer:
    """Manages incremental indexing with state persistence."""

    def __init__(self, vault_root: Path):
        self.vault_root = vault_root
        self.state_path = vault_root / STATE_FILE
        self.state: dict[str, Any] = {
            "schema_version": STATE_SCHEMA_VERSION,
            "files": {},
            "last_full_sync": None,
        }
        self._load_state()

    def _load_state(self) -> None:
        """Load state from disk if exists."""
        if self.state_path.exists():
            try:
                with open(self.state_path, encoding="utf-8") as f:
                    loaded = json.load(f)

                # Handle schema versioning
                version = loaded.get("schema_version", 1)
                if version > STATE_SCHEMA_VERSION:
                    logger.warning(
                        f"State file has newer schema version {version} "
                        f"(this version supports up to {STATE_SCHEMA_VERSION}). "
                        f"Attempting to load anyway."
                    )
                elif version < STATE_SCHEMA_VERSION:
                    logger.info(
                        f"Upgrading state schema from v{version} to v{STATE_SCHEMA_VERSION}"
                    )
                    loaded = self._upgrade_state(loaded, version)

                self.state = loaded
                logger.info(f"Loaded state from {self.state_path} (schema v{version})")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load state: {e}. Starting fresh.")
        else:
            logger.info("No existing state found. Will perform full sync.")

    def _save_state(self) -> None:
        """Persist state to disk atomically using temp file + rename."""
        # Ensure schema version is always set
        self.state["schema_version"] = STATE_SCHEMA_VERSION

        # Write to temp file first for atomicity
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp", dir=self.state_path.parent, prefix=".state_"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
            # Atomic rename
            Path(temp_path).replace(self.state_path)
            logger.debug(f"Saved state atomically to {self.state_path}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            # Cleanup temp file on failure
            Path(temp_path).unlink(missing_ok=True)
            raise

    def _upgrade_state(
        self, state: dict[str, Any], from_version: int
    ) -> dict[str, Any]:
        """Upgrade state schema from older version to current."""
        upgraded = state.copy()

        # v1 -> v2: (future upgrades go here)
        # Example:
        # if from_version < 2:
        #     upgraded["new_field"] = "default"

        # For now, just ensure base fields exist
        if "files" not in upgraded:
            upgraded["files"] = {}
        if "last_full_sync" not in upgraded:
            upgraded["last_full_sync"] = None

        return upgraded

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _get_all_vault_files(self) -> dict[Path, str]:
        """Get all markdown files with their current hashes."""
        files = {}
        for file_path in discover_vault_files(self.vault_root):
            try:
                files[file_path] = self._compute_file_hash(file_path)
            except OSError as e:
                logger.warning(f"Could not read {file_path}: {e}")
        return files

    def detect_changes(self) -> tuple[list[Path], list[Path]]:
        """
        Detect new and modified files since last sync.

        Returns:
            Tuple of (new_or_modified_files, deleted_files)
        """
        current_files = self._get_all_vault_files()
        stored_files = self.state.get("files", {})

        new_or_modified = []
        for file_path, current_hash in current_files.items():
            stored_hash = stored_files.get(str(file_path))
            if stored_hash != current_hash:
                new_or_modified.append(file_path)

        deleted = []
        for stored_path in stored_files.keys():
            if stored_path not in current_files:
                deleted.append(Path(stored_path))

        return new_or_modified, deleted

    def update_state(self, file_path: Path, file_hash: str | None = None) -> None:
        """Update state for a single file (add/update or remove)."""
        if file_hash is not None:
            self.state["files"][str(file_path)] = file_hash
        else:
            self.state["files"].pop(str(file_path), None)
        self._save_state()

    def mark_all_synced(self, files: dict[Path, str]) -> None:
        """Mark all files as synced in state."""
        self.state["files"] = {str(path): hash for path, hash in files.items()}
        self._save_state()

    def sync_file(
        self,
        file_path: Path,
        collection: chromadb.Collection,
        neo4j_driver: GraphDatabase,
        strategy: str | None = None,
    ) -> bool:
        """
        Sync a single file to both ChromaDB and Neo4j.

        Returns True if successful, False otherwise.
        """
        try:
            note_record = build_note_record(
                file_path, self.vault_root, strategy=strategy
            )
            if note_record is None:
                logger.warning(f"Skipping empty file: {file_path.name}")
                self.update_state(file_path, None)  # Remove from state
                return False

            # Index in ChromaDB
            from brain_indexer import build_chunk_payload

            ids, documents, metadatas = build_chunk_payload(note_record)
            if ids:
                collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

            # Sync to Neo4j (single note, incremental mode)
            sync_graph(neo4j_driver, [note_record], incremental=True)

            # Update state
            file_hash = self._compute_file_hash(file_path)
            self.update_state(file_path, file_hash)

            logger.info(
                f"Synced: {note_record['path']} ({len(note_record['chunks'])} chunks)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to sync {file_path}: {e}")
            return False

    def remove_deleted_from_chroma(
        self, deleted_files: list[Path], collection: chromadb.Collection
    ) -> int:
        """Remove deleted files from ChromaDB. Returns count of deleted chunks."""
        deleted_count = 0
        for file_path in deleted_files:
            relative_path = file_path.relative_to(self.vault_root).as_posix()
            # Delete all chunks with this path
            try:
                # Get all IDs for this file
                existing = collection.get(
                    where={"path": relative_path},
                    include=[],
                )
                if existing["ids"]:
                    collection.delete(ids=existing["ids"])
                    deleted_count += len(existing["ids"])
                    logger.info(
                        f"Removed {len(existing['ids'])} chunks for deleted: {relative_path}"
                    )
            except Exception as e:
                logger.warning(f"Could not delete chunks for {relative_path}: {e}")

            # Remove from state
            self.update_state(file_path, None)

        return deleted_count


def incremental_sync(
    vault_root: Path | str | None = None,
    collection: chromadb.Collection | None = None,
    neo4j_driver: Any | None = None,
    strategy: str | None = None,
    force_full: bool = False,
) -> dict[str, Any]:
    """
    Perform incremental sync of the vault.

    Args:
        vault_root: Path to Obsidian vault
        collection: ChromaDB collection (created if None)
        neo4j_driver: Neo4j driver (created if None)
        strategy: Chunking strategy
        force_full: If True, perform full sync ignoring state

    Returns:
        Summary dict with sync statistics
    """
    from brain_indexer import (
        create_chroma_client,
        create_collection,
        create_neo4j_driver,
    )

    vault_root = Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
    own_collection = collection is None
    own_driver = neo4j_driver is None

    if own_collection:
        chroma_client = create_chroma_client()
        collection = create_collection(chroma_client)
    if own_driver:
        neo4j_driver = create_neo4j_driver()

    indexer = IncrementalIndexer(vault_root)

    if force_full:
        logger.info("Force full sync requested")
        changes_dict: dict[Path, str] = indexer._get_all_vault_files()
        changes: list[Path] = list(changes_dict.keys())
        deleted: list[Path] = []
        is_full_sync = True
    else:
        new_or_modified, deleted = indexer.detect_changes()
        changes = new_or_modified
        is_full_sync = False

    logger.info(f"Detected {len(changes)} new/modified files, {len(deleted)} deleted")

    # Process changes
    synced_files = 0
    indexed_chunks = 0

    for file_path in changes:
        if indexer.sync_file(file_path, collection, neo4j_driver, strategy=strategy):
            synced_files += 1
            # Count chunks
            note_record = build_note_record(file_path, vault_root, strategy=strategy)
            if note_record:
                indexed_chunks += len(note_record["chunks"])

    # Remove deleted files
    if deleted:
        deleted_chunks = indexer.remove_deleted_from_chroma(deleted, collection)
        logger.info(f"Removed {deleted_chunks} chunks from deleted files")

    # If this was a full sync, update state with all files
    if is_full_sync:
        all_files = indexer._get_all_vault_files()
        indexer.mark_all_synced(all_files)
        indexer.state["last_full_sync"] = datetime.now().isoformat()

    indexer._save_state()

    # Cleanup: remove orphan Tag nodes from Neo4j
    with neo4j_driver.session() as session:
        session.run("MATCH (t:Tag) WHERE NOT (t)<-[:HAS_TAG]-() DELETE t")

    return {
        "vault_root": str(vault_root),
        "sync_type": "full" if is_full_sync else "incremental",
        "files_synced": synced_files,
        "files_deleted": len(deleted),
        "indexed_chunks": indexed_chunks,
    }


def full_sync(
    vault_root: Path | str | None = None,
    collection: chromadb.Collection | None = None,
    neo4j_driver: Any | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Perform a full sync of the vault."""
    return incremental_sync(
        vault_root=vault_root,
        collection=collection,
        neo4j_driver=neo4j_driver,
        strategy=strategy,
        force_full=True,
    )
