#!/usr/bin/env python3
"""
File watcher for Clawdiney vault with auto-sync capabilities.

Monitors the Obsidian vault for changes and triggers incremental indexing.
Uses watchdog for efficient file system event handling.
"""

import logging
import signal
import sys
import time
from pathlib import Path
from threading import Event, Thread

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from ..config import Config
from ..incremental_indexer import IncrementalIndexer
from ..logging_config import setup_logging

logger = logging.getLogger(__name__)

# Debounce delay in seconds to avoid processing partial writes
DEBOUNCE_DELAY = 2.0


class VaultEventHandler(FileSystemEventHandler):
    """Handles file system events for the Obsidian vault."""

    def __init__(self, indexer: IncrementalIndexer, shutdown_event: Event):
        self.indexer = indexer
        self.shutdown_event = shutdown_event
        self.pending_files: set[Path] = set()
        self.pending_deletes: set[Path] = set()
        self._debounce_thread: Thread | None = None

    def _schedule_sync(self) -> None:
        """Schedule a debounced sync operation."""
        if self._debounce_thread is not None and self._debounce_thread.is_alive():
            return  # Already scheduled

        self._debounce_thread = Thread(target=self._debounced_sync, daemon=True)
        self._debounce_thread.start()

    def _debounced_sync(self) -> None:
        """Wait for debounce delay, then sync pending changes."""
        time.sleep(DEBOUNCE_DELAY)

        if self.shutdown_event.is_set():
            return

        if not self.pending_files and not self.pending_deletes:
            return

        files_to_sync = list(self.pending_files)
        deletes_to_process = list(self.pending_deletes)
        self.pending_files.clear()
        self.pending_deletes.clear()

        logger.info(f"Syncing {len(files_to_sync)} modified/created files...")
        for file_path in files_to_sync:
            if file_path.suffix == ".md" and file_path.exists():
                try:
                    from brain_indexer import (
                        create_chroma_client,
                        create_collection,
                        create_neo4j_driver,
                    )

                    collection = create_collection(create_chroma_client())
                    driver = create_neo4j_driver()
                    self.indexer.sync_file(file_path, collection, driver)
                    driver.close()
                except Exception as e:
                    logger.error(f"Failed to sync {file_path}: {e}")

        if deletes_to_process:
            logger.info(f"Processing {len(deletes_to_process)} deleted files...")
            try:
                from brain_indexer import create_chroma_client, create_collection

                collection = create_collection(create_chroma_client())
                self.indexer.remove_deleted_from_chroma(deletes_to_process, collection)
            except Exception as e:
                logger.error(f"Failed to process deletes: {e}")

    def _handle_md_file(self, event_path: Path, is_delete: bool = False) -> None:
        """Handle a markdown file event."""
        if event_path.suffix != ".md":
            return

        # Skip hidden files and temp files
        if event_path.name.startswith("."):
            return
        if event_path.name.endswith("~") or event_path.suffix in [".tmp", ".swp"]:
            return

        logger.debug(f"File {'deleted' if is_delete else 'changed'}: {event_path}")

        if is_delete:
            self.pending_deletes.add(event_path)
        else:
            self.pending_files.add(event_path)

        self._schedule_sync()

    def on_modified(self, event) -> None:
        if isinstance(event, FileModifiedEvent) and not event.is_directory:
            self._handle_md_file(Path(event.src_path))

    def on_created(self, event) -> None:
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            self._handle_md_file(Path(event.src_path))

    def on_deleted(self, event) -> None:
        if isinstance(event, FileDeletedEvent) and not event.is_directory:
            self._handle_md_file(Path(event.src_path), is_delete=True)

    def on_moved(self, event) -> None:
        if isinstance(event, FileMovedEvent) and not event.is_directory:
            # Treat move as delete + create
            self._handle_md_file(Path(event.src_path), is_delete=True)
            self._handle_md_file(Path(event.dest_path))


class VaultWatcher:
    """Main watcher class that orchestrates vault monitoring."""

    def __init__(self, vault_root: Path | None = None, auto_sync_on_start: bool = True):
        self.vault_root = Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
        self.auto_sync_on_start = auto_sync_on_start
        self.indexer = IncrementalIndexer(self.vault_root)
        self.shutdown_event = Event()
        self.observer: Observer | None = None

    def _initial_sync(self) -> None:
        """Perform initial sync if needed."""
        if not self.auto_sync_on_start:
            logger.info("Auto-sync disabled. Skipping initial sync.")
            return

        new_files, deleted_files = self.indexer.detect_changes()
        total_changes = len(new_files) + len(deleted_files)

        if total_changes == 0:
            logger.info("Vault is up to date. No sync needed.")
            return

        logger.info(
            f"Found {total_changes} changes ({len(new_files)} new/modified, {len(deleted_files)} deleted)"
        )
        logger.info("Running initial sync...")

        try:
            from brain_indexer import (
                create_chroma_client,
                create_collection,
                create_neo4j_driver,
            )

            collection = create_collection(create_chroma_client())
            driver = create_neo4j_driver()

            from incremental_indexer import incremental_sync

            result = incremental_sync(
                vault_root=self.vault_root,
                collection=collection,
                neo4j_driver=driver,
            )

            logger.info(
                f"Initial sync complete: {result['files_synced']} files synced, "
                f"{result['files_deleted']} deleted, {result['indexed_chunks']} chunks"
            )
            driver.close()
        except Exception as e:
            logger.error(f"Initial sync failed: {e}")

    def start(self) -> None:
        """Start watching the vault."""
        logger.info(f"Starting vault watcher for: {self.vault_root}")

        if not self.vault_root.exists():
            logger.error(f"Vault path does not exist: {self.vault_root}")
            return

        # Initial sync
        self._initial_sync()

        # Set up file watcher
        event_handler = VaultEventHandler(self.indexer, self.shutdown_event)
        self.observer = Observer()
        self.observer.schedule(event_handler, str(self.vault_root), recursive=True)
        self.observer.start()

        logger.info("Vault watcher started. Press Ctrl+C to stop.")

        # Keep running until shutdown
        try:
            while not self.shutdown_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the watcher."""
        logger.info("Stopping vault watcher...")
        self.shutdown_event.set()

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            logger.info("Vault watcher stopped")


def main():
    """Main entry point for the watcher."""
    setup_logging()

    logger.info("=" * 60)
    logger.info("Clawdiney Vault Watcher")
    logger.info("=" * 60)

    watcher = VaultWatcher(auto_sync_on_start=True)

    # Set up signal handlers
    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}")
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    watcher.start()


if __name__ == "__main__":
    main()
