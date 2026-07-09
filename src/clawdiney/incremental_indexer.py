"""
Incremental indexing against the embedded SQLite store.

Change detection compares SHA-256 content hashes stored in brain.db's
documents table (no separate state file needed) against the vault files
on disk. Only changed files are re-embedded and re-indexed.
"""

import logging
from pathlib import Path
from typing import Any

from .config import Config
from .embedding_providers import EmbeddingProvider, default_provider
from .indexer import (
    build_note_record,
    compute_content_hash,
    discover_vault_files,
    index_note,
)
from .storage import BrainStorage, get_storage

logger = logging.getLogger(__name__)


class IncrementalIndexer:
    """Detects and syncs vault changes using content hashes in brain.db."""

    def __init__(
        self,
        vault_root: Path,
        vault_name: str = "default",
        storage: BrainStorage | None = None,
        provider: EmbeddingProvider | None = None,
    ):
        self.vault_root = Path(vault_root).expanduser().resolve()
        self.vault_name = vault_name
        self.storage = storage or get_storage()
        self._provider = provider

    @property
    def provider(self) -> EmbeddingProvider:
        if self._provider is None:
            self._provider = default_provider()
        return self._provider

    def _current_file_hashes(self) -> dict[str, str]:
        """Map of vault-relative path -> SHA-256 for files on disk."""
        hashes: dict[str, str] = {}
        for file_path in discover_vault_files(self.vault_root):
            try:
                relative = file_path.relative_to(self.vault_root).as_posix()
                hashes[relative] = compute_content_hash(file_path.read_bytes())
            except OSError as e:
                logger.warning(f"Could not read {file_path}: {e}")
        return hashes

    def detect_changes(self) -> tuple[list[str], list[str]]:
        """
        Compare disk against brain.db.

        Returns:
            Tuple of (new_or_modified_relative_paths, deleted_relative_paths)
        """
        current = self._current_file_hashes()
        stored = self.storage.get_document_hashes(self.vault_name)

        new_or_modified = [
            path for path, digest in current.items() if stored.get(path) != digest
        ]
        deleted = [path for path in stored if path not in current]
        return new_or_modified, deleted

    def sync_file(
        self,
        relative_path: str,
        strategy: str | None = None,
        agent_id: str = "default",
    ) -> int:
        """
        Re-index a single note (atomic replace in one transaction).

        agent_id: owning namespace for this document (see
        BrainStorage.upsert_note). Defaults to "default" for ordinary vault
        content; callers writing on behalf of a specific agent (e.g.
        memory_writer) pass their own agent_id.

        Returns number of chunks indexed (0 if file empty/skipped).
        """
        file_path = self.vault_root / relative_path
        note_record = build_note_record(file_path, self.vault_root, strategy=strategy)
        if note_record is None:
            logger.warning(f"Skipping empty file: {relative_path}")
            self.storage.delete_note(self.vault_name, relative_path)
            return 0
        chunks = index_note(
            self.storage,
            self.provider,
            note_record,
            vault_name=self.vault_name,
            agent_id=agent_id,
        )
        logger.info(f"Synced: {relative_path} ({chunks} chunks)")
        return chunks

    def remove_deleted(self, deleted_paths: list[str]) -> int:
        """Remove deleted notes from the store. Returns chunks removed."""
        removed = 0
        for relative_path in deleted_paths:
            removed += self.storage.delete_note(self.vault_name, relative_path)
            logger.info(f"Removed deleted note: {relative_path}")
        return removed


def incremental_sync(
    vault_root: Path | str | None = None,
    storage: BrainStorage | None = None,
    strategy: str | None = None,
    force_full: bool = False,
    vault_name: str = "",
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    """
    Perform incremental sync of the vault.

    Args:
        vault_root: Path to Obsidian vault
        storage: BrainStorage (process singleton if None)
        strategy: Chunking strategy
        force_full: If True, re-index every file regardless of hashes
        vault_name: Vault name for multi-vault support. If provided, uses
                    Config.get_vault_path(vault_name) as vault_root.
        provider: EmbeddingProvider (config default if None)

    Returns:
        Summary dict with sync statistics
    """
    if vault_name:
        vault_root = Config.get_vault_path(vault_name)
    vault_root = Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
    effective_vault = vault_name or "default"

    indexer = IncrementalIndexer(
        vault_root, vault_name=effective_vault, storage=storage, provider=provider
    )

    if force_full:
        logger.info("Force full sync requested")
        changes = list(indexer._current_file_hashes().keys())
        deleted = [
            path
            for path in indexer.storage.get_document_hashes(effective_vault)
            if path not in set(changes)
        ]
        sync_type = "full"
    else:
        changes, deleted = indexer.detect_changes()
        sync_type = "incremental"

    logger.info(f"Detected {len(changes)} new/modified files, {len(deleted)} deleted")

    synced_files = 0
    indexed_chunks = 0
    for relative_path in changes:
        try:
            chunks = indexer.sync_file(relative_path, strategy=strategy)
            if chunks:
                synced_files += 1
                indexed_chunks += chunks
        except Exception as e:
            logger.error(f"Failed to sync {relative_path}: {e}")

    if deleted:
        deleted_chunks = indexer.remove_deleted(deleted)
        logger.info(f"Removed {deleted_chunks} chunks from deleted files")

    result = {
        "vault_root": str(vault_root),
        "sync_type": sync_type,
        "files_synced": synced_files,
        "files_deleted": len(deleted),
        "indexed_chunks": indexed_chunks,
    }
    if vault_name:
        result["vault_name"] = vault_name
    return result


def full_sync(
    vault_root: Path | str | None = None,
    storage: BrainStorage | None = None,
    strategy: str | None = None,
    vault_name: str = "",
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    """Perform a full sync of the vault."""
    return incremental_sync(
        vault_root=vault_root,
        storage=storage,
        strategy=strategy,
        force_full=True,
        vault_name=vault_name,
        provider=provider,
    )


def incremental_sync_all_vaults(
    storage: BrainStorage | None = None,
    strategy: str | None = None,
    force_full: bool = False,
    provider: EmbeddingProvider | None = None,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for vault_name in Config.get_all_vaults():
        logger.info(f"Incremental sync for vault '{vault_name}'")
        results[vault_name] = incremental_sync(
            storage=storage,
            strategy=strategy,
            force_full=force_full,
            vault_name=vault_name,
            provider=provider,
        )
    return results
