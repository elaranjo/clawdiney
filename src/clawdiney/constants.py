"""
Application-wide constants for Clawdiney.

Centralized constants for configuration, timeouts, and other magic numbers.
"""

# Chunking defaults
CHUNK_SIZE_DEFAULT = 500  # Empirically balanced between context and precision
CHUNK_OVERLAP_DEFAULT = 50  # 10% overlap to avoid cutting sentences

# Reranking configuration
RERANK_TIMEOUT_SECONDS = 30  # Maximum time for reranking operation
RERANK_BATCH_SIZE = 5  # Number of documents to process in parallel
RERANK_THRESHOLD_DEFAULT = 0.5  # Minimum score to include reranked result

# Database timeouts
CHROMADB_TIMEOUT_SECONDS = 300  # 5 minutes for ChromaDB operations
OLLAMA_EMBEDDING_TIMEOUT_SECONDS = 600  # 10 minutes for Ollama embeddings

# Neo4j configuration
NEO4J_HEALTHCHECK_TIMEOUT_SECONDS = 30
NEO4J_HEALTHCHECK_START_PERIOD_SECONDS = 60

# Resource limits (Docker)
NEO4J_MEMORY_LIMIT = "2G"
NEO4J_CPU_LIMIT = "2.0"
CHROMADB_MEMORY_LIMIT = "1G"
CHROMADB_CPU_LIMIT = "1.0"

# Search defaults
SEARCH_N_RESULTS_DEFAULT = 3  # Default number of search results
SEARCH_EXPAND_GRAPH_DEFAULT = True  # Whether to expand graph by default
SEARCH_USE_RERANK_DEFAULT = True  # Whether to use reranking by default

VAULT_ID_GENERAL = "general"
VAULT_ID_PROJECTS = "projects"
VAULT_ID_PERSONAL = "personal"
COLLECTION_PREFIX = "vault_"
VAULT_CONFIG_FILENAME = "clawdiney.toml"
