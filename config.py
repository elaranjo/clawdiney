import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _get_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

class Config:
    """Centralized configuration class for Clawdiney"""

    # Paths
    VAULT_PATH = os.path.expanduser(os.getenv("VAULT_PATH", "~/Documents/ObsidianVault"))
    CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

    # Model
    MODEL_NAME = os.getenv("MODEL_NAME", "bge-m3")
    RERANK_MODEL_NAME = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    RERANK_THRESHOLD = os.getenv("RERANK_THRESHOLD", "0.5")
    ENABLE_RERANK = _get_bool("ENABLE_RERANK", True)

    # Chunking
    CHUNKING_STRATEGY = os.getenv("CHUNKING_STRATEGY", "headers")
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

    # Neo4j
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "change-this-password")

    @classmethod
    def get_chroma_client_config(cls):
        """Returns configuration for ChromaDB HTTP client"""
        return {
            "host": cls.CHROMA_HOST,
            "port": cls.CHROMA_PORT
        }
