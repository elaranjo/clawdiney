"""
Vault Writer module for Clawdiney.

Provides thread-safe write operations with automatic re-indexing.
"""

import logging
import tempfile
from pathlib import Path
from typing import TypedDict

import chromadb
from neo4j import GraphDatabase

from .incremental_indexer import IncrementalIndexer

logger = logging.getLogger(__name__)


class WriteResult(TypedDict):
    """Result of a write operation."""

    success: bool
    path: str
    message: str
    chunks_indexed: int | None


class VaultWriter:
    """Thread-safe vault writer with automatic re-indexing."""

    def __init__(
        self,
        vault_root: Path,
        collection: chromadb.Collection | None = None,
        neo4j_driver: GraphDatabase | None = None,
    ):
        self.vault_root = vault_root
        self.indexer = IncrementalIndexer(vault_root)
        self._collection = collection
        self._neo4j_driver = neo4j_driver

    def _get_collection(self) -> chromadb.Collection:
        """Get or create ChromaDB collection."""
        if self._collection is None:
            from .indexer import create_chroma_client, create_collection

            self._collection = create_collection(create_chroma_client())
        return self._collection

    def _get_neo4j_driver(self) -> GraphDatabase:
        """Get or create Neo4j driver."""
        if self._neo4j_driver is None:
            from .indexer import create_neo4j_driver

            self._neo4j_driver = create_neo4j_driver()
        return self._neo4j_driver

    def _validate_path(self, path: str) -> Path:
        """
        Validate and resolve vault-relative path.

        Security: Resolves symlinks and verifies final path is inside vault.
        Prevents symlink attacks where a symlink inside vault points outside.

        Raises ValueError if path is outside vault or invalid.
        """
        if not path:
            raise ValueError("Path cannot be empty")

        if path.startswith("/") or path.startswith(".."):
            raise ValueError(f"Path must be vault-relative: {path}")

        # Resolve to absolute path (follows symlinks)
        absolute_path = (self.vault_root / path).resolve()

        # Security: Ensure resolved path is inside vault (prevents symlink attacks)
        try:
            absolute_path.relative_to(self.vault_root)
        except ValueError:
            raise ValueError(
                f"Path outside vault after resolution: {path} -> {absolute_path}"
            )

        return absolute_path

    def _atomic_write(self, path: Path, content: str) -> None:
        """Write content atomically using temp file + rename."""
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp", dir=path.parent, prefix=".write_"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
            # Atomic rename
            Path(temp_path).replace(path)
        except Exception:
            # Cleanup temp file on failure
            Path(temp_path).unlink(missing_ok=True)
            raise

    def write_note(self, path: str, content: str, mode: str = "create") -> WriteResult:
        """
        Create or update a note in the vault.

        Args:
            path: Vault-relative path (e.g., "30_Resources/SOPs/SOP_New.md")
            content: Markdown content
            mode: "create" (fail if exists), "overwrite" (replace), "append" (add to end)

        Returns:
            WriteResult with success status and metadata
        """
        try:
            absolute_path = self._validate_path(path)

            # Check mode
            if mode == "create" and absolute_path.exists():
                return WriteResult(
                    success=False,
                    path=path,
                    message=f"File already exists: {path}",
                    chunks_indexed=None,
                )

            # Read existing content for append mode
            if mode == "append" and absolute_path.exists():
                existing = absolute_path.read_text(encoding="utf-8")
                content = existing + "\n\n" + content

            # Write atomically
            self._atomic_write(absolute_path, content)
            logger.info(f"Written: {path} ({len(content)} chars)")

            # Re-index
            collection = self._get_collection()
            driver = self._get_neo4j_driver()

            if self.indexer.sync_file(absolute_path, collection, driver):
                chunks_indexed = len(
                    self.indexer._get_all_vault_files().get(absolute_path, "")
                )
                return WriteResult(
                    success=True,
                    path=path,
                    message=f"Note written and indexed: {path}",
                    chunks_indexed=chunks_indexed,
                )
            else:
                return WriteResult(
                    success=True,
                    path=path,
                    message=f"Note written but indexing failed: {path}",
                    chunks_indexed=0,
                )

        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return WriteResult(
                success=False, path=path, message=f"Invalid path: {e}", chunks_indexed=0
            )
        except Exception as e:
            logger.error(f"Write failed: {e}")
            return WriteResult(
                success=False, path=path, message=f"Write error: {e}", chunks_indexed=0
            )

    def append_to_daily(self, content: str, date: str | None = None) -> WriteResult:
        """
        Append content to today's daily note.

        Args:
            content: Markdown content to append
            date: Optional date in YYYY-MM-DD format (defaults to today)

        Returns:
            WriteResult with success status
        """
        from datetime import date as dt_module

        if date is None:
            date = dt_module.today().isoformat()

        path = f"50_Daily/{date}.md"
        return self.write_note(path, content, mode="append")

    def delete_note(self, path: str) -> WriteResult:
        """
        Delete a note from the vault.

        Args:
            path: Vault-relative path

        Returns:
            WriteResult with success status
        """
        try:
            absolute_path = self._validate_path(path)

            if not absolute_path.exists():
                return WriteResult(
                    success=False,
                    path=path,
                    message=f"File not found: {path}",
                    chunks_indexed=None,
                )

            # Remove from ChromaDB first
            collection = self._get_collection()
            relative_path = absolute_path.relative_to(self.vault_root).as_posix()

            try:
                existing = collection.get(where={"path": relative_path}, include=[])
                if existing["ids"]:
                    collection.delete(ids=existing["ids"])
                    logger.info(f"Removed {len(existing['ids'])} chunks from ChromaDB")
            except Exception as e:
                logger.warning(f"Could not delete from ChromaDB: {e}")

            # Delete file
            absolute_path.unlink()
            logger.info(f"Deleted: {path}")

            # Update state
            self.indexer.update_state(absolute_path, None)

            return WriteResult(
                success=True,
                path=path,
                message=f"Note deleted: {path}",
                chunks_indexed=None,
            )

        except ValueError as e:
            return WriteResult(
                success=False, path=path, message=f"Invalid path: {e}", chunks_indexed=0
            )
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return WriteResult(
                success=False, path=path, message=f"Delete error: {e}", chunks_indexed=0
            )


# Global singleton for MCP server
_writer_lock = None
_writer_instance = None


def get_writer(
    vault_root: Path | None = None,
    collection: chromadb.Collection | None = None,
    neo4j_driver: GraphDatabase | None = None,
) -> VaultWriter:
    """
    Thread-safe singleton for VaultWriter.

    Args:
        vault_root: Optional vault path (uses Config.VAULT_PATH if None)
        collection: Optional ChromaDB collection (created if None)
        neo4j_driver: Optional Neo4j driver (created if None)
    """
    global _writer_lock, _writer_instance

    import threading

    if _writer_lock is None:
        _writer_lock = threading.Lock()

    with _writer_lock:
        if _writer_instance is None:
            from config import Config

            vault_root = Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
            _writer_instance = VaultWriter(vault_root, collection, neo4j_driver)
            logger.info("VaultWriter initialized")

        return _writer_instance
