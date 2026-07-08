"""
Application-wide constants for Clawdiney.

Centralized constants for configuration, timeouts, and other magic numbers.
"""

# Chunking defaults
CHUNK_SIZE_DEFAULT = 500  # Empirically balanced between context and precision
CHUNK_OVERLAP_DEFAULT = 50  # 10% overlap to avoid cutting sentences

# Retrieval
RRF_K = 60  # Reciprocal Rank Fusion constant (standard, robust without tuning)

# Ollama
OLLAMA_EMBEDDING_TIMEOUT_SECONDS = 600  # 10 minutes for Ollama embeddings

# Search defaults
SEARCH_N_RESULTS_DEFAULT = 3  # Default number of search results
SEARCH_EXPAND_GRAPH_DEFAULT = True  # Whether to expand graph by default
SEARCH_USE_RERANK_DEFAULT = True  # Whether to use reranking by default

VAULT_ID_GENERAL = "general"
VAULT_ID_PROJECTS = "projects"
VAULT_ID_PERSONAL = "personal"
VAULT_CONFIG_FILENAME = "clawdiney.toml"
