#!/usr/bin/env python3
"""
Command-line utility for incremental sync of Clawdiney vault.

Usage:
    python sync_vault.py                        # Incremental sync (single or all vaults)
    python sync_vault.py --full                 # Full sync (reindex everything)
    python sync_vault.py --status               # Show sync status
    python sync_vault.py --vault NAME           # Sync specific vault
    python sync_vault.py --vault NAME --full    # Full sync for specific vault
    python sync_vault.py --vault NAME --status  # Status for specific vault
"""

import argparse
from pathlib import Path

from ..config import Config
from ..logging_config import setup_logging


def show_status(vault_name: str = ""):
    """Show current sync status for one or all vaults."""
    from ..incremental_indexer import IncrementalIndexer

    def _show_vault_status(name: str, vault_root: Path):
        print(f"\nVault: {name}")
        print(f"  Root: {vault_root}")

        indexer = IncrementalIndexer(vault_root, vault_name=name)
        tracked = indexer.storage.get_document_hashes(name)
        print(f"  Tracked documents: {len(tracked)}")

        new_files, deleted = indexer.detect_changes()
        print("  Pending changes:")
        print(f"    New/modified: {len(new_files)}")
        print(f"    Deleted: {len(deleted)}")

    if vault_name:
        vault_root = Path(Config.get_vault_path(vault_name)).expanduser().resolve()
        _show_vault_status(vault_name, vault_root)
    else:
        vaults = Config.get_all_vaults()
        if not vaults:
            print("No vaults configured.")
            return
        for name, path in vaults.items():
            vault_root = Path(path).expanduser().resolve()
            _show_vault_status(name, vault_root)


def run_sync(full: bool = False, vault_name: str = ""):
    """Run sync operation for one or all vaults."""
    from ..incremental_indexer import (
        full_sync,
        incremental_sync,
        incremental_sync_all_vaults,
    )

    if vault_name:
        vault_root = Config.get_vault_path(vault_name)
        print(f"Syncing vault '{vault_name}' from {vault_root}")

        if full:
            print("Running full sync...")
            result = full_sync(vault_name=vault_name)
        else:
            print("Running incremental sync...")
            result = incremental_sync(vault_name=vault_name)

        print("\nSync complete!")
        print(f"  Vault: {result.get('vault_name', vault_name)}")
        print(f"  Type: {result['sync_type']}")
        print(f"  Files synced: {result['files_synced']}")
        print(f"  Files deleted: {result['files_deleted']}")
        print(f"  Chunks indexed: {result['indexed_chunks']}")
    else:
        results = incremental_sync_all_vaults(force_full=full)

        print("\nSync complete!")
        for vault_name, result in results.items():
            print(f"\n  Vault '{vault_name}':")
            print(f"    Type: {result['sync_type']}")
            print(f"    Files synced: {result['files_synced']}")
            print(f"    Files deleted: {result['files_deleted']}")
            print(f"    Chunks indexed: {result['indexed_chunks']}")

        total_files = sum(r["files_synced"] for r in results.values())
        total_chunks = sum(r["indexed_chunks"] for r in results.values())
        print(f"\n  Total: {total_files} files, {total_chunks} chunks indexed")


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
    parser.add_argument(
        "--vault",
        type=str,
        default="",
        help="Sync only a specific vault by name",
    )

    args = parser.parse_args()

    if args.status:
        show_status(vault_name=args.vault)
    else:
        run_sync(full=args.full, vault_name=args.vault)


if __name__ == "__main__":
    main()
