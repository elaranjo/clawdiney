"""
Clawdiney - Hybrid Vector + Graph system for Obsidian vaults.

Transforms an Obsidian Vault into a living knowledge source for AI coding agents.
"""

__version__ = "0.1.0"

# Public API exports
from clawdiney.chunking import Chunk, chunk_text
from clawdiney.config import Config
from clawdiney.incremental_indexer import full_sync, incremental_sync
from clawdiney.indexer import index_vault
from clawdiney.query_engine import BrainQueryEngine
from clawdiney.query_cache import QueryCache
from clawdiney.rag_optimizer import MMRReranker, QueryPreprocessor
from clawdiney.vault_writer import VaultWriter, get_writer

__all__ = [
    "index_vault",
    "full_sync",
    "incremental_sync",
    "BrainQueryEngine",
    "QueryCache",
    "MMRReranker",
    "QueryPreprocessor",
    "VaultWriter",
    "get_writer",
    "Config",
    "chunk_text",
    "Chunk",
]
