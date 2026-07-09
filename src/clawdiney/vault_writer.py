"""
Vault Writer module for Clawdiney.

Provides thread-safe write operations with automatic re-indexing into
the embedded SQLite store.
"""

import logging
import tempfile
import threading
from pathlib import Path
from typing import TypedDict

from .incremental_indexer import IncrementalIndexer
from .storage import BrainStorage

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
        storage: BrainStorage | None = None,
        vault_name: str | None = None,
    ):
        self.vault_root = vault_root
        self.vault_name = vault_name or "default"
        self.indexer = IncrementalIndexer(
            vault_root, vault_name=self.vault_name, storage=storage
        )

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

    def write_note(
        self,
        path: str,
        content: str,
        mode: str = "create",
        agent_id: str = "default",
    ) -> WriteResult:
        """
        Create or update a note in the vault.

        Args:
            path: Vault-relative path (e.g., "30_Resources/SOPs/SOP_New.md")
            content: Markdown content
            mode: "create" (fail if exists), "overwrite" (replace), "append" (add to end)
            agent_id: owning namespace for the indexed document (see
                BrainStorage.upsert_note); defaults to "default"

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
            relative_path = absolute_path.relative_to(self.vault_root).as_posix()
            try:
                chunks_indexed = self.indexer.sync_file(
                    relative_path, agent_id=agent_id
                )
                return WriteResult(
                    success=True,
                    path=path,
                    message=f"Note written and indexed: {path}",
                    chunks_indexed=chunks_indexed,
                )
            except Exception as e:
                logger.error(f"Indexing failed for {path}: {e}")
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
        Delete a note from the vault and remove it from the index.

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

            relative_path = absolute_path.relative_to(self.vault_root).as_posix()

            # Delete file first, then remove from index
            absolute_path.unlink()
            logger.info(f"Deleted: {path}")

            try:
                removed = self.indexer.storage.delete_note(
                    self.vault_name, relative_path
                )
                logger.info(f"Removed {removed} chunks from index")
            except Exception as e:
                logger.warning(f"Could not remove from index: {e}")

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
_writer_lock = threading.Lock()
_writer_instances: dict[str, VaultWriter] = {}


def get_writer(
    vault_root: Path | None = None,
    storage: BrainStorage | None = None,
    vault_name: str | None = None,
) -> VaultWriter:
    """
    Thread-safe singleton for VaultWriter.

    Args:
        vault_root: Optional vault path (uses Config.VAULT_PATH if vault_root and vault_name are None)
        storage: Optional BrainStorage (process singleton if None)
        vault_name: Optional vault name for multi-vault mode. Overrides vault_root.
    """
    with _writer_lock:
        from .config import Config

        if vault_name:
            key = vault_name
            resolved_root = Config.get_vault_path(vault_name)
        else:
            key = str(vault_root) if vault_root else "__default__"
            if vault_root is None and Config._is_multi_vault():
                vault_name = Config.get_default_vault()
                key = vault_name
                resolved_root = Config.get_vault_path(vault_name)
            else:
                resolved_root = (
                    Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
                )

        if key not in _writer_instances:
            _writer_instances[key] = VaultWriter(
                resolved_root, storage=storage, vault_name=vault_name
            )
            logger.info(f"VaultWriter initialized for vault: {key}")

        return _writer_instances[key]
