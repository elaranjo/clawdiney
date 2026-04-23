"""
Clawdiney - Hybrid Vector + Graph system for Obsidian vaults.

Transforms an Obsidian Vault into a living knowledge source for AI coding agents.
"""

__version__ = "0.1.0"

# Public API exports
from clawdiney.indexer import index_vault
from clawdiney.incremental_indexer import full_sync, incremental_sync
from clawdiney.query_engine import BrainQueryEngine
from clawdiney.vault_writer import VaultWriter, get_writer
from clawdiney.config import Config
from clawdiney.chunking import chunk_text, Chunk

__all__ = [
    "index_vault",
    "full_sync",
    "incremental_sync",
    "BrainQueryEngine",
    "VaultWriter",
    "get_writer",
    "Config",
    "chunk_text",
    "Chunk",
]
