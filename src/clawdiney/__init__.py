"""
Clawdiney - Hybrid Vector + Graph system for Obsidian vaults.

Transforms an Obsidian Vault into a living knowledge source for AI coding agents.
"""

__version__ = "0.2.0"

# Public API exports
from clawdiney.chunking import Chunk, chunk_text
from clawdiney.config import Config
from clawdiney.embedding_providers import (
    EmbeddingProvider,
    default_provider,
    get_embedding_provider,
)
from clawdiney.incremental_indexer import full_sync, incremental_sync
from clawdiney.indexer import index_vault
from clawdiney.query_engine import BrainQueryEngine
from clawdiney.rag_optimizer import QueryPreprocessor
from clawdiney.reranker import CrossEncoderReranker, get_reranker
from clawdiney.storage import BrainStorage, get_storage
from clawdiney.vault_writer import VaultWriter, get_writer

__all__ = [
    "index_vault",
    "full_sync",
    "incremental_sync",
    "BrainQueryEngine",
    "BrainStorage",
    "get_storage",
    "CrossEncoderReranker",
    "get_reranker",
    "EmbeddingProvider",
    "default_provider",
    "get_embedding_provider",
    "QueryPreprocessor",
    "VaultWriter",
    "get_writer",
    "Config",
    "chunk_text",
    "Chunk",
]
