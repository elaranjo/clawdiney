#!/usr/bin/env python3
"""
Command-line utility for incremental sync of Clawdiney vault.

Usage:
    python sync_vault.py              # Incremental sync
    python sync_vault.py --full       # Full sync (reindex everything)
    python sync_vault.py --status     # Show sync status
"""

import argparse
from pathlib import Path

from config import Config
from logging_config import setup_logging


def show_status():
    """Show current sync status."""
    import json

    from incremental_indexer import STATE_FILE, IncrementalIndexer

    vault_root = Path(Config.VAULT_PATH).expanduser().resolve()
    state_path = vault_root / STATE_FILE

    if not state_path.exists():
        print("No sync state found. Next sync will be full.")
        return

    with open(state_path) as f:
        state = json.load(f)

    print(f"Vault: {vault_root}")
    print(f"Tracked files: {len(state.get('files', {}))}")
    print(f"Last full sync: {state.get('last_full_sync', 'Never')}")

    # Detect pending changes
    indexer = IncrementalIndexer(vault_root)
    new_files, deleted = indexer.detect_changes()
    print("\nPending changes:")
    print(f"  New/modified: {len(new_files)}")
    print(f"  Deleted: {len(deleted)}")


def run_sync(full: bool = False):
    """Run sync operation."""
    from brain_indexer import (
        create_chroma_client,
        create_collection,
        create_neo4j_driver,
    )
    from incremental_indexer import full_sync, incremental_sync

    collection = create_collection(create_chroma_client())
    driver = create_neo4j_driver()

    try:
        if full:
            print("Running full sync...")
            result = full_sync(
                collection=collection,
                neo4j_driver=driver,
            )
        else:
            print("Running incremental sync...")
            result = incremental_sync(
                collection=collection,
                neo4j_driver=driver,
            )

        print("\nSync complete!")
        print(f"  Type: {result['sync_type']}")
        print(f"  Files synced: {result['files_synced']}")
        print(f"  Files deleted: {result['files_deleted']}")
        print(f"  Chunks indexed: {result['indexed_chunks']}")

    finally:
        driver.close()


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Sync Clawdiney vault")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full sync (reindex everything)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show sync status",
    )

    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        run_sync(full=args.full)


if __name__ == "__main__":
    main()
